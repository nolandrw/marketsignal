"""Human-selected evaluation fixtures must never become production inputs."""

import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from marketsignal.evaluation_harness import (
    ResearchTestFixture, evaluate_topic_fixture, load_test_fixture,
)
from marketsignal.topic_lead import TopicLeadAgent
from test_topic_lead import context, proposal


class RecordingModel:
    def __init__(self):
        self.inputs = []

    def complete(self, stage, payload):
        self.inputs.append((stage, payload))
        return proposal()


def ineligible_case():
    original = context()
    return replace(original, quantitative_pitch=replace(
        original.quantitative_pitch, changes_pp={}, baseline_times={},
        eligible_for_topic_review=False,
        reasons=("no_historical_baseline", "uncalibrated_volatility")))


class EvaluationFixtureTests(unittest.TestCase):
    def test_only_test_harness_bypasses_quantitative_gate(self):
        case = ineligible_case()
        model = RecordingModel()
        normal = TopicLeadAgent(model).assess(case)
        self.assertEqual(normal.disposition, "hold")
        self.assertIn("quantitative_triage_not_eligible", normal.reason_codes)
        self.assertNotIn("test_only_evaluation", model.inputs[0][1])

        fixture = ResearchTestFixture(case.story_id, case.quantitative_pitch.market_id,
                                      case.as_of, "Evaluate a deliberately selected negative case")
        tested = evaluate_topic_fixture(model, case, fixture)
        self.assertEqual(tested.disposition, "go")
        self.assertTrue(tested.evaluation_only)
        self.assertFalse(tested.publication_enabled)
        self.assertIn("test_fixture_only_quantitative_override", tested.reason_codes)
        self.assertFalse(model.inputs[1][1]["test_only_evaluation"]["original_quantitative_eligibility"])
        self.assertEqual(model.inputs[1][1]["quantitative_pitch"]["changes_pp"], {})
        self.assertNotIn("quantitative_triage_not_eligible", tested.reason_codes)

    def test_fixture_still_enforces_non_quantitative_editorial_gates(self):
        case = replace(ineligible_case(), coverage_checked=False)
        fixture = ResearchTestFixture(case.story_id, case.quantitative_pitch.market_id,
                                      case.as_of, "Test without a coverage baseline")
        incomplete = evaluate_topic_fixture(RecordingModel(), case, fixture)
        self.assertEqual(incomplete.disposition, "go")
        self.assertIn("coverage_review_pending", incomplete.reason_codes)
        case = ineligible_case()
        wrong = replace(fixture, case_id="other_case")
        with self.assertRaises(ValueError):
            evaluate_topic_fixture(RecordingModel(), case, wrong)
        model = RecordingModel()
        fixture = ResearchTestFixture(case.story_id, case.quantitative_pitch.market_id,
                                      case.as_of, "Test with no independent source support")
        no_sources = replace(case, sources=())
        with self.assertRaises(ValueError):
            evaluate_topic_fixture(model, no_sources, fixture)

    def test_fixture_loader_accepts_only_explicit_private_nonpublishing_file(self):
        case = ineligible_case()
        fixture = ResearchTestFixture(case.story_id, case.quantitative_pitch.market_id,
                                      case.as_of, "A bounded external source research test")
        with tempfile.TemporaryDirectory() as directory:
            private = Path(directory) / "private"
            private.mkdir()
            path = private / "case.json"
            path.write_text(json.dumps(fixture.__dict__), encoding="utf-8")
            self.assertEqual(load_test_fixture(path), fixture)
            path.write_text(json.dumps({**fixture.__dict__, "publication_enabled": True}),
                            encoding="utf-8")
            with self.assertRaises(ValueError):
                load_test_fixture(path)
            path.write_text(json.dumps({**fixture.__dict__, "unexpected": "policy"}),
                            encoding="utf-8")
            with self.assertRaises(ValueError):
                load_test_fixture(path)


if __name__ == "__main__":
    unittest.main()
