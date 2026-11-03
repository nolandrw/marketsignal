"""Context discovery is bounded, date-aware and never treated as proof."""

from dataclasses import asdict, replace
import json
from pathlib import Path
import tempfile
import unittest

from marketsignal.agent_sources import SourceLead
from marketsignal.context_discovery import ContextDiscoveryAgent, discover_archive
from marketsignal.feature_demo import fictional_feature_fixture


class MockNews:
    def __init__(self, fail=False):
        self.calls = []
        self.fail = fail

    def search(self, query, since, until, limit=20):
        self.calls.append((query, since, until, limit))
        if self.fail:
            raise ValueError("secret provider URL")
        return (SourceLead("gdelt", f"https://example.org/article/{len(self.calls)}",
                           "Crescent Bay engineering news", since + 100,
                           f"independent-{len(self.calls)}"),)


class ContextDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.candidate, self.dossier = fictional_feature_fixture()

    def test_three_searches_include_preexisting_baseline_and_longer_history(self):
        source = MockNews()
        result = ContextDiscoveryAgent(source).discover(self.candidate)
        self.assertEqual(len(source.calls), 3)
        self.assertEqual(len(result.leads), 3)
        self.assertEqual(result.leads[0].role, "prior_reporting")
        self.assertEqual(result.leads[1].role, "contemporaneous_reporting")
        self.assertEqual(result.leads[2].role, "broader_stakes_search")
        self.assertFalse(result.independent_claims_verified)
        self.assertTrue(all(lead.factual_status == "discovery_only" for lead in result.leads))
        self.assertLess(source.calls[0][2], source.calls[1][2])

    def test_failed_api_cannot_become_a_causal_claim(self):
        result = ContextDiscoveryAgent(MockNews(fail=True)).discover(self.candidate)
        self.assertEqual(len(result.leads), 0)
        self.assertEqual(len(result.source_errors), 3)
        self.assertNotIn("secret", str(result))

    def test_bad_signal_skips_all_searches(self):
        source = MockNews()
        corrupted = replace(self.candidate, signal=replace(self.candidate.signal,
                                                           change_pp=1.0))
        result = ContextDiscoveryAgent(source).discover(corrupted)
        self.assertEqual(len(source.calls), 0)
        self.assertEqual(result.source_errors, ("invalid_signal",))

    def test_archive_artifact_retains_only_metrics(self):
        source = MockNews()
        record = {"schema_version": 1, "markets": [asdict(self.candidate.market)],
                  "signals": [asdict(self.candidate.signal)]}
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "daily.json"
            path.write_text(json.dumps(record), encoding="utf-8")
            result = discover_archive(path, source)
        self.assertEqual(result["results"][0]["discovery_leads"], 3)
        self.assertFalse(result["publication_enabled"])
        self.assertNotIn("https://", str(result))
        self.assertNotIn("Crescent Bay engineering news", str(result))


if __name__ == "__main__":
    unittest.main()
