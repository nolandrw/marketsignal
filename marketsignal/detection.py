"""Deterministic signal detection. No model determines prices or math."""

from __future__ import annotations

from .models import Market, Signal
from .storage import Storage

MIN_LIQUIDITY_USD = 25_000.0
MIN_VOLUME_24H_USD = 50_000.0
WINDOWS = ((1, 8.0, 900), (24, 15.0, 1800))


def _signal_score(change_pp: float, threshold_pp: float, volume: float, liquidity: float) -> int:
    """Explicit, uncalibrated prioritization heuristic (not a p-value)."""
    movement = min(50.0, abs(change_pp) / threshold_pp * 25)
    participation = min(25.0, volume / 250_000 * 25)
    depth = min(25.0, liquidity / 100_000 * 25)
    return round(movement + participation + depth)


def detect_signals(store: Storage, markets: list[Market], observed_at: int) -> list[Signal]:
    bucket = store.bucket(observed_at)
    created: list[Signal] = []
    for market in markets:
        if market.liquidity < MIN_LIQUIDITY_USD or market.volume_24h < MIN_VOLUME_24H_USD:
            continue
        if store.recent_signal_exists(market.market_id, bucket):
            continue
        candidates: list[Signal] = []
        for hours, threshold, tolerance in WINDOWS:
            baseline = store.reference_snapshot(market.market_id, bucket - hours * 3600, tolerance)
            if baseline is None:
                continue
            baseline_at, reference = baseline
            delta = round((market.yes_price - reference) * 100, 3)
            if abs(delta) < threshold:
                continue
            candidates.append(Signal(
                market_id=market.market_id, observed_at=bucket, baseline_at=baseline_at,
                window_hours=hours, previous_price=reference,
                current_price=market.yes_price, change_pp=delta,
                score=_signal_score(delta, threshold, market.volume_24h, market.liquidity),
                volume_24h=market.volume_24h, liquidity=market.liquidity,
            ))
        if candidates:
            best = max(candidates, key=lambda item: item.score)
            if store.save_signal(best):
                created.append(best)
    return sorted(created, key=lambda item: item.score, reverse=True)
