import sqlite3
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from marketsignal.cli import newsroom_v3_demo
from marketsignal.copy_preflight import (
    CopyImage, CopyLink, article_digest, check_copy_artifact, prepare_copy_artifact,
)
from marketsignal.feature_demo import fictional_feature_fixture
from marketsignal.handoff_contract import ContractIssue, HandoffContractResult
from marketsignal.evidence_verifier import EvidenceReviewResult
from marketsignal.newsroom_control import (
    ClaimReview, ResearchTicket, StoryLedger, StoryState, TopicRubric,
    WorkflowController, accept_structural_dossier, story_id,
)
from marketsignal.oversight import (
    AudienceFeedback, IndependentEvaluation, OversightAgent, SyntheticAudiencePanel, grade_agents,
)


def new_story():
    return StoryState(story_id("abc", 1800000), "abc", 1800000)


class NewsroomControlTests(unittest.TestCase):
    def test_full_fictional_newsroom_reaches_release_hold_not_publication(self):
        demo = newsroom_v3_demo()
        self.assertEqual(demo["state"]["state"], "held")
        self.assertTrue(demo["audit_chain_valid"])
        self.assertEqual(demo["fictional_article"]["source_count"], 5)
        self.assertFalse(demo["fictional_article"]["semantic_factcheck_passed"])
        self.assertFalse(demo["publication_enabled"])
        self.assertIn("release_review", demo["audit_handoffs"])
        self.assertEqual(demo["audience_panel"]["issues"], [])
        self.assertEqual(demo["copy_preflight"]["status"], "passed")
        self.assertFalse(demo["copy_preflight"]["images_licensed"])
        self.assertEqual(demo["investigator_v3"]["disposition"], "ready_for_verifier")
        self.assertEqual(demo["handoff_contract"]["status"], "to_verifier")
        self.assertEqual(demo["evidence_verifier"]["status"], "provisionally_verified")
        self.assertFalse(demo["evidence_verifier"]["independent_human_review"])
        self.assertFalse(demo["process_overseer"]["semantic_truth_certified"])

    def test_illegal_transition_and_direct_release_fail_closed(self):
        story = new_story()
        with self.assertRaises(ValueError):
            WorkflowController.advance(story, "pending_owner_approval", reason="skip")
        WorkflowController.advance(story, "triaged", reason="valid movement")
        with self.assertRaises(ValueError):
            WorkflowController.advance(story, "drafting", reason="skip research")

    def test_investigator_v3_requires_contract_for_verifier_handoff(self):
        story = new_story()
        story.topic_score, story.topic_decision = 80, "go"
        for target in ("triaged", "topic_review", "investigating"):
            WorkflowController.advance(story, target, reason="test")
        report = {"case_id": story.story_id, "disposition": "ready_for_verifier",
                  "publication_enabled": False}
        review = HandoffContractResult(story.story_id, "return_to_investigator",
                                       (ContractIssue("", "invalid_source", "", "Check source"),), 0)
        WorkflowController.advance_investigator_v3(story, report, review)
        self.assertEqual(story.state, "held")
        second = new_story()
        second.topic_score, second.topic_decision = 80, "go"
        for target in ("triaged", "topic_review", "investigating"):
            WorkflowController.advance(second, target, reason="test")
        with self.assertRaises(ValueError):
            WorkflowController.advance_investigator_v3(
                second, {"case_id": "another_case", "disposition": "ready_for_verifier",
                         "publication_enabled": False}, review)
        approved = HandoffContractResult(second.story_id, "to_verifier", (), 4)
        WorkflowController.advance_investigator_v3(second,
                                                  {"case_id": second.story_id,
                                                   "disposition": "ready_for_verifier",
                                                   "publication_enabled": False},
                                                  approved)
        self.assertEqual(second.state, "verifying")
        self.assertFalse(second.evidence_verified)

    def test_research_budget_blocks_runaway_loops(self):
        story = new_story()
        story.topic_score, story.topic_decision = 80, "go"
        for target in ("triaged", "topic_review", "investigating"):
            WorkflowController.advance(story, target, reason="test")
        for _ in range(2):
            WorkflowController.advance(story, "verifying", reason="check")
            WorkflowController.advance(story, "investigating", reason="missing evidence")
        WorkflowController.advance(story, "verifying", reason="check")
        WorkflowController.advance(story, "investigating", reason="third request")
        self.assertEqual(story.state, "held")
        self.assertIn("research_revision_budget_exhausted", story.problems)

    def test_verifier_cannot_promote_without_evidence(self):
        story = new_story()
        story.topic_score, story.topic_decision = 80, "go"
        for target in ("triaged", "topic_review", "investigating", "verifying"):
            WorkflowController.advance(story, target, reason="test")
        with self.assertRaises(ValueError):
            WorkflowController.advance(story, "chief_editor", reason="unsupported")

    def test_verifier_return_is_bounded_and_missing_verifier_holds(self):
        story = new_story()
        story.topic_score, story.topic_decision = 80, "go"
        for target in ("triaged", "topic_review", "investigating", "verifying"):
            WorkflowController.advance(story, target, reason="test")
        missing = EvidenceReviewResult(story.story_id, "awaiting_independent_verifier",
                                       (ContractIssue("", "no_model", "", "Check source"),), 0)
        WorkflowController.record_evidence_verification(story, missing)
        self.assertEqual(story.state, "held")
        self.assertFalse(story.evidence_verified)
        story2 = new_story()
        story2.topic_score, story2.topic_decision = 80, "go"
        for target in ("triaged", "topic_review", "investigating", "verifying"):
            WorkflowController.advance(story2, target, reason="test")
        returned = EvidenceReviewResult(story2.story_id, "return_to_investigator",
                                        (ContractIssue("claim", "claim_contradicted", "s1",
                                                       "Research contradiction"),), 3)
        WorkflowController.record_evidence_verification(story2, returned)
        self.assertEqual(story2.state, "investigating")
        self.assertEqual(story2.research_revisions, 1)

    def test_synthetic_fixture_can_pass_structural_dossier_only(self):
        candidate, dossier = fictional_feature_fixture()
        story = new_story()
        story.topic_score, story.topic_decision = 80, "go"
        for target in ("triaged", "topic_review", "investigating", "verifying"):
            WorkflowController.advance(story, target, reason="fictional")
        issues = accept_structural_dossier(story, candidate, dossier)
        self.assertEqual(issues, ())
        with self.assertRaises(ValueError):
            WorkflowController.advance(story, "chief_editor", reason="structural_pass_only")
        WorkflowController.record_evidence_verification(
            story, EvidenceReviewResult(story.story_id, "provisionally_verified", (), 4))
        WorkflowController.advance(story, "chief_editor", reason="fixture passed")
        self.assertFalse(story.semantic_review_passed)
        with self.assertRaises(ValueError):
            WorkflowController.advance(story, "drafting", reason="no assignment")
        story.editorial_assignment_ready = True
        WorkflowController.advance(story, "drafting", reason="fictional assignment")

    def test_claim_review_rejects_unsupported_approval(self):
        with self.assertRaises(ValueError):
            ClaimReview("id", "absent", "none", "none", "approved", (), "no evidence")
        valid = ClaimReview("id", "direct", "one", "none", "approved", ("source-1",), "cited")
        self.assertEqual(valid.disposition, "approved")
        with self.assertRaises(ValueError):
            ResearchTicket("id", "", ("find file",))

    def test_topic_rubric_requires_source(self):
        rubric = TopicRubric(5, 5, 5, 5, 5)
        self.assertEqual(rubric.score, 100)
        self.assertFalse(rubric.eligible)
        self.assertTrue(TopicRubric(5, 5, 5, 5, 5, ("source-1",)).eligible)

    def test_topic_review_requires_explicit_go_not_just_self_assessed_score(self):
        story = new_story()
        WorkflowController.advance(story, "triaged", reason="test")
        WorkflowController.advance(story, "topic_review", reason="test")
        story.topic_score = 99
        with self.assertRaises(ValueError):
            WorkflowController.advance(story, "investigating", reason="no topic decision")
        story.topic_decision = "hold"
        with self.assertRaises(ValueError):
            WorkflowController.advance(story, "investigating", reason="hold cannot bypass")
        story.topic_decision, story.topic_score = "go", 64
        with self.assertRaises(ValueError):
            WorkflowController.advance(story, "investigating", reason="below 65")
        story.topic_score = 65
        WorkflowController.advance(story, "investigating", reason="passed")

    def test_held_topic_must_be_reassessed_to_reopen(self):
        story = new_story()
        for target in ("triaged", "topic_review", "held"):
            WorkflowController.advance(story, target, reason="awaiting proof")
        with self.assertRaises(ValueError):
            WorkflowController.advance(story, "investigating", reason="no approval")
        WorkflowController.advance(story, "topic_review", reason="new evidence")
        story.topic_score, story.topic_decision = 75, "go"
        WorkflowController.advance(story, "investigating", reason="reconsidered")

    def test_owner_approval_needs_full_review_even_after_editor(self):
        state = new_story()
        state.state = "pending_owner_approval"
        with self.assertRaises(ValueError):
            WorkflowController.advance(state, "approved_for_manual_release",
                                       reason="model says yes", owner_authorized=False)

    def test_release_cannot_be_self_approved_or_published_on_a_boolean(self):
        story = new_story()
        story.state = "release_review"
        story.semantic_review_passed = True
        story.risk = "low"
        story.dossier_audited = True
        story.editorial_review_passed = True
        story.copy_review_passed = True
        story.audience_review_recorded = True
        story.article_sha256 = "a" * 64
        story.copy_article_sha256 = "a" * 64
        # Even all model-controlled pass flags cannot reach owner approval.
        with self.assertRaises(ValueError):
            WorkflowController.advance(story, "pending_owner_approval", reason="no human review")
        story.human_factcheck_reference = "human-review-case-37"
        story.factchecked_article_sha256 = "b" * 64
        with self.assertRaises(ValueError):
            WorkflowController.advance(story, "pending_owner_approval", reason="reviewed stale draft")
        story.factchecked_article_sha256 = "a" * 64
        WorkflowController.advance(story, "pending_owner_approval", reason="reviewed current version")
        with self.assertRaises(ValueError):
            WorkflowController.advance(story, "approved_for_manual_release", reason="no owner", owner_authorized=False)

    def test_copy_stage_requires_editor_approved_article_fingerprint(self):
        story = new_story()
        story.state = "copy_editing"
        story.copy_review_passed = True
        story.article_sha256 = "a" * 64
        story.copy_article_sha256 = "b" * 64
        with self.assertRaises(ValueError):
            WorkflowController.advance(story, "audience_review", reason="tampered")
        story.copy_article_sha256 = story.article_sha256
        WorkflowController.advance(story, "audience_review", reason="matching article")

    def test_copy_layout_must_not_change_editor_approved_text(self):
        candidate, dossier = fictional_feature_fixture()
        from marketsignal.feature_story import FeatureNewsroom
        output = FeatureNewsroom().run(candidate, dossier)
        self.assertIsNotNone(output.article)
        draft = output.article
        artifact = prepare_copy_artifact(draft, dossier.documents)
        self.assertEqual(check_copy_artifact(draft, dossier.documents, artifact), ())
        modified = replace(artifact, headline="Edited into an unsupported allegation")
        self.assertIn("copy_modified_editor_approved_prose",
                      check_copy_artifact(draft, dossier.documents, modified))
        self.assertEqual(artifact.approved_article_sha256, article_digest(draft))
        self.assertTrue(artifact.links)
        altered = replace(artifact, links=(CopyLink(artifact.links[0].source_id,
                                "https://another.example/?affiliate=me"),) + artifact.links[1:])
        self.assertIn("altered_or_unsafe_source_link",
                      check_copy_artifact(draft, dossier.documents, altered))
        unlicensed = replace(artifact, images=(CopyImage("https://img.example/a.jpg", "Flood", "", ""),))
        self.assertIn("unlicensed_or_unattributed_image",
                      check_copy_artifact(draft, dossier.documents, unlicensed))
        malformed = replace(artifact, images=(CopyImage("https://[bad", "Flood", "X", "record"),))
        self.assertIn("unlicensed_or_unattributed_image",
                      check_copy_artifact(draft, dossier.documents, malformed))

    def test_ledger_is_append_only_and_tamper_evident(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "private.db"
            state = new_story()
            with StoryLedger(path) as ledger:
                ledger.record(state, "triage", "quality_pass", {"score": 78}, now=1234)
                ledger.record(state, "editor", "correct_hold", now=1235)
                self.assertTrue(ledger.verify_chain(state.story_id))
                self.assertEqual(len(ledger.events(state.story_id)), 2)
                ledger.db.execute("UPDATE story_events SET reason_code='quality_fail' WHERE event_id=1")
                ledger.db.commit()
                self.assertFalse(ledger.verify_chain(state.story_id))

    def test_ledger_rejects_unbounded_or_sensitive_metadata(self):
        with StoryLedger(":memory:") as ledger:
            with self.assertRaises(ValueError):
                ledger.record(new_story(), "agent", "quality_pass", {"source_text": "x" * 1000})


class OversightTests(unittest.TestCase):
    def test_panel_is_eight_diagnostic_personas_not_readers(self):
        panel = SyntheticAudiencePanel()
        report = panel.examine("Market odds jump", "Too short", 0, 1)
        self.assertFalse(report["independent_human_rating"])
        self.assertEqual(report["persona_count"], 8)
        self.assertFalse(report["publication_approval"])

    def test_real_feedback_only_proposes_weight_changes(self):
        panel = SyntheticAudiencePanel()
        fake = [AudienceFeedback("topic_newcomer", 1, "synthetic") for _ in range(30)]
        self.assertEqual(panel.propose_reweight(fake)["status"],
                         "insufficient_valid_human_feedback")
        real = [AudienceFeedback("topic_newcomer", 1) for _ in range(30)]
        proposal = panel.propose_reweight(real)
        self.assertEqual(proposal["status"], "bespoke_approval_required")
        self.assertEqual(proposal["proposed"]["topic_newcomer"], 1.1)
        self.assertEqual(panel.weights["topic_newcomer"], 1.0)

    def test_oversight_does_not_rewrite_policy(self):
        metrics = {"event_count": 30,
                   "agents": {"verifier": {"quality_fail": 10, "quality_pass": 20,
                                            "source_timeout": 6}}}
        proposals = OversightAgent().assess(metrics)
        self.assertEqual({p.tranche for p in proposals}, {"automatic"})
        auto = next(p for p in proposals if p.tranche == "automatic")
        updated = OversightAgent().apply_automatic({"source_retry_backoff_seconds": 0.25}, auto)
        self.assertEqual(updated["source_retry_backoff_seconds"], .5)
        # Internal quality_pass/fail reason codes are not external labels.
        self.assertEqual(grade_agents(metrics)["verifier"]["grade"], "unrated")
        editorial_labels = [IndependentEvaluation(str(i), "verifier", i >= 10,
                            "senior_editor", f"review-{i}", "editorial-rubric-v1")
                            for i in range(30)]
        proposals = OversightAgent().assess(metrics, editorial_labels)
        self.assertEqual({p.tranche for p in proposals}, {"automatic", "bespoke"})
        with self.assertRaises(ValueError):
            OversightAgent().apply_automatic({}, next(p for p in proposals if p.tranche == "bespoke"))
        grades = grade_agents(metrics, evaluations=editorial_labels)
        self.assertEqual(grades["verifier"]["grade"], "unrated")
        self.assertEqual(grades["verifier"]["indicative_unverified_grade"], "D")
        self.assertFalse(grades["verifier"]["authentication_integrated"])
        self.assertEqual(grade_agents({"agents": {"writer": {"quality_pass": 3}}})["writer"]["grade"],
                         "unrated")

    def test_oversight_rejects_duplicate_and_synthetic_grade_laundering(self):
        eval1 = IndependentEvaluation("story-a", "writer", False, "editor", "review-a", "rubric-1")
        with self.assertRaises(ValueError):
            grade_agents({}, evaluations=[eval1, eval1])
        with self.assertRaises(ValueError):
            IndependentEvaluation("story-a", "writer", True, "writer", "review-a", "rubric-1")
        with self.assertRaises(ValueError):
            IndependentEvaluation("story-a", "writer", True, "editor", "review-a", "rubric-1",
                                  source="synthetic")


if __name__ == "__main__":
    unittest.main()
