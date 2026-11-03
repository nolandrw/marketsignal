import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from marketsignal.gamma import discover_markets, parse_market


class GammaParsingTests(unittest.TestCase):
    def setUp(self):
        self.event = {"id": "7", "title": "Example", "slug": "example-event", "category": "Politics"}
        self.market = {
            "id": "11", "question": "Will the policy pass?", "active": True, "closed": False,
            "outcomes": '["No", "Yes"]', "outcomePrices": '["0.6", "0.4"]',
            "clobTokenIds": '["123456", "999999"]', "volume24hr": 120000,
            "liquidityNum": 51000, "endDate": "2030-12-31T00:00:00Z",
        }

    def test_selects_yes_outcome_by_label(self):
        parsed = parse_market(self.event, self.market, now=datetime(2026, 11, 3, tzinfo=timezone.utc))
        self.assertIsNotNone(parsed)
        self.assertAlmostEqual(parsed.yes_price, 0.4)
        self.assertEqual(parsed.yes_token_id, "999999")

    def test_excludes_closed_and_sports(self):
        self.market["closed"] = True
        self.assertIsNone(parse_market(self.event, self.market))
        self.market["closed"] = False
        self.event["tags"] = [{"label": "Sports"}]
        self.assertIsNone(parse_market(self.event, self.market))

    def test_missing_quotes_are_not_zero(self):
        self.market["outcomePrices"] = None
        self.assertIsNone(parse_market(self.event, self.market))

    def test_expired_market_is_ignored(self):
        self.market["endDate"] = "2020-01-01T00:00:00Z"
        self.assertIsNone(parse_market(self.event, self.market))

    def test_discovery_caps_per_event(self):
        event = dict(self.event)
        event["markets"] = [dict(self.market, id=str(i), volume24hr=60000 + i)
                            for i in range(10, 15)]
        with patch("marketsignal.gamma._fetch_json", return_value={"events": [event]}):
            markets, events = discover_markets(max_markets=10, max_pages=1)
        self.assertEqual(events, 1)
        self.assertEqual(len(markets), 3)
        self.assertEqual(markets[0].market_id, "14")

    def test_discovery_excludes_combinatorial_event(self):
        event = dict(self.event, title="Build Your Map", markets=[self.market])
        with patch("marketsignal.gamma._fetch_json", return_value={"events": [event]}):
            markets, _ = discover_markets(max_markets=10, max_pages=1)
        self.assertEqual(markets, [])


if __name__ == "__main__":
    unittest.main()
