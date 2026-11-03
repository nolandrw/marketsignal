"""No-network contract and adversarial tests for public source adapters."""

import unittest

from marketsignal.agent_sources import (
    BlueskySearch, GDELTSearch, PolymarketHistory, PublicJSONTransport,
    SourceError,
)


class FakeTransport:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def get(self, url, params):
        self.calls.append((url, params))
        return self.response


class SourceAdapterTests(unittest.TestCase):
    def test_public_transport_rejects_arbitrary_and_credentials_urls(self):
        fetcher = PublicJSONTransport()
        for url in ("http://public.api.bsky.app/xrpc/foo",
                    "https://evil.example/steal",
                    "https://user:password@public.api.bsky.app/xrpc/foo",
                    "https://public.api.bsky.app:9443/xrpc/foo"):
            with self.subTest(url=url), self.assertRaises(SourceError):
                fetcher.get(url, {"q": "test"})

    def test_valid_clob_history_is_filtered_and_sorted(self):
        fake = FakeTransport({"history": [
            {"t": 110, "p": "0.50"}, {"t": 100, "p": "0.30"},
            {"t": 999, "p": "0.80"}, {"t": 105, "p": "nan"},
            {"t": 108, "p": "1.3"}, {"t": "oops", "p": "0.1"},
        ]})
        prices = PolymarketHistory(fake).between("12345678901234567890", 100, 120)
        self.assertEqual([p.timestamp for p in prices], [100, 110])
        self.assertEqual(prices[1].yes_price, 0.50)
        self.assertEqual(fake.calls[0][1]["startTs"], 100)

    def test_clob_rejects_unbounded_or_invalid_tokens(self):
        fetcher = PolymarketHistory(FakeTransport({"history": []}))
        with self.assertRaises(ValueError):
            fetcher.between("../../secret", 100, 200)
        with self.assertRaises(ValueError):
            fetcher.between("12345678901234567890", 100, 100 + 10 * 86400)

    def test_history_duplicate_timestamp_is_deduplicated(self):
        fake = FakeTransport({"history": [
            {"t": 100, "p": "0.30"}, {"t": 100, "p": "0.31"},
            {"t": 110, "p": "0.40"},
        ]})
        hits = PolymarketHistory(fake).between("12345678901234567890", 100, 120)
        self.assertEqual(len(hits), 2)

    def test_bluesky_parses_public_posts_and_rejects_bad_timestamps(self):
        fake = FakeTransport({"posts": [
            {"uri": "at://did:plc:a/app.bsky.feed.post/3abc123",
             "author": {"handle": "news.bsky.social", "did": "did:plc:a"},
             "record": {"createdAt": "2026-11-03T12:00:00Z", "text": "A market moved"}},
            {"uri": "at://did:plc:b/app.bsky.feed.post/3abc222",
             "author": {"handle": "bad user", "did": "did:plc:b"},
             "record": {"createdAt": "2026-11-03T12:00:00Z", "text": "malformed"}},
        ]})
        start, end = 1793700000, 1793720000
        hits = BlueskySearch(fake).search("market moved", start, end, 5)
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].platform, "bluesky")
        self.assertTrue(hits[0].url.startswith("https://bsky.app/profile/"))
        self.assertEqual(fake.calls[0][1]["limit"], 5)

    def test_gdelt_only_uses_bounded_https_news_leads(self):
        fake = FakeTransport({"articles": [
            {"url": "https://example.com/report", "title": "Company update",
             "seendate": "20261103T120000Z", "domain": "example.com"},
            {"url": "http://internal.example/secret", "title": "Bad link",
             "seendate": "20261103T120000Z"},
        ]})
        hits = GDELTSearch(fake).search("company update", 1793700000, 1793720000)
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].platform, "gdelt")
        self.assertEqual(fake.calls[0][1]["mode"], "artlist")

    def test_malformed_source_payload_is_fail_closed(self):
        with self.assertRaises(SourceError):
            BlueskySearch(FakeTransport({"posts": "bad"})).search("market", 100, 200)
        with self.assertRaises(SourceError):
            GDELTSearch(FakeTransport({"articles": None})).search("market", 100, 200)


if __name__ == "__main__":
    unittest.main()
