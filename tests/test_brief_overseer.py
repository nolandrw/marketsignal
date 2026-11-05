"""The process overseer never becomes a second article-verification gate."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from marketsignal.brief_overseer import (
    analyze_brief_run, load_private_run, render_actions_summary,
    render_private_dashboard,
)


def brief(case_id, status, *, event_id=None, human=False, headline="World-facing news",
          trigger="price_movement", with_release=True):
    stages = [
        {"stage": "brief_scout", "status": "completed"},
        {"stage": "coverage_discovery", "status": "completed", "leads": 4},
        {"stage": "brief_editor", "status": "completed"},
        {"stage": "brief_writer", "status": "completed"},
        {"stage": "brief_contract", "status": "passed", "issues": []},
        {"stage": "brief_factcheck", "status": "completed"},
    ]
    if status != "held_brief_review":
        stages.append({"stage": "brief_factcheck_gate", "status": "passed_provisionally"})
    else:
        stages.append({"stage": "brief_factcheck_gate", "status": "rejected"})
    if with_release:
        state = "held_duplicate" if status == "held_redundant_brief" else "passed_unique"
        stages.append({"stage": "brief_release_editor", "status": state})
    return {"status": status,
            "market": {"market_id": case_id, "event_id": event_id or case_id,
                       "question": f"Will sample {case_id} happen?",
                       "trigger": trigger, "change_pp": 0 if trigger != "price_movement" else 4},
            "stage_trace": stages,
            "model_calls": 4,
            "editor_score": 65,
            "human_factcheck_attested": human,
            "article": {"headline": headline,
                        "deck": "This is private and not for the public",
                        "paragraphs": [{"text": "PRIVATE STORY BODY: TOP SECRET\n<script>alert(1)</script>"}]},
            "external_leads": [{"url": "https://secret.example.org/private-report"}],
            "publication_enabled": False}


class BriefOverseerTests(unittest.TestCase):
    def setUp(self):
        self.sample = [
            brief("a", "shadow_brief_ready_unpublished", event_id="fed"),
            brief("b", "held_redundant_brief", event_id="fed"),
            brief("c", "held_brief_review", with_release=False),
            brief("d", "held_brief_review", with_release=False),
            brief("e", "shadow_brief_ready_unpublished",
                  headline="Market odds imply editorial attention", trigger="coverage_without_price_movement"),
            brief("f", "shadow_brief_ready_unpublished", human=True),
        ]

    def test_stage_funnel_and_process_tickets(self):
        report = analyze_brief_run(self.sample, {"budget": {"debited_usd": 0.07}})
        summary = report["summary"]
        self.assertEqual(summary["cases"], 6)
        self.assertEqual(summary["provisional_drafts"], 4)
        self.assertEqual(summary["unique_after_release"], 3)
        self.assertEqual(summary["duplicate_holds"], 1)
        self.assertEqual(summary["coverage_attention_triggers"], 1)
        self.assertEqual(summary["human_reviewed"], 1)
        self.assertEqual(summary["estimated_model_spend_usd"], 0.07)
        codes = {p["failure_code"] for p in report["improvement_proposals"]}
        self.assertIn("brief_factcheck_rejection", codes)
        self.assertIn("brief_same_event_overlap", codes)
        self.assertNotIn("brief_human_labels_missing", codes)
        self.assertTrue(all(p["owner_approval_required"] and
                            p["status"] == "proposed_unapplied"
                            for p in report["improvement_proposals"]))
        self.assertFalse(report["provenance"]["publication_enabled"])
        self.assertFalse(report["provenance"]["automatic_prompt_edits"])

    def test_legacy_without_release_editor_is_not_marked_unique(self):
        report = analyze_brief_run([brief("a", "shadow_brief_ready_unpublished",
                                        with_release=False)])
        self.assertIsNone(report["summary"]["unique_after_release"])
        self.assertFalse(report["summary"]["release_editor_executed"])

    def test_render_is_private_escaped_and_contains_no_manuscript_or_urls(self):
        report = analyze_brief_run(self.sample)
        report["cases"][0]["market_question"] = "<img src=x onerror=alert(1)>"
        with TemporaryDirectory() as root:
            destination = Path(root) / "private" / "oversight.html"
            render_private_dashboard(report, destination)
            html = destination.read_text(encoding="utf-8")
            self.assertIn("&lt;img src=x onerror=alert(1)&gt;", html)
            self.assertNotIn("<img src=x", html)
            self.assertIn("Stage-gate funnel", html)
            self.assertIn("Proposed improvement experiments", html)
            self.assertNotIn("TOP SECRET", html)
            self.assertNotIn("secret.example.org", html)
            with self.assertRaises(ValueError):
                render_private_dashboard(report, Path(root) / "site" / "oversight.html")
        job_summary = render_actions_summary(report)
        self.assertIn("Provisional fact-check passes", job_summary)
        self.assertNotIn("<img", job_summary)
        self.assertNotIn("TOP SECRET", job_summary)
        self.assertNotIn("Will sample", job_summary)

    def test_load_private_run_uses_local_artifacts_and_no_model(self):
        with TemporaryDirectory() as root:
            directory = Path(root) / "private" / "brief-pilot-results"
            directory.mkdir(parents=True)
            (directory / "brief-01.json").write_text(json.dumps(self.sample[0]), encoding="utf-8")
            (directory / "manifest.json").write_text(json.dumps({"budget": {
                "debited_usd": 0.01}}), encoding="utf-8")
            report = load_private_run(directory)
            self.assertEqual(report["summary"]["cases"], 1)
            self.assertEqual(report["summary"]["estimated_model_spend_usd"], 0.01)
            with self.assertRaises(ValueError):
                load_private_run(Path(root) / "public")

    def test_rejects_duplicate_or_malformed_cases(self):
        with self.assertRaises(ValueError):
            analyze_brief_run([self.sample[0], self.sample[0]])
        with self.assertRaises(ValueError):
            analyze_brief_run([{"status": "bad", "stage_trace": "bad"}])


if __name__ == "__main__":
    unittest.main()
