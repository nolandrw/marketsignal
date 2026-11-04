"""The paid pilot stays manual, private, and bounded before any model calls."""

import base64
import contextlib
import io
import os
import tarfile
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace

from marketsignal.investigator_v3 import ResearchCapture
from marketsignal.topic_lead import TopicSourceLead
from scripts import run_research_pilot as pilot


class PilotRunnerTests(unittest.TestCase):
    def test_seed_gate_accepts_one_original_but_keeps_rights_dates_and_hashes(self):
        as_of = int(time.time())
        fixtures = [("records.example.gov", "official_record", "primary_record",
                     "official_public_record"),
                    ("research.example.edu", "original_research", "primary_record",
                     "permissioned_short_excerpt"),
                    ("licensed.example.com", "independent_reporting", "independent_reporting",
                     "permissioned_short_excerpt")]
        captures, leads, rows, publishers = [], [], [], []
        for index, (host, kind, lead_type, rights) in enumerate(fixtures):
            url = f"https://{host}/public-report-{index}"
            key = f"ref{index}"
            capture = ResearchCapture(key, url, host, host, as_of - 86400,
                                      as_of + 60, kind,
                                      "Original verified publisher text with a dated source record.",
                                      document_sha256="a" * 64, content_location="html:paragraph:1",
                                      mime_type="text/html",
                                      publication_date_basis="publisher_page_metadata")
            captures.append(capture)
            leads.append(TopicSourceLead(key, host, url, host, as_of - 86400,
                                         lead_type, capture.excerpt))
            rows.append({"source_id": key, "copyright_basis": rights,
                         "robots_decision": "allowed"})
            publishers.append({"host": host, "kind": kind, "copyright_basis": rights})
        context = SimpleNamespace(as_of=as_of, sources=leads)
        policy = {"publishers": publishers}
        pilot.require_authentic_seed_packet(context, captures, policy, rows)
        # The source hunt starts with one genuine record; more sources are
        # an Investigator output, not a precondition to run the Investigator.
        pilot.require_authentic_seed_packet(context, captures[:1], policy, rows[:1])
        with self.assertRaisesRegex(ValueError, "provenance"):
            pilot.require_authentic_seed_packet(context, captures, policy,
                                                 rows[:2] + [{**rows[2], "robots_decision": "denied"}])
        with self.assertRaisesRegex(ValueError, "provenance"):
            pilot.require_authentic_seed_packet(context, captures[:2] + [
                ResearchCapture(**{**captures[2].__dict__, "document_sha256": ""})], policy, rows)
        without_reporting = [ResearchCapture(**{**captures[2].__dict__,
                                             "source_kind": "original_research"})]
        altered_policy = {"publishers": publishers[:2] + [{**publishers[2],
                           "kind": "original_research"}]}
        altered_leads = leads[:2] + [TopicSourceLead(leads[2].source_id,
                         leads[2].publisher, leads[2].url, leads[2].origin_key,
                         leads[2].published_at, "primary_record", leads[2].captured_excerpt)]
        # A pilot with only official / original research remains eligible;
        # an independent-reporting document must still be permissioned if used.
        pilot.require_authentic_seed_packet(
            SimpleNamespace(as_of=as_of, sources=altered_leads),
            captures[:2] + without_reporting, altered_policy, rows)
        with self.assertRaisesRegex(ValueError, "provenance"):
            pilot.require_authentic_seed_packet(
                context, captures[:1], {"publishers": []}, rows[:1])
        with self.assertRaisesRegex(ValueError, "inventory"):
            pilot.require_authentic_seed_packet(context, (), policy, ())

    def test_exact_four_subjects_and_private_paths_required(self):
        for bad in ("../stolen.json", "data/archive/case.json",
                    "data/private/../docs/case.json", "data/private/item.txt"):
            with self.assertRaises(ValueError):
                pilot._private_file(bad)
        self.assertEqual(pilot.LIMIT_USD, "2.00")
        self.assertEqual(len(pilot.EXPECTED_IDS), 4)

    def test_missing_key_prevents_any_trial_calls(self):
        with (patch.object(pilot, "_rows", return_value=[{"name": "hormuz"}]),
              patch.object(pilot, "preflight") as checked,
              patch.object(pilot, "run_cli") as network,
              patch.dict(os.environ, {"OPENAI_API_KEY": ""})):
            with self.assertRaises(ValueError):
                pilot.run()
        checked.assert_called_once()
        network.assert_not_called()

    def test_all_four_sequential_calls_share_exactly_two_dollar_ledger(self):
        rows = [{"name": name, "context_file": f"data/private/{name}-context.json",
                 "captures_file": f"data/private/{name}-captures.json",
                 "policy_file": f"data/private/{name}-policy.json",
                 "test_fixture_file": f"data/private/{name}-fixture.json",
                 "angle_id": "auto:first"} for name in pilot.EXPECTED_IDS]
        shared = SimpleNamespace(path=Path("data/private/pilot-model-budget.sqlite"),
                                 summary=lambda: {"budget_usd": 2.0})
        with (patch.object(pilot, "_rows", return_value=rows),
              patch.object(pilot, "preflight"),
              patch.object(pilot, "ModelBudget", return_value=shared) as budget,
              patch.object(pilot, "run_cli", return_value=0) as execute,
              patch.dict(os.environ, {"OPENAI_API_KEY": "test-only-dummy"}),
              contextlib.redirect_stdout(io.StringIO())):
            self.assertEqual(pilot.run(), 0)
        budget.assert_called_once_with("data/private/pilot-model-budget.sqlite", "2.00")
        self.assertEqual(execute.call_count, 4)
        for call in execute.call_args_list:
            argv = call.args[0]
            self.assertEqual(argv[argv.index("--max-model-spend-usd") + 1], "2.00")
            self.assertEqual(argv[argv.index("--model-budget-db") + 1], str(shared.path))
            self.assertEqual(argv[argv.index("--angle-id") + 1], "auto:first")

    def test_valid_bundle_is_unpacked_into_private_paths_only(self):
        with tempfile.TemporaryDirectory() as directory:
            previous = Path.cwd()
            os.chdir(directory)
            try:
                buf = io.BytesIO()
                with tarfile.open(fileobj=buf, mode="w:gz") as archive:
                    for name in ("data/private/pilot-manifest.json", "data/private/input.json"):
                        content = b"{}"
                        info = tarfile.TarInfo(name)
                        info.size = len(content)
                        archive.addfile(info, io.BytesIO(content))
                secret = base64.b64encode(buf.getvalue()).decode()
                with patch.dict(os.environ, {"MARKETSIGNAL_PILOT_BUNDLE_B64": secret}):
                    pilot.unpack_from_secret()
                self.assertEqual(Path("data/private/input.json").read_bytes(), b"{}")
            finally:
                os.chdir(previous)

    def test_bad_bundle_fails_closed_without_writing_files(self):
        with tempfile.TemporaryDirectory() as directory:
            previous = Path.cwd()
            os.chdir(directory)
            try:
                buf = io.BytesIO()
                with tarfile.open(fileobj=buf, mode="w:gz") as archive:
                    for name in ("data/private/pilot-manifest.json", "../oops.json"):
                        content = b"{}"
                        info = tarfile.TarInfo(name)
                        info.size = len(content)
                        archive.addfile(info, io.BytesIO(content))
                secret = base64.b64encode(buf.getvalue()).decode()
                with patch.dict(os.environ, {"MARKETSIGNAL_PILOT_BUNDLE_B64": secret}):
                    with self.assertRaises(ValueError):
                        pilot.unpack_from_secret()
                self.assertFalse(Path("data/private/pilot-manifest.json").exists())
                self.assertFalse(Path("oops.json").exists())
            finally:
                os.chdir(previous)


if __name__ == "__main__":
    unittest.main()
