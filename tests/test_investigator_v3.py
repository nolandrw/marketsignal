"""Offline adversarial Investigator v3 cases; they do not test real journalism."""

import copy
import unittest
from dataclasses import replace
from types import SimpleNamespace

from marketsignal.investigator_v3 import (
    COMPLETED_CRITERIA, PRELIMINARY_CRITERIA, InvestigatorAssignment,
    InvestigatorV3, ResearchCapture, assignment_from_topic_lead, validate_scorecard,
)
from marketsignal.model_gateway import STAGE_INSTRUCTIONS, STAGE_SCHEMAS


NOW = 1_800_000_000


def source(source_id, kind="official_record", origin=None, *, captured_at=NOW - 100,
           publisher=None, text=None):
    return ResearchCapture(source_id=source_id, url=f"https://fictional.example/{source_id}",
                           publisher=publisher or source_id, origin_key=origin or source_id,
                           published_at=NOW - 10_000, captured_at=captured_at,
                           source_kind=kind,
                           excerpt=text or ("Fictional city records describe an engineering review "
                                            "before a planned flood defense milestone."))


def assignment(**kwargs):
    return InvestigatorAssignment(case_id="fictional_barrier", as_of=NOW,
                                  topic="Fictional coast flood-barrier vote",
                                  topic_lead_angle="Engineering findings delay vote",
                                  topic_lead_disposition=kwargs.pop("topic_lead_disposition", "go"),
                                  topic_lead_score=kwargs.pop("topic_lead_score", 82),
                                  coverage_summary="Prior news covered the proposal but not the new review",
                                  seed_sources=kwargs.pop("seed_sources", (source("seed_record"),)),
                                  **kwargs)


def scores(weights, evidence="seed_record", *, partial=(), none=()):
    return {name: {"grade": "none" if name in none else "partial" if name in partial else "full",
                   "rationale": "Supported by captured source and documented research planning.",
                   "evidence_refs": [evidence]}
            for name in weights}


def dossier():
    return {
        "disposition": "ready_for_verifier", "reason": "Provisional sources support a real story",
        "departure_type": "original", "departure_reason": "",
        "prior_coverage_context": "Earlier reporting described the barrier, and current records document the vote delay.",
        "findings": [
            {"claim_id": "claim_new", "statement": "City records record a delay in the coastal barrier decision.",
             "source_ids": ["seed_record"], "certainty": "reported"},
            {"claim_id": "claim_context", "statement": "Independent reporting establishes the preceding public timetable.",
             "source_ids": ["initial_report"], "certainty": "reported"},
            {"claim_id": "claim_counter", "statement": "The engineering memorandum says no safety failure has been established.",
             "source_ids": ["deep_record"], "certainty": "reported"},
        ],
        "timeline": [
            {"at": NOW - 9000, "event": "Public timetable was announced", "claim_ids": ["claim_context"]},
            {"at": NOW - 6000, "event": "Engineering review postponed the vote", "claim_ids": ["claim_new"]},
        ],
        "hypotheses": [{"theory": "The review may affect the approval schedule",
                        "test": "Compare the meeting docket and new engineering report with the previous schedule",
                        "supporting_claim_ids": ["claim_new", "claim_context"],
                        "counter_claim_ids": ["claim_counter"]}],
        "pitches": [{"pitch_id": "flood_story", "working_headline": "Coastal Barrier Vote Delayed After Engineering Review",
                     "thesis": "The review has altered the city's previously announced plan",
                     "conflict": "Officials and engineers disagree on the decision timetable",
                     "surprise": "A previously announced vote was moved",
                     "why_now": "The decision had been expected this week",
                     "stakes": "Residents and city planners face a delayed decision",
                     "reader_value": "Document comparison clarifies the timeline for readers",
                     "supporting_claim_ids": ["claim_new", "claim_context"],
                     "contrary_claim_ids": ["claim_counter"]}],
        "open_questions": ["Does the review change costs or the long-term plan?"],
        "scores": scores(COMPLETED_CRITERIA),
    }


class ScriptedResearch:
    def __init__(self, scenario):
        self.scenario = scenario
        self.calls = []

    def search(self, query, *, as_of, limit):
        self.calls.append((query, as_of, limit))
        if "primary record" in query:
            if self.scenario == "no_credible_sources":
                return (source("initial_comment", "market_comment"),)
            if self.scenario == "future_capture":
                return (source("initial_report", "independent_reporting", captured_at=NOW + 300),)
            if self.scenario == "source_collision":
                return (source("seed_record", "independent_reporting", origin="other"),)
            if self.scenario == "duplicate_origins":
                return (source("initial_report", "independent_reporting", origin="same"),)
            return (source("initial_report", "independent_reporting"),)
        if "engineering review" in query:
            if self.scenario == "no_credible_sources":
                return (source("deep_comment", "social_comment"),)
            if self.scenario == "duplicate_origins":
                return (source("deep_record", "official_record", origin="same"),)
            if self.scenario == "no_deep_results":
                return ()
            return (source("deep_record", "original_research"),)
        return ()


class ScriptedModel:
    def __init__(self, scenario):
        self.scenario = scenario
        self.calls = []

    def complete(self, stage, payload):
        self.calls.append(stage)
        if stage == "investigator_plan_v3":
            result = {"research_goal": "Test the flood barrier decision chronology",
                      "queries": ["primary record about fictional flood barrier"]}
            if self.scenario == "extra_queries":
                result["queries"] = [f"primary record {i} about project" for i in range(4)]
            if self.scenario == "duplicate_queries":
                result["queries"] *= 2
            return result
        if stage == "investigator_preliminary_v3":
            result = {"requested_disposition": "deep", "reason": "Original records may be useful",
                      "discriminating_test": "Compare the official engineering report with the original schedule",
                      "next_queries": ["engineering review documents for flood barrier"],
                      "scores": scores(PRELIMINARY_CRITERIA)}
            if self.scenario == "prelim_hold":
                result["requested_disposition"] = "hold"
                result["reason"] = "Research is blocked until the report is released"
            if self.scenario == "prelim_spike":
                result["requested_disposition"] = "spike"
                result["reason"] = "The putative angle has already been reported"
            if self.scenario == "low_prelim":
                result["scores"] = scores(PRELIMINARY_CRITERIA, partial=tuple(PRELIMINARY_CRITERIA))
            if self.scenario == "exactly_seventy":
                result["scores"] = scores(PRELIMINARY_CRITERIA, partial=(
                    "reader_question", "reader_context_gain", "specific_development",
                    "useful_story_angle"), none=("impact_magnitude", "timely_relevance"))
            if self.scenario == "missing_critical":
                result["scores"] = scores(PRELIMINARY_CRITERIA, none=("discriminating_test",))
            if self.scenario == "unknown_ref":
                result["scores"]["specific_development"]["evidence_refs"] = ["invented_source"]
            if self.scenario == "no_source_ref":
                result["scores"]["specific_development"]["evidence_refs"] = ["artifact:research_plan"]
            if self.scenario == "missing_dimension":
                result["scores"].pop("ethical_access")
            if self.scenario == "no_test":
                result["discriminating_test"] = "Could be true"
            if self.scenario == "too_many_deep_queries":
                result["next_queries"] = [f"research query {i} for barrier" for i in range(6)]
            return result
        if stage == "investigator_dossier_v3":
            result = dossier()
            if self.scenario == "reframe":
                result["departure_type"] = "reframed"
                result["departure_reason"] = "Research establishes infrastructure budgeting, not political motives."
            if self.scenario == "unrelated_new_case":
                result["departure_type"] = "new_case"
                result["departure_reason"] = "Evidence points to an unrelated science funding story."
            if self.scenario in {"final_spike", "final_hold"}:
                result["disposition"] = "spike" if self.scenario == "final_spike" else "hold"
                result["pitches"] = []
                result["reason"] = "Investigation concluded the original premise was unsound"
            if self.scenario == "low_completed":
                result["scores"] = scores(COMPLETED_CRITERIA, partial=tuple(COMPLETED_CRITERIA))
            if self.scenario == "bad_claim_id":
                result["findings"][0]["source_ids"] = ["nonexistent_source"]
            if self.scenario == "comment_as_fact":
                result["findings"][0]["source_ids"] = ["deep_comment"]
            if self.scenario == "future_timeline":
                result["timeline"][0]["at"] = NOW + 300
            if self.scenario == "empty_timeline":
                result["timeline"] = []
            if self.scenario == "market_headline":
                result["pitches"][0]["working_headline"] = "Polymarket Odds Signal Flood Barrier Delay"
            if self.scenario == "no_pitch":
                result["pitches"] = []
            if self.scenario == "no_coverage":
                result["prior_coverage_context"] = "Already known"
            if self.scenario == "duplicate_origins":
                result["findings"][0]["source_ids"] = ["seed_record"]
            if self.scenario == "no_deep_results":
                result["findings"][2]["source_ids"] = ["initial_report"]
            return result
        raise ValueError("Unknown model stage")


def run_scenario(scenario):
    model = ScriptedModel(scenario)
    provider = ScriptedResearch(scenario)
    seed = (source("seed_comment", "market_comment"),) if scenario == "no_credible_sources" else (
        source("seed_record", origin="same" if scenario == "duplicate_origins" else "seed_record"),)
    case = assignment(seed_sources=seed,
                      topic_lead_disposition="hold" if scenario == "topic_lead_no_go" else "go")
    return InvestigatorV3(model, provider).run(case), model, provider


SCENARIOS = {
    "valid_story": "ready_for_verifier",
    "reframe": "ready_for_verifier",
    "unrelated_new_case": "hold",
    "final_spike": "spike",
    "final_hold": "hold",
    "prelim_hold": "hold",
    "prelim_spike": "spike",
    "low_prelim": "hold",
    "exactly_seventy": "ready_for_verifier",
    "missing_critical": "hold",
    "unknown_ref": "hold",
    "no_source_ref": "hold",
    "missing_dimension": "hold",
    "no_credible_sources": "hold",
    "no_test": "hold",
    "future_capture": "hold",
    "source_collision": "hold",
    "extra_queries": "hold",
    "duplicate_queries": "hold",
    "too_many_deep_queries": "hold",
    "low_completed": "hold",
    "bad_claim_id": "hold",
    "future_timeline": "hold",
    "empty_timeline": "hold",
    "market_headline": "hold",
    "no_pitch": "hold",
    "no_coverage": "hold",
    "no_deep_results": "hold",
}


class InvestigatorV3Tests(unittest.TestCase):
    def test_adversarial_case_matrix(self):
        for scenario, expected in SCENARIOS.items():
            with self.subTest(scenario=scenario):
                run, model, provider = run_scenario(scenario)
                self.assertEqual(run["disposition"], expected, run["reason"])
                self.assertFalse(run["publication_enabled"])
                self.assertFalse(run["semantic_accuracy_certified"])
                self.assertLessEqual(len(provider.calls), 8)
                if expected == "ready_for_verifier":
                    self.assertEqual(run["completed_rubric"]["total"], 100)
                    self.assertEqual(len(model.calls), 3)

    def test_scores_are_anchor_bounded_and_cite_evidence(self):
        full = validate_scorecard(scores(PRELIMINARY_CRITERIA), PRELIMINARY_CRITERIA,
                                  {"seed_record"}, {"seed_record"})
        self.assertEqual(full["total"], 100)
        self.assertFalse(full["independently_validated"])
        half = validate_scorecard(scores(COMPLETED_CRITERIA,
                                         partial=tuple(COMPLETED_CRITERIA)),
                                  COMPLETED_CRITERIA, {"seed_record"}, {"seed_record"})
        self.assertEqual(half["total"], 50)
        with self.assertRaises(ValueError):
            validate_scorecard(scores(PRELIMINARY_CRITERIA, evidence="fake"),
                               PRELIMINARY_CRITERIA, {"seed_record"}, {"seed_record"})

    def test_no_direct_outreach_or_unapproved_assessment(self):
        run, model, provider = run_scenario("topic_lead_no_go")
        self.assertEqual(run["reason"], "topic_lead_assignment_not_authorized")
        self.assertEqual(model.calls, [])
        self.assertEqual(provider.calls, [])

    def test_stage_schemas_and_instructions_exist(self):
        for stage in ("investigator_plan_v3", "investigator_preliminary_v3",
                      "investigator_dossier_v3"):
            self.assertIn(stage, STAGE_SCHEMAS)
            self.assertGreater(len(STAGE_INSTRUCTIONS[stage]), 500)

    def test_reframing_has_reason_and_own_topics_get_retriaged(self):
        reframed, _, _ = run_scenario("reframe")
        self.assertEqual(reframed["dossier"]["departure_type"], "reframed")
        new_case, _, _ = run_scenario("unrelated_new_case")
        self.assertIn("unreviewed_new_topic", new_case["reason"])

    def test_live_shadow_can_use_later_capture_of_preexisting_public_record(self):
        case = assignment(research_mode="live_shadow")
        result = InvestigatorV3(ScriptedModel("future_capture"),
                                ScriptedResearch("future_capture")).run(case)
        self.assertEqual(result["disposition"], "ready_for_verifier")
        self.assertTrue(any(s["captured_after_case_as_of"]
                            for s in result["source_manifest"]))
        self.assertEqual(run_scenario("future_capture")[0]["disposition"], "hold")

    def test_topic_lead_handoff_requires_selected_angle_and_matching_captures(self):
        capture = source("seed_record")
        lead = SimpleNamespace(source_id=capture.source_id, url=capture.url,
                               published_at=capture.published_at,
                               origin_key=capture.origin_key, publisher=capture.publisher,
                               source_type="primary_record")
        context = SimpleNamespace(story_id="fictional_barrier", as_of=NOW,
                                  coverage_checked=True, sources=(lead,),
                                  coverage_matches=())
        angle = SimpleNamespace(angle_id="angle_a", central_question="Why the delay?",
                                working_headline="Engineering review delays approval",
                                source_ids=("seed_record",))
        assessment = SimpleNamespace(story_id="fictional_barrier", disposition="go",
                                     score=82, angles=(angle,),
                                     coverage_analysis="No prior identical coverage",
                                     research_questions=("Check the engineering record",))
        brief = assignment_from_topic_lead(context, assessment, (capture,), angle_id="angle_a")
        self.assertEqual(brief.seed_sources[0], capture)
        self.assertIn("Check the engineering record", brief.research_questions)
        missing_coverage = assignment_from_topic_lead(
            replace_fake(context, coverage_checked=False), assessment, (capture,),
            angle_id="angle_a")
        self.assertIn("COVERAGE UNREVIEWED", missing_coverage.coverage_summary)
        with self.assertRaises(ValueError):
            assignment_from_topic_lead(context, assessment, (capture,), angle_id="nonexistent")
        with self.assertRaises(ValueError):
            assignment_from_topic_lead(context, assessment,
                                       (replace(capture, publisher="wrong"),), angle_id="angle_a")
        with self.assertRaises(ValueError):
            assignment_from_topic_lead(context, assessment,
                                       (replace(capture, source_kind="market_comment"),),
                                       angle_id="angle_a")
        with self.assertRaises(ValueError):
            assignment_from_topic_lead(context, replace_fake(assessment, disposition="hold"),
                                       (capture,), angle_id="angle_a")


def replace_fake(item, **updates):
    """Simple helper for fake inter-stage contracts without mutable shared state."""
    return SimpleNamespace(**{**vars(item), **updates})


if __name__ == "__main__":
    unittest.main()
