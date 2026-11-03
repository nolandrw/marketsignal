"""Deterministic tests of the free daily path; no external API access."""

import json
import tempfile
import unittest
from pathlib import Path

from marketsignal.daily import run_daily
from marketsignal.gamma import GammaError
from marketsignal.models import Market


class DailyTests(unittest.TestCase):
    BASE_TIME = 1793520000  # 2026-11-01 UTC, on a 15-minute boundary

    @staticmethod
    def market(yes_price: float) -> Market:
        return Market(
            market_id="m-1", event_id="e-1", event_title="Federal decision",
            event_slug="federal-decision", question="Test outcome?",
            yes_token_id="123456", yes_price=yes_price,
            volume_24h=300_000, liquidity=90_000, end_date="",
        )

    def test_daily_archive_is_idempotent_and_uses_actual_baseline(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "archive"
            html = Path(directory) / "site" / "index.html"
            first = run_daily(archive, html, now=self.BASE_TIME,
                              discover=lambda **_: ([self.market(0.40)], 5))
            self.assertEqual(first["new_signals"], 0)
            self.assertEqual(len(list(archive.glob("*.json"))), 1)

            second = run_daily(archive, html, now=self.BASE_TIME + 86400,
                               discover=lambda **_: ([self.market(0.61)], 5))
            self.assertEqual(second["new_signals"], 1)
            self.assertEqual(second["signals"][0]["window_hours"], 24)
            self.assertAlmostEqual(second["signals"][0]["change_pp"], 21)
            self.assertEqual(len(list(archive.glob("*.json"))), 2)

            def no_fetch(**_):
                raise AssertionError("A retry must use immutable archived observations")

            retry = run_daily(archive, html, now=self.BASE_TIME + 86400,
                              discover=no_fetch)
            self.assertTrue(retry["reused_existing_snapshot"])
            self.assertEqual(retry["new_signals"], 1)
            self.assertIn("Daily market briefing", html.read_text(encoding="utf-8"))
            latest = json.loads((html.parent / "latest.json").read_text(encoding="utf-8"))
            self.assertEqual(latest["markets_observed"], 1)

    def test_skipped_day_shows_real_elapsed_interval(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "archive"
            html = Path(directory) / "site" / "index.html"
            run_daily(archive, html, now=self.BASE_TIME,
                      discover=lambda **_: ([self.market(0.40)], 5))
            result = run_daily(archive, html, now=self.BASE_TIME + 2 * 86400,
                               discover=lambda **_: ([self.market(0.61)], 5))
            self.assertEqual(result["new_signals"], 1)
            self.assertEqual(result["signals"][0]["window_hours"], 48)

    def test_empty_source_never_writes_an_archive(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "archive"
            html = Path(directory) / "site" / "index.html"
            with self.assertRaises(GammaError):
                run_daily(archive, html, now=self.BASE_TIME,
                          discover=lambda **_: ([], 0))
            self.assertEqual(list(archive.glob("*.json")), [])


if __name__ == "__main__":
    unittest.main()
