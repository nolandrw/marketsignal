"""Small immutable data contracts shared across the ingestion and signal stages."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Market:
    market_id: str
    event_id: str
    event_title: str
    event_slug: str
    question: str
    yes_token_id: str
    yes_price: float
    volume_24h: float
    liquidity: float
    end_date: str
    # Optional provenance fields keep v1 JSON archives and synthetic fixtures
    # readable. A venue-qualified market_id avoids exchange ID collisions.
    venue: str = "polymarket"
    category: str = "general"

    @property
    def source_url(self) -> str:
        if self.venue == "kalshi":
            # Exchange URLs are not canonicalized by the market API. Do not
            # invent a deep link using a ticker that may have a different slug.
            return "https://kalshi.com/markets"
        return f"https://polymarket.com/event/{self.event_slug}"


@dataclass(frozen=True)
class Signal:
    market_id: str
    observed_at: int
    baseline_at: int
    window_hours: int
    previous_price: float
    current_price: float
    change_pp: float
    score: int
    volume_24h: float
    liquidity: float
