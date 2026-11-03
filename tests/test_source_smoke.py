import json
import tempfile
import unittest
from pathlib import Path

from marketsignal.source_smoke import probe_sources


class FixtureTransport:
    def __init__(self):
        self.calls = []

    def get(self, url, params):
        self.calls.append(url)
        if "searchPosts" in url:
            return {"posts": []}
        if "gdeltproject" in url:
            return {"articles": []}
        return {"history": []}


class SourceSmokeTests(unittest.TestCase):
    def test_without_archive_skips_history_and_never_retains_content(self):
        with tempfile.TemporaryDirectory() as directory:
            transport = FixtureTransport()
            packet = probe_sources(directory, now=1_800_000_000, transport=transport)
        self.assertEqual(packet["sources"]["polymarket_history"]["status"], "skipped")
        self.assertEqual(len(transport.calls), 2)
        self.assertFalse(packet["publication_enabled"])
        self.assertFalse(packet["contents_retained"])

    def test_with_archive_uses_history_but_only_reports_counts(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "2026-11-03.json"
            archive.write_text(json.dumps({
                "markets": [{"yes_token_id": "12345678901234567890"}]
            }), encoding="utf-8")
            transport = FixtureTransport()
            packet = probe_sources(directory, now=1_800_000_000, transport=transport)
        self.assertEqual(len(transport.calls), 3)
        self.assertEqual(packet["sources"]["polymarket_history"]["status"], "ok")
        self.assertNotIn("12345678901234567890", str(packet))


if __name__ == "__main__":
    unittest.main()
