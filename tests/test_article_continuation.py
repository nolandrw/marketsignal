"""Offline controls for the real-dossier-to-article shadow continuation."""

import copy
import unittest
from dataclasses import replace

from marketsignal.article_continuation import continue_verified_dossier
from marketsignal.evidence_verifier import EvidenceReviewResult
from marketsignal.story_thesis import RUBRIC_WEIGHTS

from test_investigator_v3 import NOW, run_scenario, source


class ArticleModel:
    def __init__(self, *, invalid_citation=False):
        self.calls = []
        self.invalid_citation = invalid_citation

    def complete(self, stage, packet):
        self.calls.append(stage)
        if stage == "pitch_verifier":
            return {"reviews": [{"pitch_id": pitch["pitch_id"], "verdict": "accept",
                                 "issues": [], "research_requests": []}
                                for pitch in packet["pitches"]]}
        if stage == "chief_editor":
            pitch = packet["verified_pitches"][0]
            return {"decision": "commission", "selected_pitch_id": pitch["pitch_id"],
                    "headline": pitch["working_headline"],
                    "rationale": "The dated decision and its effect on residents deserve a clear, sourced explanation now.",
                    "scores": {key: maximum for key, maximum in RUBRIC_WEIGHTS.items()},
                    "requested_work": []}
        if stage == "writer":
            paragraphs = []
            ids = [("claim_new", "seed_record"), ("claim_context", "initial_report"),
                   ("claim_counter", "deep_record"), ("claim_new", "seed_record")]
            for index, (claim_id, source_id) in enumerate(ids):
                paragraphs.append({
                    "text": (f"In this fictional report, the documented coastal protection decision "
                             f"matters to residents who have been tracking the timetable. "
                             f"The evidence available for this particular point is limited to the "
                             f"linked public source. Readers should distinguish the recorded decision "
                             f"from speculation about its wider causes and future consequences. "
                             f"This is paragraph {index + 1} in a synthetic workflow demonstration."),
                    "claim_ids": [claim_id],
                    "source_ids": ["invented_source"] if self.invalid_citation else [source_id],
                })
            return {"headline": packet["editorial_selection"]["headline"],
                    "deck": "How a fictional municipal decision tests a sourced newsroom workflow.",
                    "paragraphs": paragraphs}
        if stage == "fact_verifier":
            return {"reviews": [{"paragraph_index": i, "verdict": "supported", "issues": []}
                                for i, _ in enumerate(packet["article"]["paragraphs"])],
                    "article_issues": []}
        if stage == "quality_reviewer":
            return {"verdict": "pass", "scores": RUBRIC_WEIGHTS, "issues": [],
                    "strengths": ["Clear evidence attribution"]}
        raise AssertionError("Unexpected model stage " + stage)


def ready_inputs():
    investigation, _, _ = run_scenario("valid_story")
    captures = (source("seed_record"), source("initial_report", "independent_reporting"),
                source("deep_record", "original_research"))
    review = EvidenceReviewResult(investigation["case_id"], "provisionally_verified", (), 3)
    return {"case_id": investigation["case_id"], "as_of": NOW,
            "investigation": investigation, "captures": captures,
            "verification": review, "market_question": "Will the fictional barrier be approved?"}


class ArticleContinuationTests(unittest.TestCase):
    def test_supported_dossier_reaches_every_article_gate_but_never_publishes(self):
        model = ArticleModel()
        result = continue_verified_dossier(**ready_inputs(), model=model)
        self.assertEqual(result["status"], "shadow_draft_ready_unpublished")
        self.assertEqual(result["model_calls"], 5)
        self.assertTrue(result["article"]["paragraphs"])
        self.assertFalse(result["publication_enabled"])
        self.assertFalse(result["human_factcheck_attested"])
        self.assertEqual(model.calls, ["pitch_verifier", "chief_editor", "writer",
                                       "fact_verifier", "quality_reviewer"])
        self.assertIn("draft_contract", [s["stage"] for s in result["stage_trace"]])

    def test_failed_prior_verification_cannot_reach_article_model(self):
        data = ready_inputs()
        data["verification"] = replace(data["verification"], status="return_to_investigator")
        model = ArticleModel()
        result = continue_verified_dossier(**data, model=model)
        self.assertEqual(result["status"], "held_pre_editorial")
        self.assertEqual(model.calls, [])

    def test_invented_citation_rejected_before_paragraph_fact_verifier(self):
        model = ArticleModel(invalid_citation=True)
        result = continue_verified_dossier(**ready_inputs(), model=model)
        self.assertEqual(result["status"], "shadow_review_hold")
        self.assertTrue(any(s["stage"] == "draft_contract" and s["status"] == "rejected"
                            for s in result["stage_trace"]))
        self.assertNotIn("fact_verifier", model.calls)
        self.assertFalse(result["publication_enabled"])

    def test_unverified_findings_from_unknown_sources_are_rejected(self):
        data = ready_inputs()
        data["investigation"] = copy.deepcopy(data["investigation"])
        data["investigation"]["dossier"]["findings"][0]["source_ids"] = ["invented_source"]
        model = ArticleModel()
        result = continue_verified_dossier(**data, model=model)
        self.assertEqual(result["status"], "held_pre_editorial")
        self.assertEqual(model.calls, [])


if __name__ == "__main__":
    unittest.main()
