"""Zero-dependency learning infrastructure for a *future* labeled news ranker.

No model is activated automatically. Time-ordered holdout evaluation and real
human labels are mandatory. The ranker predicts editorial investigation value,
not contract outcomes or whether any reported claim is true.
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path

from .quantitative import QuantitativePitch


FEATURE_NAMES = (
    "abs_24h_pp", "abs_7d_pp", "abs_30d_pp", "volume_ratio",
    "typical_daily_pp", "quant_score", "history_samples", "horizon_count",
    "is_sports", "is_crypto", "is_politics", "is_business",
)
MIN_LABELS = 60


def feature_vector(pitch: QuantitativePitch) -> tuple[float, ...]:
    cat = pitch.category.lower()
    return (
        abs(pitch.changes_pp.get("24h", 0)),
        abs(pitch.changes_pp.get("168h", 0)),
        abs(pitch.changes_pp.get("720h", 0)),
        min(10.0, pitch.volume_to_historical_median or 0.0),
        min(50.0, pitch.typical_daily_movement_pp or 0.0),
        float(pitch.quantitative_score),
        min(60.0, float(pitch.historical_daily_samples)),
        float(len(pitch.changes_pp)),
        float("sport" in cat), float("crypto" in cat),
        float(any(x in cat for x in ("politic", "election", "government"))),
        float(any(x in cat for x in ("business", "econom", "finance"))),
    )


@dataclass(frozen=True)
class EditorialLabel:
    market_id: str
    observed_at: int
    features: tuple[float, ...]
    worth_investigating: int  # 0 or 1, as judged at that historical moment
    label_source: str  # independently_reviewed_human

    def __post_init__(self):
        if (not self.market_id or not isinstance(self.observed_at, int) or
                len(self.features) != len(FEATURE_NAMES) or
                any(not math.isfinite(value) for value in self.features) or
                self.worth_investigating not in (0, 1) or
                self.label_source != "independently_reviewed_human"):
            raise ValueError("Only complete, independently human-labeled examples are trainable")


@dataclass(frozen=True)
class NewsRanker:
    schema_version: int
    feature_names: tuple[str, ...]
    means: tuple[float, ...]
    scales: tuple[float, ...]
    coefficients: tuple[float, ...]
    intercept: float
    training_examples: int
    holdout_metrics: dict[str, float | int]
    status: str = "challenger_only"

    def probability_of_editorial_value(self, features: tuple[float, ...]) -> float:
        if len(features) != len(self.feature_names) or any(not math.isfinite(x) for x in features):
            raise ValueError("Feature schema mismatch")
        z = self.intercept + sum(w * ((x - mean) / scale)
                                 for x, mean, scale, w in
                                 zip(features, self.means, self.scales, self.coefficients))
        z = max(-35, min(35, z))
        return 1.0 / (1.0 + math.exp(-z))

    def save(self, filename: str | Path) -> None:
        path = Path(filename)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2, sort_keys=True) + "\n", encoding="utf-8")

    @classmethod
    def load(cls, filename: str | Path) -> "NewsRanker":
        value = json.loads(Path(filename).read_text(encoding="utf-8"))
        if value.get("schema_version") != 1 or tuple(value.get("feature_names", [])) != FEATURE_NAMES:
            raise ValueError("Incompatible or unexpected model schema")
        for key in ("feature_names", "means", "scales", "coefficients"):
            value[key] = tuple(value[key])
        model = cls(**value)
        if (model.status != "challenger_only" or model.training_examples < MIN_LABELS or
                any(scale <= 0 or not math.isfinite(scale) for scale in model.scales)):
            raise ValueError("Model must be a valid challenger, never a publisher")
        return model


def _sigmoid(value: float) -> float:
    return 1 / (1 + math.exp(-max(-35, min(35, value))))


def _precision_at_k(scores: list[float], labels: list[int], k: int = 10) -> float:
    order = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:k]
    return round(sum(labels[i] for i in order) / len(order), 4) if order else 0.0


def train_challenger(labels: list[EditorialLabel]) -> NewsRanker:
    """Chronological split; refuse tiny or single-class training/holdout data."""
    if len(labels) < MIN_LABELS:
        raise ValueError("Insufficient real editorial labels")
    ordered = sorted(labels, key=lambda item: (item.observed_at, item.market_id))
    if len({(item.market_id, item.observed_at) for item in ordered}) != len(ordered):
        raise ValueError("Duplicate historical candidates")
    split = int(len(ordered) * .8)
    training, holdout = ordered[:split], ordered[split:]
    if (max(item.observed_at for item in training) >= min(item.observed_at for item in holdout) or
            len({item.worth_investigating for item in training}) < 2 or
            len({item.worth_investigating for item in holdout}) < 2 or
            min(sum(l.worth_investigating for l in training),
                sum(1 - l.worth_investigating for l in training)) < 10):
        raise ValueError("Chronological and class-diverse holdout unavailable")
    means = tuple(sum(l.features[i] for l in training) / len(training)
                  for i in range(len(FEATURE_NAMES)))
    scales = tuple(max(1.0, math.sqrt(sum((l.features[i] - means[i]) ** 2
                              for l in training) / len(training)))
                   for i in range(len(FEATURE_NAMES)))
    weights = [0.0] * len(FEATURE_NAMES)
    prior = sum(l.worth_investigating for l in training) / len(training)
    bias = math.log(prior / (1 - prior))
    # Small regularized full-batch logistic regression; deterministic.
    for _ in range(500):
        gradient = [0.0] * len(weights)
        bias_gradient = 0.0
        for item in training:
            x = [(value - mean) / scale
                 for value, mean, scale in zip(item.features, means, scales)]
            error = _sigmoid(bias + sum(w * v for w, v in zip(weights, x))) - item.worth_investigating
            bias_gradient += error
            for j, value in enumerate(x):
                gradient[j] += error * value
        for j in range(len(weights)):
            weights[j] -= .15 * (gradient[j] / len(training) + .02 * weights[j])
        bias -= .15 * bias_gradient / len(training)
    provisional = NewsRanker(1, FEATURE_NAMES, means, scales, tuple(weights), bias,
                             len(training), {})
    scores = [provisional.probability_of_editorial_value(item.features) for item in holdout]
    answers = [item.worth_investigating for item in holdout]
    baseline = [item.features[FEATURE_NAMES.index("quant_score")] for item in holdout]
    metrics = {"holdout_samples": len(holdout),
               "brier_score": round(sum((p - y) ** 2 for p, y in zip(scores, answers)) / len(holdout), 4),
               "precision_at_10": _precision_at_k(scores, answers),
               "baseline_precision_at_10": _precision_at_k(baseline, answers)}
    return NewsRanker(1, FEATURE_NAMES, means, scales, tuple(weights), bias,
                      len(training), metrics)


def load_human_labels(path: str | Path) -> list[EditorialLabel]:
    rows = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise ValueError("Expected a list of human-labeled examples")
    return [EditorialLabel(market_id=row["market_id"],
                           observed_at=int(row["observed_at"]),
                           features=tuple(float(x) for x in row["features"]),
                           worth_investigating=row["worth_investigating"],
                           label_source=row["label_source"]) for row in rows]
