"""Read-only, rate-conscious Polymarket Gamma API client.

Prices here are the API's outcomePrices, NOT a verified probability estimate,
bid/ask midpoint, or proof of any real-world event. Live data fetching is
intentionally isolated for easy fixture testing and API-version changes.
"""

from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .models import Market

API_URL = "https://gamma-api.polymarket.com/events/keyset"
USER_AGENT = "MarketSignal/0.1 (read-only portfolio research)"
VALID_SLUG = re.compile(r"^[a-zA-Z0-9_-]+$")


class GammaError(RuntimeError):
    """The upstream API did not return a usable result."""


def _fetch_json(url: str) -> dict:
    request = Request(url, headers={"Accept": "application/json", "User-Agent": USER_AGENT})
    for attempt in range(3):
        try:
            with urlopen(request, timeout=25) as response:
                data = json.load(response)
            if not isinstance(data, dict):
                raise GammaError("Expected an object from Gamma API")
            return data
        except HTTPError as exc:
            if exc.code not in (429, 500, 502, 503, 504) or attempt == 2:
                raise GammaError(f"Gamma API HTTP {exc.code}") from exc
        except (URLError, TimeoutError, OSError) as exc:
            if attempt == 2:
                raise GammaError(f"Gamma API connection failed: {exc}") from exc
        time.sleep(1.5 * (attempt + 1))
    raise GammaError("Exhausted Gamma API retries")


def _json_list(value: object) -> list:
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except json.JSONDecodeError:
            return []
    return []


def _number(value: object) -> float | None:
    try:
        number = float(value)  # type: ignore[arg-type]
        if not (number == number and abs(number) != float("inf")):
            return None
        return number
    except (ValueError, TypeError):
        return None


def _category(event: dict, market: dict) -> str:
    labels = [str(market.get("category") or ""), str(event.get("category") or "")]
    for tag in event.get("tags") or []:
        if isinstance(tag, dict):
            labels.append(str(tag.get("label") or tag.get("slug") or ""))
    if market.get("sportsMarketType"):
        return "sports"
    return next((label.strip().lower()[:60] for label in labels if label.strip()), "general")


def parse_market(event: dict, market: dict, *, now: datetime | None = None) -> Market | None:
    """Return only usable, active, binary Yes/No markets.

    Filtering is intentionally conservative about numerical integrity, not
    editorial category. All subject areas are eligible for the owner's broad
    coverage mandate; a downstream topic desk decides publication relevance.
    """
    if not (market.get("active") and not market.get("closed")):
        return None
    outcomes = _json_list(market.get("outcomes"))
    prices = _json_list(market.get("outcomePrices"))
    tokens = _json_list(market.get("clobTokenIds"))
    if len(outcomes) != 2 or {str(x).lower() for x in outcomes} != {"yes", "no"}:
        return None
    yes_index = next(i for i, value in enumerate(outcomes) if str(value).lower() == "yes")
    if len(prices) != 2 or len(tokens) != 2:
        return None
    price = _number(prices[yes_index])
    volume = _number(market.get("volume24hr"))
    liquidity = _number(market.get("liquidityNum") or market.get("liquidity"))
    if any(value is None for value in (price, volume, liquidity)):
        return None
    assert price is not None and volume is not None and liquidity is not None
    if not (0.01 < price < 0.99 and volume >= 0 and liquidity >= 0):
        return None
    end_date = str(market.get("endDate") or "")
    if end_date:
        try:
            expiry = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
            if expiry.tzinfo is None:
                expiry = expiry.replace(tzinfo=timezone.utc)
            if expiry <= (now or datetime.now(timezone.utc)):
                return None
        except ValueError:
            return None
    slug = str(event.get("slug") or "")
    if not VALID_SLUG.fullmatch(slug):
        return None
    market_id = str(market.get("id") or "")
    event_id = str(event.get("id") or "")
    if not market_id or not event_id or not str(tokens[yes_index]).isdigit():
        return None
    return Market(
        market_id=market_id,
        event_id=event_id,
        event_title=str(event.get("title") or ""),
        event_slug=slug,
        question=str(market.get("question") or ""),
        yes_token_id=str(tokens[yes_index]),
        yes_price=price,
        volume_24h=volume,
        liquidity=liquidity,
        end_date=end_date,
        category=_category(event, market),
    )


def discover_markets(
    *, max_markets: int = 150, max_pages: int = 8, min_liquidity: float = 25000.0,
    min_volume_24h: float = 50000.0,
) -> tuple[list[Market], int]:
    """Discover a bounded high-activity watchlist using current keyset API.

    Note: this is a high-volume sample, NOT complete Polymarket coverage.
    Event ranking is by 24h volume; market-level filters apply afterward.
    """
    cursor: str | None = None
    found: dict[str, Market] = {}
    events_scanned = 0
    for _ in range(max_pages):
        query = {
            "limit": 100,
            "closed": "false",
            "order": "volume24hr",
            "ascending": "false",
        }
        if cursor:
            query["after_cursor"] = cursor
        payload = _fetch_json(f"{API_URL}?{urlencode(query)}")
        events = payload.get("events")
        if not isinstance(events, list):
            raise GammaError("Gamma API returned no events array; check schema")
        events_scanned += len(events)
        for event in events:
            if not isinstance(event, dict):
                continue
            # Large 'build-your-map' combinatorial events generate many nearly
            # identical contracts and overwhelm an editorial watchlist.
            open_markets = [m for m in event.get("markets") or []
                            if isinstance(m, dict) and m.get("active") and not m.get("closed")]
            if len(open_markets) > 30 or "build your map" in str(event.get("title", "")).lower():
                continue
            event_candidates: list[Market] = []
            for raw_market in open_markets:
                if not isinstance(raw_market, dict):
                    continue
                market = parse_market(event, raw_market)
                if market and market.liquidity >= min_liquidity and market.volume_24h >= min_volume_24h:
                    event_candidates.append(market)
            # Limit concentration in one event; prefer its most traded legs.
            for market in sorted(event_candidates, key=lambda item: item.volume_24h, reverse=True)[:3]:
                found[market.market_id] = market
        if len(found) >= max_markets:
            break
        cursor = payload.get("next_cursor")
        if not cursor or len(events) < 100:
            break
    return sorted(found.values(), key=lambda item: item.volume_24h, reverse=True)[:max_markets], events_scanned
