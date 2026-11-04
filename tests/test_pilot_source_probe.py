"""The source readiness probe must neither spend nor promote snippets."""

import unittest

from marketsignal.source_capture import FetchedDocument, HostPermission, SourceCaptureGateway
from scripts.probe_pilot_sources import inspect


URL = "https://official.example.org/record"


class FakeTransport:
    def __init__(self, page, robots="User-agent: *\nAllow: /"):
        self.page = page
        self.robots = robots
        self.urls = []

    def get(self, url, *, max_bytes, media):
        self.urls.append(url)
        return self.robots if url.endswith("robots.txt") else self.page

    def fetch_document(self, url, *, max_bytes):
        self.urls.append(url)
        return FetchedDocument(self.page.encode(), "text/html")


def gateway(page, robots="User-agent: *\nAllow: /"):
    fake = FakeTransport(page, robots)
    return SourceCaptureGateway((HostPermission("official.example.org", "official_record",
                                                "official_public_record"),), fake), fake


class SourceProbeTests(unittest.TestCase):
    def test_dated_original_page_is_shape_ready_not_captured(self):
        paragraph = "The agency published the outcome of its formal record review with supporting facts. " * 2
        html = ('<html><head><meta property="article:published_time" '
                'content="2026-10-28T12:00:00Z"></head><main>'
                f'<p>{paragraph}</p><p>{paragraph}</p></main></html>')
        checker, fake = gateway(html)
        result = inspect("test", URL, checker)
        self.assertEqual(result["status"], "potentially_capturable")
        self.assertFalse(result["full_source_capture_performed"])
        self.assertEqual(len(fake.urls), 2)

    def test_undated_page_is_hold(self):
        checker, _ = gateway('<main><p>Official source lacks a date.</p></main>')
        self.assertEqual(inspect("test", URL, checker)["status"], "date_metadata_hold")

    def test_robots_deny_never_requests_page(self):
        checker, fake = gateway("<main>Material</main>", "User-agent: *\nDisallow: /")
        self.assertEqual(inspect("test", URL, checker)["status"], "retrieval_hold")
        self.assertEqual(fake.urls, ["https://official.example.org/robots.txt"])


if __name__ == "__main__":
    unittest.main()
