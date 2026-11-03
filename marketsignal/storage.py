"""SQLite implementation of the local, append-only observation store."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from .models import Market, Signal


SCHEMA = """
CREATE TABLE IF NOT EXISTS markets (
  market_id TEXT PRIMARY KEY,
  event_id TEXT NOT NULL,
  event_title TEXT NOT NULL,
  event_slug TEXT NOT NULL,
  question TEXT NOT NULL,
  yes_token_id TEXT NOT NULL,
  end_date TEXT NOT NULL,
  last_seen_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS snapshots (
  market_id TEXT NOT NULL REFERENCES markets(market_id),
  observed_at INTEGER NOT NULL,
  yes_price REAL NOT NULL CHECK (yes_price BETWEEN 0 AND 1),
  volume_24h REAL NOT NULL CHECK (volume_24h >= 0),
  liquidity REAL NOT NULL CHECK (liquidity >= 0),
  price_basis TEXT NOT NULL DEFAULT 'gamma_outcomePrices',
  PRIMARY KEY (market_id, observed_at)
);
CREATE INDEX IF NOT EXISTS idx_snapshots_time ON snapshots(observed_at);
CREATE TABLE IF NOT EXISTS signals (
  signal_id INTEGER PRIMARY KEY AUTOINCREMENT,
  market_id TEXT NOT NULL REFERENCES markets(market_id),
  observed_at INTEGER NOT NULL,
  baseline_at INTEGER NOT NULL,
  window_hours INTEGER NOT NULL,
  previous_price REAL NOT NULL,
  current_price REAL NOT NULL,
  change_pp REAL NOT NULL,
  score INTEGER NOT NULL,
  volume_24h REAL NOT NULL,
  liquidity REAL NOT NULL,
  UNIQUE(market_id, observed_at)
);
CREATE INDEX IF NOT EXISTS idx_signals_time ON signals(observed_at DESC);
CREATE TABLE IF NOT EXISTS runs (
  run_id INTEGER PRIMARY KEY AUTOINCREMENT,
  started_at INTEGER NOT NULL,
  finished_at INTEGER,
  status TEXT NOT NULL,
  source TEXT NOT NULL,
  events_scanned INTEGER NOT NULL DEFAULT 0,
  markets_saved INTEGER NOT NULL DEFAULT 0,
  signals_created INTEGER NOT NULL DEFAULT 0,
  error_message TEXT
);
CREATE TABLE IF NOT EXISTS metadata (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
"""


class Storage:
    def __init__(self, filename: str | Path):
        path = Path(filename)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, timeout=15)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys = ON")
        self.db.execute("PRAGMA journal_mode = WAL")
        self.db.executescript(SCHEMA)
        # Pre-release compatibility for databases created by the first
        # prototype iteration. Unknown historical baseline times remain NULL;
        # we never fabricate timestamps for prior signal records.
        columns = {row["name"] for row in self.db.execute("PRAGMA table_info(signals)")}
        if "baseline_at" not in columns:
            with self.db:
                self.db.execute("ALTER TABLE signals ADD COLUMN baseline_at INTEGER")

    def close(self) -> None:
        self.db.close()

    def __enter__(self) -> "Storage":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    @staticmethod
    def bucket(timestamp: int, interval_seconds: int = 900) -> int:
        return timestamp - timestamp % interval_seconds

    def save_snapshots(self, markets: list[Market], observed_at: int) -> int:
        """Insert one immutable observation per market per 15-minute bucket."""
        time_bucket = self.bucket(observed_at)
        inserted = 0
        with self.db:
            for market in markets:
                self.db.execute(
                    """INSERT INTO markets VALUES (?,?,?,?,?,?,?,?)
                    ON CONFLICT(market_id) DO UPDATE SET
                    event_title=excluded.event_title, event_slug=excluded.event_slug,
                    question=excluded.question, end_date=excluded.end_date,
                    last_seen_at=excluded.last_seen_at""",
                    (market.market_id, market.event_id, market.event_title, market.event_slug,
                     market.question, market.yes_token_id, market.end_date, time_bucket),
                )
                cursor = self.db.execute(
                    """INSERT OR IGNORE INTO snapshots
                    (market_id, observed_at, yes_price, volume_24h, liquidity)
                    VALUES (?,?,?,?,?)""",
                    (market.market_id, time_bucket, market.yes_price,
                     market.volume_24h, market.liquidity),
                )
                inserted += cursor.rowcount
        return inserted

    def reference_snapshot(self, market_id: str, target_time: int, tolerance: int) -> tuple[int, float] | None:
        row = self.db.execute(
            """SELECT observed_at,yes_price FROM snapshots
            WHERE market_id=? AND observed_at BETWEEN ? AND ?
            ORDER BY ABS(observed_at - ?) ASC LIMIT 1""",
            (market_id, target_time - tolerance, target_time + tolerance, target_time),
        ).fetchone()
        return (int(row["observed_at"]), float(row["yes_price"])) if row else None

    def recent_signal_exists(self, market_id: str, observed_at: int, cooldown_seconds: int = 21600) -> bool:
        row = self.db.execute(
            "SELECT 1 FROM signals WHERE market_id=? AND observed_at>? LIMIT 1",
            (market_id, observed_at - cooldown_seconds),
        ).fetchone()
        return row is not None

    def save_signal(self, signal: Signal) -> bool:
        with self.db:
            row = self.db.execute(
                """INSERT OR IGNORE INTO signals
                (market_id,observed_at,baseline_at,window_hours,previous_price,current_price,change_pp,score,volume_24h,liquidity)
                VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (signal.market_id, signal.observed_at, signal.baseline_at, signal.window_hours,
                 signal.previous_price, signal.current_price, signal.change_pp,
                 signal.score, signal.volume_24h, signal.liquidity),
            )
        return row.rowcount == 1

    def start_run(self, started_at: int, source: str = "live") -> int:
        with self.db:
            row = self.db.execute(
                "INSERT INTO runs (started_at,status,source) VALUES (?,?,?)",
                (started_at, "running", source),
            )
        return int(row.lastrowid)

    def finish_run(self, run_id: int, finished_at: int, *, status: str,
                   events: int = 0, markets: int = 0, signals: int = 0,
                   error: str | None = None) -> None:
        with self.db:
            self.db.execute(
                """UPDATE runs SET finished_at=?,status=?,events_scanned=?,
                markets_saved=?,signals_created=?,error_message=? WHERE run_id=?""",
                (finished_at, status, events, markets, signals, error, run_id),
            )

    def recover_stale_runs(self, now: int, stale_after: int = 1800) -> int:
        with self.db:
            row = self.db.execute(
                """UPDATE runs SET status='interrupted',finished_at=?,
                error_message='Worker terminated without completing run'
                WHERE status='running' AND started_at<?""",
                (now, now - stale_after),
            )
        return row.rowcount

    def prune_snapshots(self, cutoff: int) -> int:
        """Expire unremarkable old quotes, not points supporting a signal."""
        with self.db:
            row = self.db.execute(
                """DELETE FROM snapshots WHERE observed_at<? AND NOT EXISTS
                (SELECT 1 FROM signals s WHERE s.market_id=snapshots.market_id
                 AND (s.observed_at=snapshots.observed_at OR s.baseline_at=snapshots.observed_at))""",
                (cutoff,),
            )
        return row.rowcount

    def set_metadata(self, key: str, value: str) -> None:
        with self.db:
            self.db.execute(
                "INSERT INTO metadata VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, value),
            )

    def get_metadata(self, key: str, default: str = "") -> str:
        row = self.db.execute("SELECT value FROM metadata WHERE key=?", (key,)).fetchone()
        return str(row["value"]) if row else default

    def dashboard_data(self, limit: int = 30) -> dict:
        signals = [dict(row) for row in self.db.execute(
            """SELECT s.*,m.question,m.event_title,m.event_slug FROM signals s
            JOIN markets m USING(market_id) ORDER BY s.observed_at DESC,s.score DESC LIMIT ?""", (limit,)
        ).fetchall()]
        markets = [dict(row) for row in self.db.execute(
            """SELECT m.*,s.yes_price,s.volume_24h,s.liquidity,s.observed_at
            FROM markets m JOIN snapshots s ON s.market_id=m.market_id
            WHERE s.observed_at=(SELECT MAX(observed_at) FROM snapshots WHERE market_id=m.market_id)
            ORDER BY s.volume_24h DESC LIMIT ?""", (limit,)
        ).fetchall()]
        runs = [dict(row) for row in self.db.execute(
            "SELECT * FROM runs ORDER BY run_id DESC LIMIT 8"
        ).fetchall()]
        stats = self.db.execute(
            """SELECT (SELECT COUNT(*) FROM markets) markets,
                      (SELECT COUNT(*) FROM snapshots) observations,
                      (SELECT COUNT(*) FROM signals) signals,
                      (SELECT COUNT(*) FROM runs WHERE status IN ('error','interrupted')) failures"""
        ).fetchone()
        return {"stats": dict(stats), "signals": signals, "markets": markets,
                "runs": runs, "dataset": self.get_metadata("dataset", "live")}
