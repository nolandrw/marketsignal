"""Golden synthetic research handoff scenarios; no network calls."""

import unittest
import json
import tempfile
from dataclasses import replace
from dataclasses import asdict
from pathlib import Path

from marketsignal.agent_sources import PricePoint, SourceLead
from marketsignal.editorial import Candidate
from marketsignal.investigation import NarrativeScout, search_terms
from marketsignal.newsroom import ShadowNewsroom, replay_archive, safe_report
from test_editorial import sample_candidate


class History:
    def between(self, token_id, since, until):
        return (
            PricePoint(since + 3600, .35),
            PricePoint(since + 7200, .36),
            PricePoint(since + 10800, .54),
            PricePoint(since + 14400, .54),
        )


class Search:
    def __init__(self, platform, fail=False):
        self.platform = platform
        self.fail = fail
        self.calls = 0

    def search(self, query, since, until, limit=20):
        self.calls += 1
        if self.fail:
            raise RuntimeError("private key should never leak")
        return (
            SourceLead(self.platform, "https://bsky.app/profile/a/post/1",
                       "Atlas launch possible delay unverified", since + 600, "author-a"),
            SourceLead(self.platform, "https://bsky.app/profile/a/post/1",
                       "Atlas launch possible delay unverified", since + 600, "author-a"),
            SourceLead(self.platform, "https://bsky.app/profile/b/post/2",
                       "Atlas launch public filing", since + 900, "author-b"),
            SourceLead(self.platform, "https://bsky.app/profile/c/post/3",
                       "Unrelated gardening discussion", since + 400, "author-c"),
        )


class InvestigationTests(unittest.TestCase):
    def test_query_is_bounded_and_semantically_relevant(self):
        self.assertEqual(search_terms("Will Atlas launch by December 31?"),
                         "atlas launch december 31")

    def test_movement_window_and_unverified_hypotheses(self):
        scout = NarrativeScout(History(), Search("bluesky"), Search("gdelt"))
        c = sample_candidate()
        result = scout.investigate(c)
        self.assertEqual(result.move_window.confidence, "sampled_interval")
        self.assertEqual(result.move_window.start_at, c.signal.baseline_at + 7200)
        self.assertEqual(result.social_observations, 4)
        self.assertEqual(len(result.hypotheses), 2)
        self.assertTrue(all(item.factual_status == "unverified" for item in result.hypotheses))
        self.assertEqual(result.publication_rights, "SHADOW_ONLY")

    def test_source_failures_do_not_produce_invented_catalyst(self):
        scout = NarrativeScout(History(), Search("bluesky", fail=True), Search("gdelt", fail=True))
        packet = scout.investigate(sample_candidate())
        self.assertFalse(packet.hypotheses)
        self.assertEqual(len(packet.source_errors), 2)
        self.assertNotIn("private key", str(packet))

    def test_live_candidate_is_held_and_never_published(self):
        scout = NarrativeScout(History(), Search("bluesky"), Search("gdelt"))
        candidate = sample_candidate()
        live = Candidate(candidate.market, candidate.signal)
        result = ShadowNewsroom(scout).run(live)
        self.assertEqual(result.outcome, "held")
        self.assertFalse(result.publication_enabled)
        self.assertEqual(result.research.candidate_id, live.candidate_id)
        public = safe_report([result])
        self.assertNotIn("possible delay", str(public))
        self.assertFalse(public["publication_enabled"])

    def test_bad_quote_stops_before_external_search(self):
        social = Search("bluesky")
        scout = NarrativeScout(History(), social, Search("gdelt"))
        candidate = sample_candidate()
        corrupted = replace(candidate, signal=replace(candidate.signal, change_pp=90.0))
        result = ShadowNewsroom(scout).run(corrupted)
        self.assertEqual(result.outcome, "held")
        self.assertEqual(social.calls, 0)
        self.assertIsNone(result.research)

    def test_unexpected_scout_exception_holds_without_message_leak(self):
        class CrashingScout:
            def investigate(self, candidate):
                raise RuntimeError("SECRET_SOURCE_HEADER")

        result = ShadowNewsroom(CrashingScout()).run(sample_candidate())
        self.assertEqual(result.outcome, "held")
        self.assertIn("research_failure:RuntimeError", result.stages)
        self.assertNotIn("SECRET", str(safe_report([result])))

    def test_wrong_research_candidate_id_cannot_cross_handoff(self):
        class InvalidScout:
            def investigate(self, candidate):
                from marketsignal.investigation import ResearchPacket, MoveWindow
                return ResearchPacket(
                    1, "wrong-candidate", MoveWindow(10, 20, "sparse_history", "test"),
                    "test", 0, 0, (), (), (), "not verified"
                )

        result = ShadowNewsroom(InvalidScout()).run(sample_candidate())
        self.assertEqual(result.outcome, "held")
        self.assertIn("research_id_mismatch", result.stages)

    def test_archive_replay_no_signals_never_calls_public_sources(self):
        social = Search("bluesky")
        scout = NarrativeScout(History(), social, Search("gdelt"))
        with tempfile.TemporaryDirectory() as tmp:
            file = Path(tmp) / "daily.json"
            file.write_text(json.dumps({"schema_version": 1, "markets": [],
                                        "signals": []}), encoding="utf-8")
            result = replay_archive(file, scout)
        self.assertEqual(result, [])
        self.assertEqual(social.calls, 0)

    def test_archive_replay_real_signal_defaults_to_hold(self):
        c = sample_candidate()
        with tempfile.TemporaryDirectory() as tmp:
            file = Path(tmp) / "daily.json"
            file.write_text(json.dumps({
                "schema_version": 1, "markets": [asdict(c.market)],
                "signals": [asdict(c.signal)],
            }), encoding="utf-8")
            results = replay_archive(
                file, NarrativeScout(History(), Search("bluesky"), Search("gdelt"))
            )
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].outcome, "held")
        self.assertIn("risk_classification_requires_review",
                      results[0].editorial.reasons)


if __name__ == "__main__":
    unittest.main()
