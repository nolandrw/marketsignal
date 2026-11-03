import unittest

from marketsignal.agent_sources import PolymarketComments
from marketsignal.kalshi import KalshiDiscovery, parse_kalshi_market


class FakeTransport:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def get(self, url, params):
        self.calls.append((url, params))
        return self.payload


class SourceV3Tests(unittest.TestCase):
    def test_comments_are_unverified_hypothesis_seeds(self):
        now = 1800000000
        rows = [
            {"id": "1", "createdAt": now - 30, "userAddress": "abc",
             "body": "This new filing may change the approval schedule"},
            {"id": "2", "createdAt": now - 90, "userAddress": "abc",
             "body": "Can anyone find the official order?"},
            {"id": "3", "createdAt": now - 100000, "userAddress": "xyz",
             "body": "This old rumor should not count"},
        ]
        transport = FakeTransport(rows)
        pulse = PolymarketComments(transport).pulse("12", "some-event", now)
        self.assertEqual(pulse.recent_comments_24h, 2)
        self.assertEqual(pulse.distinct_recent_accounts, 1)
        self.assertEqual(pulse.evidence_grade, "unverified_discussion_only")
        self.assertTrue(all(lead.platform.endswith("unverified") for lead in pulse.theory_leads))
        self.assertNotIn("abc", str(pulse))

    def test_comment_lookup_rejects_unsafe_ids(self):
        with self.assertRaises(ValueError):
            PolymarketComments(FakeTransport([])).pulse("11/../../", "event", 10000)

    def test_kalshi_adapter_preserves_contract_volume_unit(self):
        raw = {"ticker": "TEST-YES", "event_ticker": "TEST-EVENT", "title": "Test event",
               "yes_bid_dollars": "0.42", "yes_ask_dollars": "0.46",
               "volume_24h_fp": "12000", "liquidity_dollars": "24000"}
        quote = parse_kalshi_market(raw)
        self.assertAlmostEqual(quote.midpoint_yes, .44)
        self.assertEqual(quote.volume_24h_contracts, 12000)
        self.assertEqual(quote.price_basis, "kalshi_yes_bid_ask_midpoint")
        transport = FakeTransport({"markets": [raw], "cursor": ""})
        self.assertEqual(len(KalshiDiscovery(transport).sample()), 1)

    def test_kalshi_rejects_broken_books_and_guessed_quotes(self):
        raw = {"ticker": "ABC", "event_ticker": "DEF", "yes_bid_dollars": "0.80",
               "yes_ask_dollars": "0.20", "volume_24h_fp": "100",
               "liquidity_dollars": "500"}
        self.assertIsNone(parse_kalshi_market(raw))
        del raw["yes_bid_dollars"]
        raw["last_price_dollars"] = "0.40"
        self.assertIsNone(parse_kalshi_market(raw))


if __name__ == "__main__":
    unittest.main()
