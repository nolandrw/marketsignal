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

    @property
    def source_url(self) -> str:
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
