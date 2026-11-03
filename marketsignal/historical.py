"""Bounded, optional Polymarket historical backfill for offline calibration.

An explicit command captures price points only; no account information,
orders, comments, or model inference. Live daily collection does not depend
on backfill success. Backfill files are immutable per UTC date by default.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from .agent_sources import PolymarketHistory, PublicJSONTransport
from .models import Market


def backfill_prices(archive_file: str | Path, output_dir: str | Path, *,
                    max_markets: int = 3, lookback_days: int = 30,
                    provider: PolymarketHistory | None = None) -> dict:
    """Fetch selected history in seven-day windows under a strict call budget."""
    if not 1 <= max_markets <= 10 or not 1 <= lookback_days <= 35:
        raise ValueError("Historical backfill budget exceeded")
    source = Path(archive_file)
    record = json.loads(source.read_text(encoding="utf-8"))
    observed_at = int(record["observed_at"])
    destination = Path(output_dir) / datetime.fromtimestamp(
        observed_at, timezone.utc).strftime("%Y-%m-%d.json")
    if destination.exists():
        existing = json.loads(destination.read_text(encoding="utf-8"))
        return {"reused": True, "markets": len(existing.get("markets", [])),
                "observations": sum(len(m.get("points", [])) for m in existing.get("markets", [])),
                "errors": existing.get("errors", [])}
    client = provider or PolymarketHistory(PublicJSONTransport(timeout=8, retries=1))
    eligible = []
    for raw in record.get("markets", []):
        try:
            market = Market(**raw)
        except (TypeError, ValueError):
            continue
        if market.venue == "polymarket" and market.yes_token_id.isdigit():
            eligible.append(market)
    eligible.sort(key=lambda m: m.volume_24h, reverse=True)
    captured = []
    errors = []
    for market in eligible[:max_markets]:
        start = observed_at - lookback_days * 86400
        cursor = start
        observations = {}
        failed = False
        while cursor < observed_at:
            until = min(cursor + 7 * 86400, observed_at)
            try:
                for point in client.between(market.yes_token_id, cursor, until):
                    if start <= point.timestamp < observed_at:
                        observations[point.timestamp] = point.yes_price
            except (OSError, ValueError, RuntimeError):
                errors.append({"market_id": market.market_id,
                               "kind": "historical_source_unavailable"})
                failed = True
                break
            cursor = until
        if failed:
            continue
        captured.append({"market_id": market.market_id, "venue": "polymarket",
                         "price_basis": "clob_prices_history",
                         "points": [{"timestamp": ts, "yes_price": price}
                                    for ts, price in sorted(observations.items())]})
    payload = {"schema_version": 1, "observed_at": observed_at,
               "lookback_days": lookback_days, "markets": captured, "errors": errors,
               "historical_not_live_probabilities": True}
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".pending")
    try:
        temporary.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return {"reused": False, "markets": len(captured),
            "observations": sum(len(row["points"]) for row in captured), "errors": errors}
