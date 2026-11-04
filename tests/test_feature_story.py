"""Fail-closed contracts for evidence-based newspaper writing (synthetic)."""

from dataclasses import asdict, replace
import json
from pathlib import Path
import tempfile
import unittest

from marketsignal.feature_demo import demo_feature, fictional_feature_fixture
from marketsignal.feature_story import (
    ContextResearchEditor, FeatureNewsroom, GroundedNewspaperWriter, NewspaperEditor,
    NewspaperVerifier, assign_reporting_from_archive, audit_dossier, model_writer_assignment,
)


class NewspaperFeatureTests(unittest.TestCase):
    def setUp(self):
        self.candidate, self.dossier = fictional_feature_fixture()
        self.editor = NewspaperEditor()
        self.verifier = NewspaperVerifier()

    def test_editor_sets_broad_assignment_not_price_rewrite(self):
        task = ContextResearchEditor().assign(self.candidate)
        self.assertEqual(task.candidate_id, self.candidate.candidate_id)
        self.assertGreaterEqual(len(task.questions), 8)
        self.assertTrue(any("broader stakes" in question for question in task.questions))
        self.assertTrue(any("contradict" in item for item in task.minimum_checks))
        self.assertTrue(any("quote" in item for item in task.questions))

    def test_sufficient_credible_context_produces_standard_article(self):
        plan = self.editor.plan(self.candidate, self.dossier)
        self.assertEqual(plan.disposition, "draft_shadow")
        # Even five sources do not justify 1,000 words when supplied details
        # only support a ~300-word piece.
        self.assertEqual(plan.length_tier, "standard")
        article = GroundedNewspaperWriter().write(self.candidate, self.dossier, plan)
        self.assertEqual(self.verifier.check(self.candidate, self.dossier, plan, article), ())
        self.assertNotIn("odds", article.headline.lower())
        self.assertNotIn("%", article.headline)
        self.assertTrue(any(p.role == "prior_view" for p in article.paragraphs))
        self.assertTrue(any(p.role == "stakes" for p in article.paragraphs))
        self.assertTrue(any(p.role == "possible_explanation" for p in article.paragraphs))
        self.assertTrue(any(p.role == "counterpoint" for p in article.paragraphs))
        self.assertTrue(any(p.role == "market_context" for p in article.paragraphs))
        self.assertTrue(250 <= article.approximate_word_count <= 600)
        self.assertEqual(article.status, "SHADOW_ONLY")
        self.assertNotEqual(article.headline, self.dossier.proposed_headline)
        self.assertEqual(article.headline, self.dossier.editorial_selection.headline)

    def test_investigator_must_propose_multiple_supported_angles(self):
        broken = replace(self.dossier, story_pitches=())
        self.assertIn("missing_or_duplicate_story_pitches", self.editor.plan(self.candidate, broken).blockers)
        self.assertEqual(self.editor.plan(self.candidate, broken).disposition, "research_hold")

    def test_chief_editor_must_select_an_angle(self):
        broken = replace(self.dossier, editorial_selection=None)
        self.assertIn("no_editorially_selected_story", self.editor.plan(self.candidate, broken).blockers)

    def test_selected_story_requires_a_verifiable_spine_and_counterevidence(self):
        first = self.dossier.story_pitches[0]
        broken_pitch = replace(first, supporting_claim_ids=("development",), contrary_claim_ids=())
        broken = replace(self.dossier, story_pitches=(broken_pitch,) + self.dossier.story_pitches[1:])
        issues = self.editor.plan(self.candidate, broken).blockers
        self.assertIn("selected_pitch_missing_news_spine", issues)
        self.assertIn("selected_pitch_missing_counterevidence", issues)

    def test_an_epistemic_nonstory_headline_is_not_commissioned(self):
        selection = replace(self.dossier.editorial_selection,
                            headline="Early Voting Raises a Question Nobody Can Yet Answer")
        broken = replace(self.dossier, editorial_selection=selection)
        self.assertIn("epistemic_nonstory_headline", self.editor.plan(self.candidate, broken).blockers)

    def test_rewritten_headline_must_return_to_editorial_gate(self):
        plan = self.editor.plan(self.candidate, self.dossier)
        draft = GroundedNewspaperWriter().write(self.candidate, self.dossier, plan)
        revised = replace(draft, headline="A Reporter Invents a Different Framing of the Harbor")
        self.assertIn("headline_changed_without_evidence_review",
                      self.verifier.check(self.candidate, self.dossier, plan, revised))

    def test_quote_must_exist_in_captured_source(self):
        broken = replace(self.dossier.quotes[0], text="I said something completely different")
        dossier = replace(self.dossier, quotes=(broken,) + self.dossier.quotes[1:])
        self.assertIn("unverifiable_quote", audit_dossier(dossier, self.candidate))
        self.assertEqual(self.editor.plan(self.candidate, dossier).disposition, "research_hold")

    def test_source_text_hash_detects_tampering(self):
        altered = replace(self.dossier.documents[0], content="tampered " + self.dossier.documents[0].content)
        dossier = replace(self.dossier, documents=(altered,) + self.dossier.documents[1:])
        self.assertIn("invalid_source_capture", audit_dossier(dossier, self.candidate))

    def test_market_centered_headline_is_held(self):
        dossier = replace(self.dossier, proposed_headline="Market odds rise to 63% in Crescent Bay")
        self.assertIn("market_centered_headline", self.editor.plan(self.candidate, dossier).blockers)

    def test_consensus_cannot_come_from_single_public_statement(self):
        prior = replace(self.dossier.documents[0], source_kind="public_statement")
        dossier = replace(self.dossier, documents=(prior,) + self.dossier.documents[1:])
        self.assertIn("prior_consensus_unsubstantiated", self.editor.plan(self.candidate, dossier).blockers)

    def test_duplicated_origins_do_not_masquerade_as_independent_sources(self):
        dossier = replace(self.dossier, documents=tuple(replace(doc, independent_origin="same-origin")
                                                         for doc in self.dossier.documents))
        self.assertIn("insufficient_independent_origins", self.editor.plan(self.candidate, dossier).blockers)

    def test_investigator_handoff_id_mismatch_is_held(self):
        dossier = replace(self.dossier, candidate_id="other-market")
        self.assertIn("invalid_dossier_handoff", self.editor.plan(self.candidate, dossier).blockers)

    def test_speculation_cannot_be_labeled_confirmed(self):
        claims = tuple(replace(claim, certainty="reported") if claim.role == "hypothesis"
                       else claim for claim in self.dossier.claims)
        dossier = replace(self.dossier, claims=claims)
        self.assertIn("unsupported_context_claim", self.editor.plan(self.candidate, dossier).blockers)

    def test_fabricated_quote_in_article_is_blocked(self):
        plan = self.editor.plan(self.candidate, self.dossier)
        article = GroundedNewspaperWriter().write(self.candidate, self.dossier, plan)
        first = replace(article.paragraphs[0], text=article.paragraphs[0].text +
                        " “An invented direct quote appears here.”")
        altered = replace(article, paragraphs=(first,) + article.paragraphs[1:])
        self.assertIn("fabricated_direct_quote", self.verifier.check(self.candidate, self.dossier,
                                                                      plan, altered))

    def test_unsourced_paraphrase_is_not_automatically_verified(self):
        plan = self.editor.plan(self.candidate, self.dossier)
        article = GroundedNewspaperWriter().write(self.candidate, self.dossier, plan)
        first = replace(article.paragraphs[0], text="Every contractor secretly caused the delay")
        altered = replace(article, paragraphs=(first,) + article.paragraphs[1:])
        self.assertIn("claim_rephrased_without_semantic_review",
                      self.verifier.check(self.candidate, self.dossier, plan, altered))

    def test_synthetic_fixture_clearly_disclaims_independent_verification(self):
        report = demo_feature()
        self.assertTrue(report["synthetic"])
        self.assertFalse(report["publication_enabled"])
        self.assertFalse(report["review"]["semantic_accuracy_independently_certified"])
        self.assertFalse(report["review"]["publication_approved"])
        self.assertFalse(report["review"]["model_written"])

    def test_market_lead_without_corroborated_context_yields_no_article(self):
        result = FeatureNewsroom().run(self.candidate)
        self.assertEqual(result.status, "needs_context")
        self.assertIsNone(result.article)
        self.assertFalse(result.publication_enabled)

    def test_held_research_never_reaches_writer(self):
        dossier = replace(self.dossier, proposed_headline="Odds Jump 21 Points")
        result = FeatureNewsroom().run(self.candidate, dossier)
        self.assertEqual(result.status, "research_hold")
        self.assertIsNone(result.article)
        self.assertNotIn("permissioned_writer_handoff", result.handoffs)

    def test_invalid_market_move_is_held_before_reading_dossier(self):
        corrupted = replace(self.candidate, signal=replace(self.candidate.signal,
                                                           change_pp=90.0))
        result = FeatureNewsroom().run(corrupted, self.dossier)
        self.assertEqual(result.status, "research_hold")
        self.assertIn("nonrecomputable_change", result.issue_codes)
        self.assertNotIn("evidence_package_handoff", result.handoffs)

    def test_high_risk_context_draft_does_not_receive_editorial_clearance(self):
        high_risk = replace(self.candidate, risk="high")
        result = FeatureNewsroom().run(high_risk, self.dossier)
        self.assertEqual(result.status, "review_hold")
        self.assertIn("topic_risk_requires_human_editor", result.issue_codes)
        self.assertFalse(result.publication_enabled)

    def test_future_model_receives_bounded_evidence_not_full_source_pages(self):
        plan = self.editor.plan(self.candidate, self.dossier)
        assignment = model_writer_assignment(self.candidate, self.dossier, plan)
        self.assertFalse(assignment["publication_enabled"])
        self.assertTrue(assignment["human_semantic_factcheck_required"])
        self.assertEqual(len(assignment["sources"]), len(self.dossier.documents))
        self.assertFalse(any("content" in source for source in assignment["sources"]))
        self.assertTrue(any(c["certainty"] == "attributed_theory"
                            for c in assignment["claims"]))

    def test_real_archive_assigns_reporting_questions_but_not_a_story(self):
        record = {"schema_version": 1, "markets": [asdict(self.candidate.market)],
                  "signals": [asdict(self.candidate.signal)]}
        with tempfile.TemporaryDirectory() as location:
            path = Path(location) / "daily.json"
            path.write_text(json.dumps(record), encoding="utf-8")
            result = assign_reporting_from_archive(path)
        self.assertFalse(result["publication_enabled"])
        self.assertEqual(len(result["assignments"]), 1)
        self.assertEqual(result["assignments"][0]["status"], "needs_context")
        self.assertEqual(result["assignments"][0]["source_documents"], 0)


if __name__ == "__main__":
    unittest.main()
