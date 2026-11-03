"""Multi-horizon, inspectable story pitches from archived market observations.

This module is *not* a significance test and never decides to publish. Price
history is evaluated strictly as-of the candidate timestamp (no look-ahead).
Missing or stale baselines are reported as missing, never filled with guesses.
"""

from __future__ import annotations

import json
import math
import statistics
from dataclasses import asdict, dataclass
from pathlib import Path

from .models import Market


HORIZONS = ((1, 1800), (24, 12 * 3600), (168, 24 * 3600), (720, 48 * 3600))
MIN_VOLUME = 50_000.0
MIN_LIQUIDITY = 25_000.0
DEFAULT_24H_THRESHOLD_PP = 8.0
CATEGORY_24H_FALLBACK_PP = {
    "sports": 15.0, "esports": 15.0, "crypto": 15.0,
    "entertainment": 12.0, "weather": 12.0,
}


@dataclass(frozen=True)
class MarketObservation:
    timestamp: int
    price: float
    volume_24h: float
    liquidity: float


@dataclass(frozen=True)
class QuantitativePitch:
    market_id: str
    venue: str
    category: str
    observed_at: int
    changes_pp: dict[str, float]
    baseline_times: dict[str, int]
    historical_daily_samples: int
    typical_daily_movement_pp: float | None
    volume_to_historical_median: float | None
    threshold_24h_pp: float
    movement_surprise: float | None
    quantitative_score: int
    eligible_for_topic_review: bool
    reasons: tuple[str, ...]

    def to_dict(self) -> dict:
        return asdict(self)


def _valid_point(point: MarketObservation) -> bool:
    return (isinstance(point.timestamp, int) and point.timestamp > 0 and
            all(math.isfinite(x) for x in (point.price, point.volume_24h, point.liquidity)) and
            0 <= point.price <= 1 and point.volume_24h >= 0 and point.liquidity >= 0)


def _closest(points: tuple[MarketObservation, ...], target: int, tolerance: int) -> MarketObservation | None:
    candidates = (p for p in points if abs(p.timestamp - target) <= tolerance)
    return min(candidates, key=lambda p: abs(p.timestamp - target), default=None)


def create_pitch(market: Market, observed_at: int,
                 history: list[MarketObservation] | tuple[MarketObservation, ...]) -> QuantitativePitch:
    """Score one quote against earlier observations, with missing-data abstention."""
    if not (0 <= market.yes_price <= 1 and math.isfinite(market.yes_price)):
        raise ValueError("Invalid current price")
    points = tuple(sorted({p.timestamp: p for p in history
                           if _valid_point(p) and p.timestamp < observed_at}.values(),
                          key=lambda p: p.timestamp))
    changes: dict[str, float] = {}
    times: dict[str, int] = {}
    for hours, tolerance in HORIZONS:
        baseline = _closest(points, observed_at - hours * 3600, tolerance)
        if baseline is not None:
            changes[f"{hours}h"] = round((market.yes_price - baseline.price) * 100, 3)
            times[f"{hours}h"] = baseline.timestamp

    # Only comparable daily intervals inform daily volatility: a missing week
    # must not be interpreted as one exceptionally volatile day.
    daily_abs = [abs((right.price - left.price) * 100)
                 for left, right in zip(points, points[1:])
                 if 12 * 3600 <= right.timestamp - left.timestamp <= 36 * 3600]
    typical = (statistics.median(daily_abs) if len(daily_abs) >= 5 else None)
    sigma = max(1.0, 1.4826 * typical) if typical is not None else None
    baseline_threshold = CATEGORY_24H_FALLBACK_PP.get(
        market.category.lower(), DEFAULT_24H_THRESHOLD_PP)
    threshold = (round(max(4.0, min(20.0, 2.5 * sigma)), 2)
                 if sigma is not None else baseline_threshold)

    historical_volumes = [p.volume_24h for p in points if p.volume_24h > 0]
    volume_ratio = None
    if len(historical_volumes) >= 3:
        base_volume = statistics.median(historical_volumes)
        if base_volume > 0:
            volume_ratio = round(market.volume_24h / base_volume, 3)

    delta24 = abs(changes.get("24h", 0.0))
    surprise = round(delta24 / sigma, 3) if sigma is not None and "24h" in changes else None
    # Multi-window cumulative movements are independently useful. Never
    # combine missing periods as if those changes had been observed.
    significant = [window for window, cutoff in
                   (("1h", 8.0), ("24h", threshold), ("168h", 15.0), ("720h", 22.0))
                   if window in changes and abs(changes[window]) >= cutoff]
    healthy = market.volume_24h >= MIN_VOLUME and market.liquidity >= MIN_LIQUIDITY
    reasons = []
    if not healthy:
        reasons.append("insufficient_market_depth")
    if not changes:
        reasons.append("no_historical_baseline")
    if significant:
        reasons.extend("movement_" + window for window in significant)
    if sigma is None:
        reasons.append("uncalibrated_volatility")

    # 0..100 triage index, deliberately distinct from a probability or a
    # journalistic-quality score. The 7/30-day terms prevent missing slower
    # stories, while volume and depth reduce fragile one-trade anomalies.
    normalized = max((abs(changes.get(window, 0.0)) / cutoff
                      for window, cutoff in (("1h", 8.0), ("24h", threshold),
                                             ("168h", 15.0), ("720h", 22.0))),
                     default=0.0)
    magnitude = min(55.0, normalized * 25.0)
    volume = min(20.0, (volume_ratio if volume_ratio is not None else
                        market.volume_24h / 200_000.0) * 10.0)
    depth = min(15.0, market.liquidity / 100_000.0 * 15.0)
    coverage = min(10.0, len(changes) * 2.5)
    score = round(magnitude + volume + depth + coverage)
    return QuantitativePitch(
        market_id=market.market_id, venue=market.venue, category=market.category,
        observed_at=observed_at, changes_pp=changes, baseline_times=times,
        historical_daily_samples=len(daily_abs),
        typical_daily_movement_pp=round(typical, 3) if typical is not None else None,
        volume_to_historical_median=volume_ratio, threshold_24h_pp=threshold,
        movement_surprise=surprise, quantitative_score=score,
        eligible_for_topic_review=bool(healthy and significant), reasons=tuple(reasons),
    )


def pitches_from_archive(archive_file: str | Path, *, max_prior_days: int = 50,
                         max_pitches: int = 500,
                         history_dir: str | Path | None = None) -> list[QuantitativePitch]:
    """Replay only dated local archive files, never a live source or model."""
    source = Path(archive_file)
    current = json.loads(source.read_text(encoding="utf-8"))
    now = int(current["observed_at"])
    historical: dict[str, list[MarketObservation]] = {}
    older = sorted(p for p in source.parent.glob("????-??-??.json") if p.name < source.name)
    for path in older[-max_prior_days:]:
        record = json.loads(path.read_text(encoding="utf-8"))
        timestamp = record.get("observed_at")
        if not isinstance(timestamp, int) or timestamp >= now:
            continue
        for value in record.get("markets", []):
            try:
                m = Market(**value)
                historical.setdefault(m.market_id, []).append(MarketObservation(
                    timestamp, m.yes_price, m.volume_24h, m.liquidity))
            except (TypeError, ValueError):
                continue
    # A historical backfill is optional. Its finer time resolution allows
    # valid one-hour comparisons without pretending daily quotes are intraday.
    # Preserve complete daily observations over bare backfill prices at the
    # same timestamp; backfill points do not contain compatible USD volumes.
    extra = Path(history_dir) if history_dir is not None else source.parent.parent / "history"
    backfill = extra / source.name
    if backfill.exists():
        payload = json.loads(backfill.read_text(encoding="utf-8"))
        if payload.get("schema_version") != 1 or int(payload.get("observed_at", -1)) != now:
            raise ValueError("Historical file does not match daily archive")
        for row in payload.get("markets", []):
            if row.get("venue") != "polymarket":
                continue
            target = historical.setdefault(str(row.get("market_id")), [])
            observed_times = {point.timestamp for point in target}
            for point in row.get("points", []):
                try:
                    value = MarketObservation(int(point["timestamp"]), float(point["yes_price"]),
                                              0.0, 0.0)
                except (KeyError, TypeError, ValueError):
                    continue
                if value.timestamp < now and value.timestamp not in observed_times:
                    target.append(value)
                    observed_times.add(value.timestamp)
    result = []
    for value in current.get("markets", [])[:max_pitches]:
        market = Market(**value)
        result.append(create_pitch(market, now, historical.get(market.market_id, [])))
    return sorted(result, key=lambda p: (p.eligible_for_topic_review, p.quantitative_score),
                  reverse=True)
