import tempfile
import unittest
from pathlib import Path

from marketsignal.learning import (
    EditorialLabel, FEATURE_NAMES, NewsRanker, feature_vector, train_challenger,
)
from marketsignal.models import Market
from marketsignal.quantitative import create_pitch


def labels(n=80):
    data = []
    for i in range(n):
        useful = int(i % 2 == 0)
        features = [0.0] * len(FEATURE_NAMES)
        features[0] = 18 if useful else 1
        features[5] = 82 if useful else 22
        data.append(EditorialLabel(f"market-{i}", (i + 1) * 86400,
                                   tuple(features), useful,
                                   "independently_reviewed_human"))
    return data


class LearningTests(unittest.TestCase):
    def test_training_refuses_synthetic_or_insufficient_labels(self):
        with self.assertRaises(ValueError):
            EditorialLabel("m", 1, (0.0,) * len(FEATURE_NAMES), 1, "synthetic")
        with self.assertRaises(ValueError):
            train_challenger(labels(20))

    def test_chronological_training_produces_only_challenger(self):
        ranker = train_challenger(labels())
        self.assertEqual(ranker.status, "challenger_only")
        self.assertEqual(ranker.training_examples, 64)
        # The 16-row holdout contains only eight positive examples, so 0.8
        # is the mathematical ceiling for precision among ten selections.
        self.assertEqual(ranker.holdout_metrics["precision_at_10"], .8)
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "ranker.json"
            ranker.save(target)
            loaded = NewsRanker.load(target)
            self.assertEqual(loaded.status, "challenger_only")
            self.assertGreater(loaded.probability_of_editorial_value(labels()[0].features), .5)

    def test_time_leakage_prevents_training(self):
        samples = labels()
        samples = [EditorialLabel(item.market_id, 1, item.features,
                                  item.worth_investigating, item.label_source) for item in samples]
        with self.assertRaises(ValueError):
            train_challenger(samples)

    def test_feature_schema_is_fixed(self):
        market = Market("m", "e", "t", "slug", "question", "1000", .6, 100000, 50000, "")
        pitch = create_pitch(market, 1000000, [])
        self.assertEqual(len(feature_vector(pitch)), len(FEATURE_NAMES))


if __name__ == "__main__":
    unittest.main()
