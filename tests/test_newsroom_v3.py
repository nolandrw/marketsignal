import sqlite3
import tempfile
import unittest
from pathlib import Path

from marketsignal.cli import newsroom_v3_demo
from marketsignal.feature_demo import fictional_feature_fixture
from marketsignal.newsroom_control import (
    ClaimReview, ResearchTicket, StoryLedger, StoryState, TopicRubric,
    WorkflowController, accept_structural_dossier, story_id,
)
from marketsignal.oversight import (
    AudienceFeedback, OversightAgent, SyntheticAudiencePanel, grade_agents,
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

    def test_illegal_transition_and_direct_release_fail_closed(self):
        story = new_story()
        with self.assertRaises(ValueError):
            WorkflowController.advance(story, "pending_owner_approval", reason="skip")
        WorkflowController.advance(story, "triaged", reason="valid movement")
        with self.assertRaises(ValueError):
            WorkflowController.advance(story, "drafting", reason="skip research")

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

    def test_synthetic_fixture_can_pass_structural_dossier_only(self):
        candidate, dossier = fictional_feature_fixture()
        story = new_story()
        story.topic_score, story.topic_decision = 80, "go"
        for target in ("triaged", "topic_review", "investigating", "verifying"):
            WorkflowController.advance(story, target, reason="fictional")
        issues = accept_structural_dossier(story, candidate, dossier)
        self.assertEqual(issues, ())
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
        rubric = TopicRubric(5, 5, 5, 5, 5, 5)
        self.assertEqual(rubric.score, 100)
        self.assertFalse(rubric.eligible)
        self.assertTrue(TopicRubric(5, 5, 5, 5, 5, 5, ("source-1",)).eligible)

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
        self.assertEqual({p.tranche for p in proposals}, {"automatic", "bespoke"})
        auto = next(p for p in proposals if p.tranche == "automatic")
        updated = OversightAgent().apply_automatic({"source_retry_backoff_seconds": 0.25}, auto)
        self.assertEqual(updated["source_retry_backoff_seconds"], .5)
        with self.assertRaises(ValueError):
            OversightAgent().apply_automatic({}, next(p for p in proposals if p.tranche == "bespoke"))
        grades = grade_agents(metrics)
        self.assertEqual(grades["verifier"]["grade"], "D")
        self.assertEqual(grade_agents({"agents": {"writer": {"quality_pass": 3}}})["writer"]["grade"],
                         "unrated")


if __name__ == "__main__":
    unittest.main()
