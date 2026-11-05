"""Offline evidence, gate and disclosure tests for the lightweight brief lane."""

import copy
import unittest
from pathlib import Path

from marketsignal.agent_sources import SourceLead
from marketsignal.brief_pilot import (
    MAX_CASES, SOURCE_MARKET, _manuscript_issues, _short_query, run_brief,
    select_movers, select_quiet_candidates, probe_quiet_attention,
    review_release_redundancy,
)
from marketsignal.model_gateway import STAGE_INSTRUCTIONS, STAGE_SCHEMAS


ARCHIVE = Path(__file__).resolve().parents[1] / "data" / "archive"


class FakeSearch:
    def __init__(self, leads):
        self.leads = leads
        self.queries = []

    def search(self, query, since, until, limit=8):
        self.queries.append(query)
        return tuple(self.leads)


class FakeModel:
    def __init__(self, *, editor_score=65, bad_first_draft=False, bad_check=False,
                 duplicate_pair=None, broken_release=False):
        self.stages = []
        self.editor_score = editor_score
        self.bad_first_draft = bad_first_draft
        self.bad_check = bad_check
        self.drafts = 0
        self.duplicate_pair = duplicate_pair
        self.broken_release = broken_release

    def complete(self, stage, packet):
        self.stages.append(stage)
        if stage == "brief_scout":
            return {"reader_question": "What is changing in regional policy?",
                    "possible_connection": "Related coverage may provide context, not causation",
                    "search_queries": ["Iran ceasefire negotiations 2026"]}
        if stage == "brief_editor":
            return {"decision": "go", "headline": "New diplomatic coverage frames a changing policy debate",
                    "reader_value": "Understand what publishers are discussing",
                    "reader_value_score": self.editor_score,
                    "selected_source_ids": ["coverage_1"]}
        if stage == "brief_writer":
            self.drafts += 1
            market_id = SOURCE_MARKET if not (self.bad_first_draft and self.drafts == 1) else "fake_source"
            text = (
                "The policy question is receiving renewed attention from readers. "
                "The comparison uses two real observations of the same contract, "
                "which can move for reasons unrelated to the underlying outcome. "
                "It should be read as a market quote, not as a calibrated forecast. "
                "The observation does not establish any cause or event."
            )
            coverage = (
                "Example News published a headline about ceasefire discussions, "
                "although the headline alone cannot establish whether the talks "
                "succeeded or how officials interpreted the situation. Readers "
                "should consult the linked original article to understand its "
                "evidence. This brief is only a map of what is being covered."
            )
            connection = (
                "The juxtaposition of an active contract and that headline makes "
                "the topic worth watching, but it is a connection in subject matter, "
                "not a demonstration that the reporting changed traders' minds. "
                "A market can also move with thin liquidity, changing participation, "
                "or developments that were not present in the coverage index."
            )
            return {"headline": "New diplomatic coverage frames a changing policy debate",
                    "deck": "Dated contract movements alongside attributed coverage titles",
                    "paragraphs": [
                        {"text": text, "claim_type": "market_observation", "source_ids": [market_id]},
                        {"text": coverage, "claim_type": "attributed_coverage", "source_ids": ["coverage_1"]},
                        {"text": connection, "claim_type": "interpretation",
                         "source_ids": [SOURCE_MARKET, "coverage_1"]},
                    ]}
        if stage == "brief_factcheck":
            return {"reviews": [{"paragraph_index": i,
                                 "verdict": "revise" if self.bad_check else "supported",
                                 "issues": ["Review required"] if self.bad_check else []}
                                for i in range(len(packet["article"]["paragraphs"]))],
                    "article_issues": []}
        if stage == "brief_release_editor":
            if self.broken_release:
                return {"reviews": []}
            return {"reviews": [
                {"market_id": d["market_id"],
                 "duplicate_of": (self.duplicate_pair[0] if self.duplicate_pair and
                                  d["market_id"] == self.duplicate_pair[1] else ""),
                 "reason": "Same news peg" if self.duplicate_pair else "Distinct news peg"}
                for d in packet["drafts"]]}
        raise AssertionError(f"Unknown test stage: {stage}")


class WindowedSearch:
    def __init__(self, *, recent_count=8, prior_count=1, publisher_count=5,
                 syndicated=False):
        self.recent_count = recent_count
        self.prior_count = prior_count
        self.publisher_count = publisher_count
        self.syndicated = syndicated
        self.calls = 0

    def search(self, query, since, until, limit=12):
        self.calls += 1
        is_recent = self.calls % 2 == 1
        count = self.recent_count if is_recent else self.prior_count
        return tuple(SourceLead("offline", f"https://example.org/story-{self.calls}-{i}",
                                (f"A public report on {query}" if self.syndicated else
                                 f"A public report on {query} number {i}"), until - 60,
                                f"Publisher {i % self.publisher_count}")
                     for i in range(count))


class BriefPilotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.movers = select_movers(ARCHIVE / "2026-11-03.json",
                                  ARCHIVE / "2026-11-04.json")

    def test_real_market_selection_from_adjacent_archives(self):
        self.assertEqual(len(self.movers), MAX_CASES)
        self.assertEqual(len({m.market.market_id for m in self.movers}), MAX_CASES)
        self.assertEqual(self.movers[0].market.market_id, "1450214")
        for movement in self.movers:
            self.assertGreaterEqual(abs(movement.delta_pp), 1)
            self.assertGreaterEqual(movement.market.liquidity, 25_000)
            self.assertGreaterEqual(movement.market.volume_24h, 50_000)
            self.assertTrue(movement.market.source_url.startswith("https://"))
            self.assertGreater(movement.observed_at, movement.baseline_at)

    def test_real_selection_bounds(self):
        with self.assertRaises(ValueError):
            select_movers(ARCHIVE / "2026-11-03.json",
                          ARCHIVE / "2026-11-04.json", maximum=20)
        with self.assertRaises(ValueError):
            select_movers(ARCHIVE / "2026-11-04.json",
                          ARCHIVE / "2026-11-03.json")

    def test_concise_queries_prevent_previous_gdelt_validation_error(self):
        self.assertLessEqual(len(_short_query("market policy " * 20)), 110)
        self.assertEqual(_short_query("tiny"), "")

    def test_all_new_model_stages_are_registered(self):
        for stage in ("brief_scout", "brief_editor", "brief_writer", "brief_factcheck",
                      "brief_release_editor"):
            self.assertIn(stage, STAGE_SCHEMAS)
            self.assertIn(stage, STAGE_INSTRUCTIONS)

    def test_full_stage_gates_release_only_unpublished_draft(self):
        mover = self.movers[1]
        search = FakeSearch([SourceLead("gdelt", "https://examplenews.org/2026/story",
                                        "Ceasefire discussions continue this week",
                                        mover.observed_at - 3600, "Example News")])
        model = FakeModel()
        result = run_brief(mover, model, search)
        self.assertEqual(result["status"], "shadow_brief_ready_unpublished")
        self.assertEqual(model.stages, ["brief_scout", "brief_editor", "brief_writer", "brief_factcheck"])
        self.assertEqual([x["stage"] for x in result["stage_trace"]], [
            "brief_scout", "coverage_discovery", "brief_editor", "brief_writer",
            "brief_contract", "brief_factcheck", "brief_factcheck_gate", "release"])
        self.assertEqual(result["article"]["status"], "UNPUBLISHED_CURATION_BRIEF")
        self.assertFalse(result["publication_enabled"])
        self.assertFalse(result["human_factcheck_attested"])
        self.assertEqual(result["source_depth"], "market_data_and_unverified_headline_metadata")
        self.assertEqual(len(search.queries), 1)
        self.assertEqual(len(result["external_leads"]), 1)

    def test_bad_first_draft_gets_one_repair_pass(self):
        mover = self.movers[1]
        search = FakeSearch([SourceLead("gdelt", "https://examplenews.org/story",
                                        "Ceasefire discussions continue this week",
                                        mover.observed_at - 60, "Example News")])
        model = FakeModel(bad_first_draft=True)
        result = run_brief(mover, model, search)
        self.assertEqual(result["status"], "shadow_brief_ready_unpublished")
        self.assertEqual(model.drafts, 2)
        self.assertTrue(any(r["stage"] == "brief_contract" and r["status"] == "rejected"
                            for r in result["stage_trace"]))

    def test_editor_score_below_new_bar_holds(self):
        mover = self.movers[1]
        search = FakeSearch([SourceLead("gdelt", "https://examplenews.org/story",
                                        "Ceasefire discussions continue this week",
                                        mover.observed_at - 60, "Example News")])
        model = FakeModel(editor_score=49)
        result = run_brief(mover, model, search)
        self.assertEqual(result["status"], "held_editor")
        self.assertEqual(len(model.stages), 2)
        self.assertIsNone(result["article"])

    def test_no_verified_headline_leads_holds_without_writer(self):
        mover = self.movers[1]
        search = FakeSearch([SourceLead("gdelt", "https://examplenews.org/story",
                                        "Ceasefire discussions continue this week",
                                        mover.observed_at + 600, "Example News")])
        model = FakeModel()
        result = run_brief(mover, model, search)
        self.assertEqual(result["status"], "held_no_coverage")
        self.assertEqual(model.stages, ["brief_scout"])

    def test_negative_factcheck_does_not_mark_ready(self):
        mover = self.movers[1]
        search = FakeSearch([SourceLead("gdelt", "https://examplenews.org/story",
                                        "Ceasefire discussions continue this week",
                                        mover.observed_at - 60, "Example News")])
        model = FakeModel(bad_check=True)
        result = run_brief(mover, model, search)
        self.assertEqual(result["status"], "held_brief_review")
        self.assertFalse(result["publication_enabled"])
        self.assertEqual(result["model_calls"], 6)

    def test_contract_disallows_unknown_citations_and_no_market(self):
        valid = {"headline": "A specific, informative, restrained headline",
                 "deck": "This deck identifies a policy topic and what we can know",
                 "paragraphs": [{"text": "A long paragraph with a citation " * 15,
                                 "claim_type": "market_observation", "source_ids": ["fake"]},
                                {"text": "Coverage context that would otherwise be valid " * 10,
                                 "claim_type": "attributed_coverage", "source_ids": ["coverage_1"]},
                                {"text": "Interpretation rather than proven causation " * 12,
                                 "claim_type": "interpretation", "source_ids": ["coverage_1"]}]}
        issues = _manuscript_issues(valid, valid["headline"], {"market_snapshot", "coverage_1"})
        self.assertIn("invalid_paragraph_0", issues)
        self.assertIn("missing_market_or_external_coverage_link", issues)

    def test_quiet_news_attention_is_real_bounded_and_publisher_diverse(self):
        old, new = ARCHIVE / "2026-11-03.json", ARCHIVE / "2026-11-04.json"
        quiet = select_quiet_candidates(old, new, maximum=5)
        self.assertGreater(len(quiet), 0)
        self.assertEqual(len({m.market.event_id for m in quiet}), len(quiet))
        self.assertTrue(all(abs(m.delta_pp) < 1 for m in quiet))
        search = WindowedSearch()
        attention = probe_quiet_attention(quiet, search, maximum=1)
        self.assertEqual(len(attention), 1)
        self.assertEqual(search.calls, 2)
        self.assertEqual(attention[0].trigger, "coverage_without_price_movement")
        self.assertEqual(attention[0].coverage_attention["sampled_recent_headlines"], 8)
        self.assertTrue(attention[0].coverage_attention["sampled_not_total_media_volume"])

    def test_attention_requires_broad_relevant_growth_not_repeated_single_source(self):
        quiet = select_quiet_candidates(ARCHIVE / "2026-11-03.json",
                                        ARCHIVE / "2026-11-04.json", maximum=1)
        self.assertFalse(probe_quiet_attention(quiet, WindowedSearch(
            recent_count=8, prior_count=8), maximum=1))
        self.assertFalse(probe_quiet_attention(quiet, WindowedSearch(
            recent_count=10, prior_count=1, publisher_count=1), maximum=1))
        self.assertFalse(probe_quiet_attention(quiet, WindowedSearch(
            recent_count=10, prior_count=1, syndicated=True), maximum=1))
        self.assertFalse(probe_quiet_attention(quiet, WindowedSearch(
            recent_count=5, prior_count=0), maximum=1))
        self.assertFalse(probe_quiet_attention(quiet, WindowedSearch(), maximum=0))

    def _ready(self, market_id, event_id):
        source = self.movers[0]
        result = run_brief(source, FakeModel(), FakeSearch([
            SourceLead("offline", "https://example.org/story",
                       "A substantial diplomatic development was reported",
                       source.observed_at - 60, "Example News")]))
        result["market"] = {**result["market"], "market_id": market_id,
                            "event_id": event_id}
        return result

    def test_release_editor_suppresses_opposite_contracts_in_same_event(self):
        first = self._ready("fed-hike", "december-fed")
        second = self._ready("fed-hold", "december-fed")
        model = FakeModel()  # Deliberately misses the duplicate.
        review_release_redundancy([first, second], model)
        self.assertEqual(model.stages, ["brief_release_editor"])
        self.assertEqual(len([r for r in (first, second)
                              if r["status"] == "shadow_brief_ready_unpublished"]), 1)
        held = [r for r in (first, second) if r["status"] == "held_redundant_brief"][0]
        self.assertIn(held["duplicate_of"], {"fed-hike", "fed-hold"})
        self.assertFalse(held["publication_enabled"])
        self.assertEqual(held["stage_trace"][-1]["stage"], "brief_release_editor")

    def test_release_editor_catches_semantic_duplication_across_events(self):
        first = self._ready("a", "event-one")
        second = self._ready("b", "event-two")
        review_release_redundancy([first, second], FakeModel(duplicate_pair=("a", "b")))
        self.assertEqual(first["status"], "shadow_brief_ready_unpublished")
        self.assertEqual(second["status"], "held_redundant_brief")
        self.assertEqual(second["duplicate_of"], "a")

    def test_release_editor_bad_response_holds_all_for_manual_comparison(self):
        results = [self._ready("a", "event-one"), self._ready("b", "event-two")]
        review_release_redundancy(results, FakeModel(broken_release=True))
        self.assertEqual([r["status"] for r in results],
                         ["held_release_editor", "held_release_editor"])


if __name__ == "__main__":
    unittest.main()
