import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from marketsignal.detection import detect_signals
from marketsignal.models import Market
from marketsignal.storage import Storage


class SignalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Storage(Path(self.temp.name) / "test.db")
        self.start = 1_800_000_000  # 15-minute-aligned after bucketing
        self.market = Market("m1", "e1", "Policy", "policy", "Will it pass?", "12345",
                             0.4, 250_000, 100_000, "2030-01-01T00:00:00Z")

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def test_detects_eight_point_hourly_move_and_dedupes(self):
        timestamp = self.store.bucket(self.start)
        self.store.save_snapshots([self.market], timestamp - 3600)
        updated = replace(self.market, yes_price=0.51)
        self.store.save_snapshots([updated], timestamp)
        signals = detect_signals(self.store, [updated], timestamp)
        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0].window_hours, 1)
        self.assertAlmostEqual(signals[0].change_pp, 11)
        self.assertEqual(detect_signals(self.store, [updated], timestamp), [])

    def test_rejects_thin_markets(self):
        timestamp = self.store.bucket(self.start)
        thin = replace(self.market, liquidity=100)
        self.store.save_snapshots([thin], timestamp - 3600)
        moved = replace(thin, yes_price=0.80)
        self.store.save_snapshots([moved], timestamp)
        self.assertEqual(detect_signals(self.store, [moved], timestamp), [])

    def test_twenty_four_hour_signal(self):
        timestamp = self.store.bucket(self.start)
        self.store.save_snapshots([self.market], timestamp - 86400)
        updated = replace(self.market, yes_price=0.60)
        self.store.save_snapshots([updated], timestamp)
        signals = detect_signals(self.store, [updated], timestamp)
        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0].window_hours, 24)

    def test_missing_baseline_yields_no_signal(self):
        timestamp = self.store.bucket(self.start)
        self.store.save_snapshots([self.market], timestamp)
        self.assertEqual(detect_signals(self.store, [self.market], timestamp), [])

    def test_store_idempotency(self):
        timestamp = self.store.bucket(self.start)
        self.assertEqual(self.store.save_snapshots([self.market], timestamp), 1)
        self.assertEqual(self.store.save_snapshots([replace(self.market, yes_price=0.6)], timestamp), 0)
        self.assertEqual(self.store.reference_snapshot("m1", timestamp, 0), (timestamp, 0.4))

    def test_retention_preserves_signal_provenance(self):
        timestamp = self.store.bucket(self.start)
        self.store.save_snapshots([self.market], timestamp - 86400)
        self.store.save_snapshots([self.market], timestamp - 3600)
        moved = replace(self.market, yes_price=0.51)
        self.store.save_snapshots([moved], timestamp)
        detect_signals(self.store, [moved], timestamp)
        removed = self.store.prune_snapshots(timestamp + 1)
        self.assertEqual(removed, 1)  # unrelated 24h baseline
        self.assertIsNotNone(self.store.reference_snapshot("m1", timestamp, 0))
        self.assertIsNotNone(self.store.reference_snapshot("m1", timestamp - 3600, 0))

    def test_interrupted_runs_are_recovered(self):
        timestamp = self.store.bucket(self.start)
        run = self.store.start_run(timestamp - 7200)
        self.assertEqual(self.store.recover_stale_runs(timestamp), 1)
        self.assertEqual(self.store.recover_stale_runs(timestamp), 0)
        self.assertEqual(self.store.dashboard_data()["runs"][0]["status"], "interrupted")


if __name__ == "__main__":
    unittest.main()
