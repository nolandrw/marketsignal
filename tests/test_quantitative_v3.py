import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from marketsignal.historical import backfill_prices
from marketsignal.models import Market
from marketsignal.quantitative import MarketObservation, create_pitch, pitches_from_archive


def market(**changes):
    base = Market("m1", "ev", "Synthetic event", "synthetic", "Will something happen?",
                  "12345678901", .55, 500000, 150000, "")
    return replace(base, **changes)


class QuantitativeTests(unittest.TestCase):
    def test_five_point_move_can_be_significant_in_quiet_market(self):
        now = 80 * 86400
        history = [MarketObservation(now - i * 86400, .50 + .0001 * (i % 2),
                                     100000, 60000) for i in range(1, 36)]
        pitch = create_pitch(market(yes_price=.55), now, history)
        self.assertTrue(pitch.eligible_for_topic_review)
        self.assertEqual(pitch.threshold_24h_pp, 4)
        self.assertIn("movement_24h", pitch.reasons)
        self.assertIn("168h", pitch.changes_pp)
        self.assertIn("720h", pitch.changes_pp)

    def test_missing_baseline_never_manufactures_movement(self):
        pitch = create_pitch(market(), 80 * 86400, [])
        self.assertFalse(pitch.eligible_for_topic_review)
        self.assertEqual(pitch.changes_pp, {})
        self.assertIn("no_historical_baseline", pitch.reasons)

    def test_future_points_are_excluded_and_thin_markets_fail(self):
        now = 90 * 86400
        points = [MarketObservation(now + 1, .01, 100000, 100000),
                  MarketObservation(now - 86400, .40, 100000, 100000)]
        pitch = create_pitch(market(liquidity=100, yes_price=.58), now, points)
        self.assertEqual(pitch.changes_pp["24h"], 18.0)
        self.assertFalse(pitch.eligible_for_topic_review)

    def test_archive_replay_supports_monthly_window(self):
        now = 90 * 86400
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder) / "archive"
            directory.mkdir()
            for i in range(1, 34):
                past = market(yes_price=.40)
                (directory / f"2026-10-{i:02d}.json").write_text(json.dumps({
                    "observed_at": now - i * 86400, "markets": [past.__dict__]}))
            latest = directory / "2026-11-03.json"
            latest.write_text(json.dumps({"observed_at": now, "markets": [market().__dict__]}))
            results = pitches_from_archive(latest)
            self.assertEqual(len(results), 1)
            self.assertIn("720h", results[0].changes_pp)

    def test_finer_backfill_can_create_one_hour_comparison(self):
        now = 90 * 86400
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder) / "archive"
            directory.mkdir()
            latest = directory / "2026-11-03.json"
            latest.write_text(json.dumps({"observed_at": now, "markets": [market().__dict__]}))
            history = Path(folder) / "history"
            history.mkdir()
            (history / latest.name).write_text(json.dumps({
                "schema_version": 1, "observed_at": now,
                "markets": [{"market_id": "m1", "venue": "polymarket",
                             "points": [{"timestamp": now - 3600, "yes_price": .4}]}]}))
            pitch = pitches_from_archive(latest)[0]
            self.assertEqual(pitch.changes_pp["1h"], 15.0)

    def test_backfill_is_bounded_and_idempotent(self):
        class FakeHistory:
            calls = 0

            def between(self, token_id, since, until):
                from marketsignal.agent_sources import PricePoint
                self.calls += 1
                return (PricePoint(since + 100, .44),)

        with tempfile.TemporaryDirectory() as folder:
            src = Path(folder) / "archive.json"
            src.write_text(json.dumps({"observed_at": 90 * 86400,
                                       "markets": [market().__dict__]}))
            fake = FakeHistory()
            first = backfill_prices(src, Path(folder) / "history", max_markets=1,
                                    lookback_days=14, provider=fake)
            second = backfill_prices(src, Path(folder) / "history", max_markets=1,
                                     lookback_days=14, provider=fake)
            self.assertEqual(first["observations"], 2)
            self.assertTrue(second["reused"])
            self.assertEqual(fake.calls, 2)


if __name__ == "__main__":
    unittest.main()
