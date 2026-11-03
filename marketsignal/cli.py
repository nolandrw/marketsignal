"""Command-line entrypoints for collection, replayable demo, and inspection."""

from __future__ import annotations

import argparse
import json
import sys
import time
import os
from dataclasses import replace
from pathlib import Path

from .dashboard import render_dashboard
from .detection import detect_signals
from .gamma import GammaError, discover_markets
from .models import Market
from .postgres import PostgresStorage, open_storage
from .storage import Storage


def collect(db_file: str, max_markets: int, max_pages: int,
            retention_days: int = 30) -> int:
    started_at = int(time.time())
    with open_storage(db_file) as store:
        recovered = store.recover_stale_runs(started_at)
        run_id = store.start_run(started_at)
        try:
            markets, events_scanned = discover_markets(max_markets=max_markets, max_pages=max_pages)
            if not markets:
                raise GammaError("No markets matched the watchlist; keeping previous observations unchanged")
            inserted = store.save_snapshots(markets, started_at)
            new_signals = detect_signals(store, markets, started_at)
            # Perform retention cleanup at most once per UTC day. Signal-linked
            # before/after quotes are retained as an audit trail.
            day = str(started_at // 86400)
            expired = 0
            if store.get_metadata("last_retention_day") != day:
                expired = store.prune_snapshots(started_at - retention_days * 86400)
                store.set_metadata("last_retention_day", day)
            store.set_metadata("dataset", "live")
            store.finish_run(run_id, int(time.time()), status="ok", events=events_scanned,
                             markets=inserted, signals=len(new_signals))
            print(json.dumps({"status": "ok", "events_scanned": events_scanned,
                              "eligible_markets": len(markets), "new_snapshots": inserted,
                              "new_signals": len(new_signals), "expired_snapshots": expired,
                              "recovered_runs": recovered,
                              "backend": "postgres" if os.environ.get("DATABASE_URL") else "sqlite"}, indent=2))
            return 0
        except Exception as exc:
            # Untrusted network/database exceptions can echo secrets or URLs.
            # Store the error class, not an arbitrary third-party message.
            summary = type(exc).__name__
            store.finish_run(run_id, int(time.time()), status="error", error=summary)
            print(f"Collection failed safely ({summary})", file=sys.stderr)
            return 1


def demo(db_file: str, report_file: str) -> int:
    """Create a synthetic replay for layout and detector verification only."""
    current = Storage.bucket(int(time.time()))
    basis = [
        ("demo-1", "Federal Reserve cuts rates at the next meeting?", 0.42, 0.57, 1_200_000, 320_000),
        ("demo-2", "Major AI regulation passes before year-end?", 0.33, 0.21, 750_000, 185_000),
        ("demo-3", "New international climate agreement signed?", 0.52, 0.54, 185_000, 95_000),
        ("demo-4", "National infrastructure bill passes?", 0.14, 0.31, 600_000, 280_000),
    ]
    with Storage(db_file) as store:
        run_id = store.start_run(current, source="synthetic-demo")
        past: list[Market] = []
        present: list[Market] = []
        for market_id, question, before, after, volume, liquidity in basis:
            market = Market(market_id, market_id, "Synthetic demonstration event", "demo-only",
                            question, "123456789", before, volume, liquidity, "")
            past.append(market)
            present.append(replace(market, yes_price=after))
        store.save_snapshots(past, current - 86400)
        store.save_snapshots(past, current - 3600)
        inserted = store.save_snapshots(present, current)
        signals = detect_signals(store, present, current)
        store.set_metadata("dataset", "demo")
        store.finish_run(run_id, current, status="ok", events=4, markets=inserted, signals=len(signals))
        total_signals = store.dashboard_data()["stats"]["signals"]
        rendered = render_dashboard(store, report_file)
    print(json.dumps({"status": "demo", "synthetic_signals_visible": total_signals,
                      "new_signals": len(signals),
                      "database": db_file, "dashboard": str(rendered)}, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Auditable Polymarket movement monitoring")
    commands = parser.add_subparsers(dest="command", required=True)
    ingest = commands.add_parser("collect", help="Fetch current markets and append observations")
    ingest.add_argument("--db", default="data/marketsignal.db")
    ingest.add_argument("--max-markets", type=int, default=150)
    ingest.add_argument("--max-pages", type=int, default=8)
    ingest.add_argument("--retention-days", type=int, default=30)
    dashboard = commands.add_parser("report", help="Generate a read-only HTML operations dashboard")
    dashboard.add_argument("--db", default="data/marketsignal.db")
    dashboard.add_argument("--out", default="reports/index.html")
    health = commands.add_parser("health", help="Fail if the collector is stale or unsuccessful")
    health.add_argument("--db", default="data/marketsignal.db")
    health.add_argument("--max-age-minutes", type=int, default=35)
    commands.add_parser("init-db", help="Initialize PostgreSQL schema with a privileged migration account")
    simulate = commands.add_parser("demo", help="Generate a clearly labeled synthetic detector demo")
    simulate.add_argument("--db", default="demo/demo.db")
    simulate.add_argument("--out", default="demo/index.html")
    arguments = parser.parse_args(argv)
    if arguments.command == "collect":
        if not 1 <= arguments.max_markets <= 1000 or not 1 <= arguments.max_pages <= 100:
            parser.error("--max-markets must be 1..1000 and --max-pages 1..100")
        if not 1 <= arguments.retention_days <= 365:
            parser.error("--retention-days must be 1..365")
        return collect(arguments.db, arguments.max_markets, arguments.max_pages,
                       arguments.retention_days)
    if arguments.command == "demo":
        return demo(arguments.db, arguments.out)
    if arguments.command == "init-db":
        url = os.environ.get("DATABASE_URL")
        if not url:
            parser.error("init-db requires DATABASE_URL (privileged migration credential)")
        with PostgresStorage(url, initialize=True):
            pass
        print("PostgreSQL schema initialized (run with restricted role for collection)")
        return 0
    if arguments.command == "health":
        with open_storage(arguments.db) as store:
            runs = store.dashboard_data()["runs"]
        last = runs[0] if runs else None
        age = (int(time.time()) - last["started_at"]) if last else None
        healthy = last is not None and last["status"] == "ok" and age is not None and age <= arguments.max_age_minutes * 60
        print(json.dumps({"healthy": healthy, "last_run_status": last["status"] if last else None,
                          "age_seconds": age}))
        return 0 if healthy else 1
    with open_storage(arguments.db) as store:
        output = render_dashboard(store, arguments.out)
    print(f"Dashboard generated: {output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
