"""Real-topic, unapproved source-linked shadow article contract checks."""

import copy
import tempfile
import unittest
from pathlib import Path

from marketsignal.field_trial import audit_case, load_case, render_shadow


FIXTURE = Path(__file__).resolve().parent / "fixtures/fictional_field_trial.json"


class FieldTrialTests(unittest.TestCase):
    def setUp(self):
        self.case = load_case(FIXTURE)

    def test_fictional_case_is_structurally_complete_but_unapproved(self):
        audit = audit_case(self.case)
        self.assertEqual(audit["score"], 100)
        self.assertFalse(audit["semantic_accuracy_certified"])
        self.assertFalse(audit["human_editorial_quality_measured"])
        article = render_shadow(self.case)
        self.assertIn("Fictional Coastal Town", article)
        self.assertIn("SHADOW REPORT", article)
        self.assertIn("## Sources and outstanding checks", article)
        self.assertIn("No qualifying movement was observed", article)

    def test_future_source_fails_as_of_integrity(self):
        broken = copy.deepcopy(self.case)
        broken["sources"][0]["published_at"] = "2031-01-04T00:00:00Z"
        self.assertFalse(audit_case(broken)["checks"]["no_future_sources"])

    def test_missing_claim_provenance_blocks_report(self):
        broken = copy.deepcopy(self.case)
        broken["claims"][0]["supporting_excerpt"] = "an unsupported, invented assertion"
        self.assertFalse(audit_case(broken)["checks"]["source_linked_claims"])
        with self.assertRaises(ValueError):
            render_shadow(broken)

    def test_writer_cannot_invent_a_quote_or_skip_claim_link(self):
        broken = copy.deepcopy(self.case)
        broken["article"]["paragraphs"][0]["text"] += ' “We already won.”'
        self.assertFalse(audit_case(broken)["checks"]["quote_text_provenance"])
        broken = copy.deepcopy(self.case)
        broken["article"]["paragraphs"][0]["source_ids"] = ["city_notice"]
        self.assertFalse(audit_case(broken)["checks"]["paragraph_evidence_linkage"])

    def test_cannot_mark_case_publishable(self):
        broken = copy.deepcopy(self.case)
        broken["article"]["publication_enabled"] = True
        broken["article"]["human_semantic_factcheck"] = True
        self.assertFalse(audit_case(broken)["checks"]["human_release_gate_disabled"])

    def test_oversize_case_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "big.json"
            path.write_text("x" * 210000, encoding="utf-8")
            with self.assertRaises(ValueError):
                load_case(path)


if __name__ == "__main__":
    unittest.main()
