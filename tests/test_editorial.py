"""Synthetic, no-network golden cases for the future agent workflow."""

import unittest
import math
from dataclasses import replace

from marketsignal.editorial import (
    Candidate, Claim, EditorialPipeline, Evidence, MarketRecordResearcher,
    TemplateWriter,
)
from marketsignal.models import Market, Signal


def sample_candidate(risk="low") -> Candidate:
    observed = 1_800_000_000
    market = Market(
        market_id="fictional-101", event_id="event-1",
        event_title="Fictional commercial space launch",
        event_slug="fictional-launch", question="Will Atlas launch by December 31?",
        yes_token_id="example-token", yes_price=0.54,
        volume_24h=640_000, liquidity=210_000, end_date="",
    )
    signal = Signal(
        market_id=market.market_id, observed_at=observed,
        baseline_at=observed - 86400, window_hours=24,
        previous_price=0.35, current_price=0.54, change_pp=19.0,
        score=83, volume_24h=640_000, liquidity=210_000,
    )
    return Candidate(market=market, signal=signal, risk=risk)


class EditorialTests(unittest.TestCase):
    def test_template_movement_brief_is_shadow_ready_not_published(self):
        result = EditorialPipeline().run(sample_candidate())
        self.assertEqual(result.status, "shadow_ready")
        self.assertFalse(result.reasons)
        self.assertIn("19.0 points", result.draft.headline)
        self.assertIn("not confirmation", result.draft.summary)
        self.assertEqual(result.evidence[0].kind, "market_snapshot")
        self.assertEqual(result.trace[-1], "shadow_ready")

    def test_real_candidates_default_to_unknown_risk_and_are_held(self):
        candidate = sample_candidate()
        candidate = Candidate(market=candidate.market, signal=candidate.signal)
        result = EditorialPipeline().run(candidate)
        self.assertEqual(result.status, "held")
        self.assertIn("risk_classification_requires_review", result.reasons)

    def test_high_risk_is_held(self):
        result = EditorialPipeline().run(sample_candidate("high"))
        self.assertEqual(result.status, "held")

    def test_market_price_math_cannot_be_invented(self):
        candidate = sample_candidate()
        tampered = replace(candidate.signal, change_pp=31.0)
        result = EditorialPipeline().run(replace(candidate, signal=tampered))
        self.assertEqual(result.status, "held")
        self.assertIn("nonrecomputable_change", result.reasons)
        self.assertIsNone(result.draft)

    def test_cross_market_quote_cannot_be_used(self):
        candidate = sample_candidate()
        result = EditorialPipeline().run(replace(candidate, market=replace(candidate.market, yes_price=.9)))
        self.assertEqual(result.status, "held")
        self.assertIn("current_quote_mismatch", result.reasons)

    def test_thin_market_is_held_even_if_signal_was_provided(self):
        candidate = sample_candidate()
        market = replace(candidate.market, liquidity=1_000)
        signal = replace(candidate.signal, liquidity=1_000)
        result = EditorialPipeline().run(replace(candidate, market=market, signal=signal))
        self.assertEqual(result.status, "held")
        self.assertIn("insufficient_market_depth", result.reasons)

    def test_nonfinite_value_is_held(self):
        candidate = sample_candidate()
        result = EditorialPipeline().run(replace(candidate, market=replace(candidate.market,
                                                                            liquidity=math.nan)))
        self.assertEqual(result.status, "held")
        self.assertIn("nonfinite_numeric_input", result.reasons)

    def test_candidate_key_is_deterministic_for_retry(self):
        a = sample_candidate()
        b = sample_candidate()
        self.assertEqual(a.candidate_id, b.candidate_id)

    def test_bad_external_source_url_is_rejected(self):
        class BadResearcher:
            def research(self, candidate):
                record = MarketRecordResearcher().research(candidate)[0]
                return (replace(record, url="http://localhost/admin"),)

        result = EditorialPipeline(researcher=BadResearcher()).run(sample_candidate())
        self.assertEqual(result.status, "held")
        self.assertIn("invalid_evidence_provenance", result.reasons)

    def test_unsupported_causal_explanation_is_held(self):
        class CausalWriter:
            def write(self, candidate, evidence):
                template = TemplateWriter().write(candidate, evidence)
                claim = Claim("A regulatory announcement caused the price move.",
                              "causal_explanation", (evidence[0].evidence_id,))
                return replace(template, claims=(claim,))

        result = EditorialPipeline(writer=CausalWriter()).run(sample_candidate())
        self.assertEqual(result.status, "held")
        self.assertIn("non_market_claim_requires_review", result.reasons)
        self.assertIn("model_or_custom_writer_requires_language_verification", result.reasons)

    def test_attributed_social_speculation_is_reviewable_but_not_auto_approved(self):
        class RumorWriter:
            def write(self, candidate, evidence):
                baseline = TemplateWriter().write(candidate, evidence)
                rumor = Claim("Some people are discussing an unverified launch delay.",
                              "attributed_speculation", (evidence[0].evidence_id,))
                return replace(baseline, claims=baseline.claims + (rumor,))

        result = EditorialPipeline(writer=RumorWriter()).run(sample_candidate())
        self.assertEqual(result.status, "held")
        self.assertIn("non_market_claim_requires_review", result.reasons)
        self.assertIn("model_or_custom_writer_requires_language_verification", result.reasons)

    def test_custom_writer_cannot_self_certify_as_trusted(self):
        class ImposterWriter:
            def write(self, candidate, evidence):
                return TemplateWriter().write(candidate, evidence)

        result = EditorialPipeline(writer=ImposterWriter()).run(sample_candidate())
        self.assertEqual(result.status, "held")
        self.assertIn("model_or_custom_writer_requires_language_verification", result.reasons)

    def test_missing_evidence_holds_draft(self):
        class EmptyResearcher:
            def research(self, candidate):
                return ()

        result = EditorialPipeline(researcher=EmptyResearcher()).run(sample_candidate())
        self.assertEqual(result.status, "held")
        self.assertIn("missing_evidence", result.reasons)
        self.assertIn("unsupported_citation", result.reasons)

    def test_agent_exception_holds_without_leaking_message(self):
        class BrokenResearcher:
            def research(self, candidate):
                raise RuntimeError("SECRET_EXTERNAL_API_KEY")

        result = EditorialPipeline(researcher=BrokenResearcher()).run(sample_candidate())
        self.assertEqual(result.status, "held")
        self.assertNotIn("SECRET", str(result.to_dict()))
        self.assertIn("agent_error:RuntimeError", result.trace)


if __name__ == "__main__":
    unittest.main()
