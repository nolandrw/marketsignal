"""Offline tests for the fixed-host, publication-date-filtered RSS backup."""

import unittest
from datetime import datetime, timezone
from email.utils import format_datetime

from marketsignal.agent_sources import SourceError
from marketsignal.news_rss import BING_URL, GOOGLE_URL, RSSNewsSearch


OBSERVED = 1793779200


def rss(*, published=OBSERVED - 3600, publisher="Example News",
        url="https://example.org/story", title="New discussions change the policy conversation"):
    stamp = format_datetime(datetime.fromtimestamp(published, timezone.utc))
    return (f"<rss version='2.0'><channel><item><title>{title}</title>"
            f"<link>{url}</link><pubDate>{stamp}</pubDate>"
            f"<source>{publisher}</source></item></channel></rss>").encode()


class FakeRSS:
    def __init__(self, google=None, bing=None):
        self.google = google
        self.bing = bing
        self.calls = []

    def get(self, endpoint, params):
        self.calls.append((endpoint, params))
        result = self.google if endpoint == GOOGLE_URL else self.bing
        if isinstance(result, Exception):
            raise result
        return result


class RSSNewsTests(unittest.TestCase):
    def test_google_yields_dated_attributed_coverage_without_bing(self):
        fake = FakeRSS(google=rss())
        leads = RSSNewsSearch(transport=fake).search("Iran ceasefire", OBSERVED - 30 * 86400,
                                                    OBSERVED)
        self.assertEqual(len(leads), 1)
        self.assertEqual(leads[0].author_key, "Example News")
        self.assertEqual(leads[0].platform, "google_news_rss")
        self.assertEqual(leads[0].posted_at, OBSERVED - 3600)
        self.assertEqual(len(fake.calls), 1)
        self.assertIn("before:2026-11-05", fake.calls[0][1]["q"])

    def test_fallback_to_bing_when_google_provider_blocked(self):
        fake = FakeRSS(google=SourceError("RSS provider HTTP 429"), bing=rss())
        leads = RSSNewsSearch(transport=fake).search("Iran ceasefire", OBSERVED - 30 * 86400,
                                                    OBSERVED)
        self.assertEqual(len(leads), 1)
        self.assertEqual(leads[0].platform, "bing_news_rss")
        self.assertEqual([c[0] for c in fake.calls], [GOOGLE_URL, BING_URL])

    def test_after_snapshot_and_undated_leads_cannot_be_cited(self):
        fake = FakeRSS(google=rss(published=OBSERVED + 10), bing=rss(published=OBSERVED + 10))
        leads = RSSNewsSearch(transport=fake).search("Iran ceasefire", OBSERVED - 30 * 86400,
                                                    OBSERVED)
        self.assertEqual(leads, ())
        missing_publisher = FakeRSS(google=rss(publisher=""), bing=rss(publisher=""))
        self.assertEqual(RSSNewsSearch(transport=missing_publisher).search(
            "Iran ceasefire", OBSERVED - 30 * 86400, OBSERVED), ())

    def test_doctype_and_http_lead_rejected(self):
        unsafe = b"<!DOCTYPE rss [<!ENTITY x 'unsafe'>]><rss><channel/></rss>"
        with self.assertRaises(SourceError):
            RSSNewsSearch(transport=FakeRSS(google=unsafe, bing=unsafe)).search(
                "Iran ceasefire", OBSERVED - 30 * 86400, OBSERVED)
        self.assertEqual(RSSNewsSearch(transport=FakeRSS(
            google=rss(url="http://example.org/unsafe"),
            bing=rss(url="http://example.org/unsafe"))).search(
                "Iran ceasefire", OBSERVED - 30 * 86400, OBSERVED), ())

    def test_request_budgets(self):
        fake = FakeRSS(google=rss())
        source = RSSNewsSearch(transport=fake)
        for query in ("too", "x" * 111, "bad\nquery"):
            with self.assertRaises(ValueError):
                source.search(query, OBSERVED - 30 * 86400, OBSERVED)
        with self.assertRaises(ValueError):
            source.search("Iran ceasefire", OBSERVED - 32 * 86400, OBSERVED)
        self.assertEqual(fake.calls, [])


if __name__ == "__main__":
    unittest.main()
