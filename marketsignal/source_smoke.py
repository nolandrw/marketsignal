"""Bounded, sanitized live-public-source smoke probe (no raw result retention)."""

from __future__ import annotations

import json
import time
from pathlib import Path

from .agent_sources import (
    BlueskySearch, GDELTSearch, PolymarketHistory, PublicJSONTransport, SourceError,
)


def probe_sources(archive_dir: str | Path, *, now: int | None = None,
                  transport=None) -> dict:
    now = int(time.time()) if now is None else now
    client = transport or PublicJSONTransport(timeout=8, retries=0)
    probes = {}
    archive = Path(archive_dir)
    files = sorted(archive.glob("????-??-??.json"))
    token_id = None
    if files:
        try:
            if files[-1].stat().st_size > 5_000_000:
                raise ValueError("Oversized archive")
            record = json.loads(files[-1].read_text(encoding="utf-8"))
            for market in record.get("markets", []):
                value = market.get("yes_token_id")
                if isinstance(value, str) and value.isdecimal() and 10 <= len(value) <= 120:
                    token_id = value
                    break
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
            pass
    attempts = [
        ("bluesky", lambda: BlueskySearch(client).search("polymarket", now - 3600, now, 2)),
        ("gdelt", lambda: GDELTSearch(client).search("polymarket", now - 86400, now, 2)),
    ]
    if token_id:
        attempts.insert(0, ("polymarket_history",
                            lambda: PolymarketHistory(client).between(
                                token_id, now - 86400, now)))
    else:
        probes["polymarket_history"] = {"status": "skipped", "reason": "no_token"}
    for name, call in attempts:
        try:
            hits = call()
            probes[name] = {"status": "ok", "observations": len(hits)}
        except SourceError as exc:
            # SourceError contains only deliberately sanitized diagnostics:
            # status code or a fixed failure class, never URL or response body.
            probes[name] = {"status": "unavailable", "reason": str(exc)}
        except Exception as exc:
            # Never print provider exception strings, request URLs or user data.
            probes[name] = {"status": "unavailable", "error_class": type(exc).__name__}
    return {
        "mode": "read_only_source_smoke", "publication_enabled": False,
        "contents_retained": False, "sources": probes,
    }
