"""Isolated public Kalshi discovery adapter, not yet mixed into USD scoring.

Kalshi reports volume in *contracts*, whereas MarketSignal's initial detector
assumes USD-like Polymarket trading metrics. Never silently substitute one
unit for another or claim two differently resolved contracts are equivalent.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

from .agent_sources import JSONTransport, SourceError


ENDPOINT = "https://external-api.kalshi.com/trade-api/v2/markets"
TICKER = re.compile(r"^[A-Za-z0-9_-]{1,160}$")


def _number(value: object) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


@dataclass(frozen=True)
class KalshiQuote:
    ticker: str
    event_ticker: str
    title: str
    category: str
    midpoint_yes: float
    yes_bid: float
    yes_ask: float
    volume_24h_contracts: float
    liquidity_usd: float
    close_time: str
    price_basis: str = "kalshi_yes_bid_ask_midpoint"


def parse_kalshi_market(row: dict) -> KalshiQuote | None:
    ticker = str(row.get("ticker") or "")
    event = str(row.get("event_ticker") or "")
    if not TICKER.fullmatch(ticker) or not TICKER.fullmatch(event):
        return None
    bid, ask = _number(row.get("yes_bid_dollars")), _number(row.get("yes_ask_dollars"))
    volume = _number(row.get("volume_24h_fp"))
    liquidity = _number(row.get("liquidity_dollars"))
    if (bid is None or ask is None or volume is None or liquidity is None or
            not 0 <= bid <= ask <= 1 or volume < 0 or liquidity < 0 or
            bid == 0 and ask == 0):
        return None
    # We intentionally do not use the last trade as a fallback for a missing
    # orderbook quote; old trades can masquerade as current information.
    return KalshiQuote(ticker, event, str(row.get("title") or "")[:200],
                       str(row.get("category") or "general")[:60].lower(),
                       round((bid + ask) / 2, 6), bid, ask, volume, liquidity,
                       str(row.get("close_time") or "")[:40])


class KalshiDiscovery:
    def __init__(self, transport: JSONTransport):
        self.transport = transport

    def sample(self, *, max_pages: int = 2, page_size: int = 50) -> tuple[KalshiQuote, ...]:
        if not 1 <= max_pages <= 3 or not 1 <= page_size <= 100:
            raise ValueError("Kalshi request budget exceeded")
        cursor = ""
        found: dict[str, KalshiQuote] = {}
        for _ in range(max_pages):
            args: dict[str, str | int] = {"status": "open", "limit": page_size}
            if cursor:
                args["cursor"] = cursor
            response = self.transport.get(ENDPOINT, args)
            if not isinstance(response, dict) or not isinstance(response.get("markets"), list):
                raise SourceError("Invalid Kalshi market response")
            for row in response["markets"][:page_size]:
                if isinstance(row, dict):
                    item = parse_kalshi_market(row)
                    if item:
                        found[item.ticker] = item
            cursor = str(response.get("cursor") or "")
            if not cursor:
                break
        return tuple(found.values())
