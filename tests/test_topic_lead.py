"""Topic Lead contract tests: never treat model enthusiasm as proof."""

import copy
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from marketsignal.cli import main
from marketsignal.model_gateway import STAGE_INSTRUCTIONS, STAGE_SCHEMAS
from marketsignal.quantitative import QuantitativePitch
from marketsignal.topic_lead import (
    CoverageMatch, TopicLeadAgent, TopicLeadContext, TopicSourceLead, load_topic_context,
)


def context():
    as_of = 1_800_000_000
    quantitative = QuantitativePitch(
        market_id="fictional-bay", venue="polymarket", category="weather",
        observed_at=as_of, changes_pp={"24h": 21.0},
        baseline_times={"24h": as_of - 86400}, historical_daily_samples=2,
        typical_daily_movement_pp=None, volume_to_historical_median=None,
        threshold_24h_pp=12.0, movement_surprise=None, quantitative_score=84,
        eligible_for_topic_review=True, reasons=("movement_24h",),
    )
    sources = (
        TopicSourceLead("notice", "Fictional City Engineering Department",
                        "https://example.org/notice", "city", as_of - 3000,
                        "primary_record", "Approval delayed pending foundation review"),
        TopicSourceLead("impact", "Fictional Civic Research Institute",
                        "https://example.org/impact", "research", as_of - 5000,
                        "independent_reporting", "Thousands of residents lack flood defenses"),
        TopicSourceLead("comment", "Anonymous market commentator",
                        "https://example.org/comments", "market-users", as_of - 100,
                        "market_comment", "Rumor about unrelated costs"),
    )
    return TopicLeadContext(
        "case-fictional-1", as_of,
        "Will a fictional coastal flood barrier be approved this year?",
        "Resolves YES on documented formal approval before year end",
        quantitative, sources, True,
    )


def proposal():
    return {
        "requested_disposition": "go",
        "scores": {"news_peg": 5, "consequences": 4, "editorial_potential": 4,
                   "originality": 4, "research_feasibility": 4, "timeliness": 4},
        "score_rationales": {
            "news_peg": "Dated official notice records an actual delay",
            "consequences": "Residents need flood protection",
            "editorial_potential": "Technical review threatens long-promised protection",
            "originality": "The local tradeoffs merit independent assessment",
            "research_feasibility": "Independent documentary and reporting leads",
            "timeliness": "A newly postponed city decision",
        },
        "news_peg_type": "documented_development",
        "news_peg": "A vote was postponed",
        "news_peg_source_ids": ["notice"],
        "prior_expectation": "Approval had been expected",
        "prior_expectation_source_ids": ["notice"],
        "public_stakes": "Households face another storm season without new defenses",
        "public_stakes_source_ids": ["impact"],
        "coverage_analysis": "Index checked; angle not yet assigned",
        "angles": [{"angle_id": "timeline-delay",
                    "working_headline": "Coastal Barrier Delayed as Residents Wait for Protection",
                    "central_question": "Why did approval slip?",
                    "thesis_to_test": "An unfinished survey upset the projected timetable",
                    "disconfirmation_test": "Find a dated document showing the survey is complete",
                    "novel_contribution": "Explain a consequential engineering tradeoff",
                    "source_ids": ["notice", "impact"]}],
        "counterevidence": ["Delay alone does not prove design failure"],
        "research_questions": ["What does the engineering study actually show?"],
        "uncertainties": ["Final approval timing remains unknown"],
        "sensitivity_flags": ["public_safety"],
        "revisit_condition": "An updated review or vote announcement",
    }


class RecordedModel:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def complete(self, stage, payload):
        self.calls.append((stage, payload))
        return copy.deepcopy(self.response)


class TopicLeadTests(unittest.TestCase):
    def test_balanced_go_requires_independent_sourced_assignment(self):
        model = RecordedModel(proposal())
        result = TopicLeadAgent(model).assess(context())
        self.assertEqual(result.score, 84)
        self.assertEqual(result.disposition, "go")
        self.assertEqual(result.referenced_source_ids, ("impact", "notice"))
        self.assertFalse(result.publication_enabled)
        self.assertEqual(model.calls[0][0], "topic_lead")

    def test_65_is_minimum_go_threshold_with_gates(self):
        response = proposal()
        response["scores"] = {"news_peg": 3, "consequences": 3,
                              "editorial_potential": 3, "originality": 3,
                              "research_feasibility": 4, "timeliness": 4}
        accepted = TopicLeadAgent(RecordedModel(response)).assess(context())
        self.assertEqual(accepted.score, 65)
        self.assertEqual(accepted.disposition, "go")
        response["scores"]["research_feasibility"] = 3
        response["scores"]["timeliness"] = 5
        held = TopicLeadAgent(RecordedModel(response)).assess(context())
        self.assertEqual(held.score, 64)
        self.assertEqual(held.disposition, "hold")
        self.assertIn("score_below_go_threshold", held.reason_codes)

    def test_high_stakes_low_score_is_held_not_automatically_spiked(self):
        response = proposal()
        response["scores"] = {"news_peg": 1, "consequences": 5,
                              "editorial_potential": 1, "originality": 0,
                              "research_feasibility": 1, "timeliness": 0}
        assessed = TopicLeadAgent(RecordedModel(response)).assess(context())
        self.assertEqual(assessed.score, 31)
        self.assertEqual(assessed.disposition, "hold")
        self.assertIn("high_consequence_exception", assessed.reason_codes)

    def test_unexplained_large_movement_does_not_go(self):
        response = proposal()
        response["news_peg_type"] = "emerging_signal"
        response["news_peg"] = "Market activity has risen without reported catalyst"
        response["news_peg_source_ids"] = []
        assessed = TopicLeadAgent(RecordedModel(response)).assess(context())
        self.assertEqual(assessed.disposition, "hold")
        self.assertIn("unexplained_market_movement", assessed.reason_codes)

    def test_market_comments_never_count_as_independent_reporting(self):
        response = proposal()
        response["angles"][0]["source_ids"] = ["comment"]
        response["news_peg_source_ids"] = ["comment"]
        response["public_stakes_source_ids"] = ["comment"]
        response["prior_expectation_source_ids"] = ["comment"]
        assessed = TopicLeadAgent(RecordedModel(response)).assess(context())
        self.assertEqual(assessed.disposition, "hold")
        self.assertIn("no_authentic_research_seed", assessed.reason_codes)

    def test_one_primary_can_start_source_hunt_without_prior_corroboration(self):
        only_primary = replace(context(), sources=(context().sources[0],),
                               primary_has_independent_test=False)
        response = proposal()
        response["public_stakes_source_ids"] = ["notice"]
        response["angles"][0]["source_ids"] = ["notice"]
        result = TopicLeadAgent(RecordedModel(response)).assess(only_primary)
        self.assertEqual(result.disposition, "go")

    def test_missing_coverage_check_is_explicit_research_task_not_a_hold(self):
        candidate = replace(context(), coverage_checked=False)
        result = TopicLeadAgent(RecordedModel(proposal())).assess(candidate)
        self.assertEqual(result.disposition, "go")
        self.assertIn("coverage_review_pending", result.reason_codes)

    def test_exact_angle_duplication_spikes_only_existing_angles(self):
        candidate = replace(context(), coverage_matches=(CoverageMatch(
            "old-story", "Existing article on same delay", "complete", ("timeline-delay",)),))
        result = TopicLeadAgent(RecordedModel(proposal())).assess(candidate)
        self.assertEqual(result.disposition, "spike")
        self.assertIn("all_angles_duplicative", result.reason_codes)

    def test_unknown_source_cannot_enter_handoff(self):
        response = proposal()
        response["angles"][0]["source_ids"].append("invented-document")
        with self.assertRaisesRegex(ValueError, "invented source"):
            TopicLeadAgent(RecordedModel(response)).assess(context())

    def test_future_dated_evidence_rejected_before_model(self):
        bad_source = replace(context().sources[0], published_at=context().as_of + 1)
        with self.assertRaisesRegex(ValueError, "Future-dated"):
            replace(context(), sources=(bad_source,))

    def test_missing_hold_revisit_is_rejected(self):
        response = proposal()
        response["requested_disposition"] = "hold"
        response["revisit_condition"] = ""
        with self.assertRaisesRegex(ValueError, "revisit condition"):
            TopicLeadAgent(RecordedModel(response)).assess(context())

    def test_market_headline_rejected(self):
        response = proposal()
        response["angles"][0]["working_headline"] = "Polymarket Odds Jump 21%"
        with self.assertRaisesRegex(ValueError, "market mechanics"):
            TopicLeadAgent(RecordedModel(response)).assess(context())

    def test_provider_prompt_has_exact_stage_schema_and_safety_scope(self):
        self.assertEqual(STAGE_SCHEMAS["topic_lead"]["additionalProperties"], False)
        instruction = STAGE_INSTRUCTIONS["topic_lead"]
        for expected in ("65/100", "LOW-RELIABILITY", "original", "untrusted"):
            self.assertIn(expected.lower(), instruction.lower())

    def test_private_context_file_roundtrip_and_no_key_hold(self):
        with tempfile.TemporaryDirectory() as temp:
            case_path = Path(temp) / "context.json"
            case_path.write_text(json.dumps({"schema_version": 1, **context().to_dict()}),
                                 encoding="utf-8")
            loaded = load_topic_context(case_path)
            self.assertEqual(loaded.story_id, context().story_id)
            self.assertEqual(len(loaded.sources), 3)
            report_path = Path(temp) / "data/private/topic-lead-result.json"
            with patch.dict(os.environ, {"OPENAI_API_KEY": ""}):
                with redirect_stdout(io.StringIO()) as output:
                    status = main(["topic-lead", "--context-file", str(case_path),
                                   "--out", str(report_path)])
            self.assertEqual(status, 1)
            self.assertIn('"status": "research_hold"', output.getvalue())
            self.assertFalse(report_path.exists())

    def test_spiked_and_held_topics_are_never_promoted_by_score(self):
        for disposition in ("spike", "hold"):
            response = proposal()
            response["requested_disposition"] = disposition
            result = TopicLeadAgent(RecordedModel(response)).assess(context())
            self.assertEqual(result.disposition, disposition)
            self.assertEqual(result.score, 84)


if __name__ == "__main__":
    unittest.main()
