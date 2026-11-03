"""Zero-cost daily collector: Git-tracked JSON records + static HTML.

This is an alternative adapter around the existing detector, not a separate
detector or a persistent cloud database. Each successful UTC date has exactly
one immutable collection record. A later paid deployment can ingest the same
records into PostgreSQL without changing the signal schema.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .dashboard import render_dashboard
from .detection import detect_signals
from .gamma import GammaError, discover_markets
from .models import Market, Signal
from .storage import Storage

ARCHIVE_VERSION = 1
# A 24-hour target tolerates scheduling delays and up to one missed day.
# The actual hours between observations are written to each signal.
DAILY_WINDOWS = ((24, 15.0, 36 * 3600),)


def _record_file(directory: Path, epoch: int) -> Path:
    name = datetime.fromtimestamp(epoch, tz=timezone.utc).strftime("%Y-%m-%d.json")
    return directory / name


def _load_record(path: Path) -> dict:
    record = json.loads(path.read_text(encoding="utf-8"))
    if record.get("schema_version") != ARCHIVE_VERSION:
        raise ValueError(f"Unsupported daily archive schema in {path.name}")
    if not isinstance(record.get("observed_at"), int):
        raise ValueError(f"Missing observation time in {path.name}")
    if not isinstance(record.get("markets"), list) or not isinstance(record.get("signals"), list):
        raise ValueError(f"Invalid market/signal arrays in {path.name}")
    return record


def _restore(store: Storage, record: dict) -> None:
    observed_at = record["observed_at"]
    markets = [Market(**market) for market in record["markets"]]
    store.save_snapshots(markets, observed_at)
    for signal in record["signals"]:
        store.save_signal(Signal(**signal))
    run_id = store.start_run(observed_at, source="daily-archive")
    store.finish_run(run_id, observed_at, status="ok",
                     events=int(record["events_scanned"]),
                     markets=len(markets), signals=len(record["signals"]))


def run_daily(archive_dir: str | Path, report_file: str | Path, *,
              now: int | None = None, max_markets: int = 150,
              max_pages: int = 8,
              discover: Callable[..., tuple[list[Market], int]] = discover_markets) -> dict:
    """Collect once per UTC date; reuse an existing record on a retry.

    A workflow uses this without a database or model API key. Failures leave no
    new dated record, so a failed run cannot be mistaken for valid coverage.
    """
    now = int(time.time()) if now is None else now
    bucket = Storage.bucket(now)
    archive = Path(archive_dir)
    archive.mkdir(parents=True, exist_ok=True)
    today = _record_file(archive, now)
    reused = today.exists()

    with Storage(":memory:") as store:
        # Only recent history is required for a daily comparator. Old JSON
        # records remain in Git for future backtests and migration.
        prior_files = sorted(p for p in archive.glob("????-??-??.json") if p.name < today.name)[-45:]
        for file in prior_files:
            _restore(store, _load_record(file))

        if reused:
            current = _load_record(today)
            _restore(store, current)
        else:
            markets, events_scanned = discover(max_markets=max_markets, max_pages=max_pages)
            if not markets:
                raise GammaError("No eligible markets discovered; refusing an empty daily record")
            run_id = store.start_run(bucket, source="daily-live")
            inserted = store.save_snapshots(markets, bucket)
            new_signals = detect_signals(store, markets, bucket, windows=DAILY_WINDOWS)
            store.finish_run(run_id, bucket, status="ok", events=events_scanned,
                             markets=inserted, signals=len(new_signals))
            current = {
                "schema_version": ARCHIVE_VERSION,
                "source": "Polymarket Gamma outcomePrices (read-only)",
                "observed_at": bucket,
                "events_scanned": events_scanned,
                "markets": [asdict(market) for market in markets],
                "signals": [asdict(signal) for signal in new_signals],
            }
            # Write a complete record only after all collection and checks
            # succeed. The GitHub job commits it after the report is rendered.
            temporary = today.with_suffix(".pending")
            try:
                temporary.write_text(json.dumps(current, indent=2, sort_keys=True) + "\n",
                                     encoding="utf-8")
                os.replace(temporary, today)
            finally:
                temporary.unlink(missing_ok=True)

        store.set_metadata("dataset", "daily")
        rendered = render_dashboard(store, report_file)

    latest = {
        "schema_version": ARCHIVE_VERSION,
        "date": today.stem,
        "observed_at": current["observed_at"],
        "events_scanned": current["events_scanned"],
        "markets_observed": len(current["markets"]),
        "new_signals": len(current["signals"]),
        "signals": current["signals"],
        "reused_existing_snapshot": reused,
        "archive_file": str(today),
        "report_file": str(rendered),
    }
    # The static site exposes a structured payload for later consumers.
    payload = rendered.parent / "latest.json"
    payload.write_text(json.dumps({key: value for key, value in latest.items()
                                   if key not in {"archive_file", "report_file"}},
                                  indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return latest
