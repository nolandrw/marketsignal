"""Fictional multi-source fixtures; no real access, billing, or claim truth tests."""

import unittest
import json
import tempfile
from types import SimpleNamespace
from dataclasses import replace
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path
from unittest.mock import patch

from marketsignal.agent_sources import CrossrefSearch, SourceLead
from marketsignal.handoff_contract import HandoffContractGateway
from marketsignal.evidence_verifier import ClaimJudgment, EvidenceVerifier, ModelClaimReview
from marketsignal.evaluation_harness import ResearchTestFixture
from marketsignal.oversight import ProcessFailureEvent, ProcessOverseer
from marketsignal.investigator_v3 import ResearchBatch, ResearchLead
from marketsignal.research_retrieval import (
    MultiSourceResearchProvider, OfficialFeedSearch, PublicOfficialFeedTransport,
    SOURCE_CATALOG,
)
from marketsignal.research_runtime import (
    configure_research_sources, load_seed_captures, run_research_shadow,
)
from marketsignal.source_capture import ArticleCapture

from test_investigator_v3 import NOW, run_scenario, source
from test_topic_lead import context as topic_context, proposal as topic_proposal


class FictionalFeedTransport:
    def get(self, url):
        date = format_datetime(datetime.fromtimestamp(NOW - 2400, timezone.utc))
        return (f"<rss><channel><item><title>Coastal barrier engineering review</title>"
                f"<link>https://agency.gov/review</link><pubDate>{date}</pubDate>"
                "</item></channel></rss>").encode("utf-8")


class FictionalDiscovery:
    def __init__(self, leads):
        self.leads = leads
        self.calls = []

    def search(self, query, since, until, limit=4):
        self.calls.append((query, since, until, limit))
        return self.leads[:limit]


class FictionalCrossrefTransport:
    def get(self, endpoint, params):
        self.endpoint, self.params = endpoint, params
        self.timestamp = datetime.fromtimestamp(NOW - 86400, timezone.utc)
        return {"message": {"items": [{
            "title": ["Scientific observations of coastal resilience"],
            "URL": "https://doi.org/10.0000/fictional",
            "publisher": "Fictional Science Society",
            "published": {"date-parts": [[self.timestamp.year, self.timestamp.month,
                                          self.timestamp.day]]},
        }]}}


class FictionalPageCapturer:
    def __init__(self):
        self.calls = []

    def capture(self, lead, *, observed_at):
        self.calls.append(lead)
        host = "agency.gov" if "agency.gov" in lead.url else "paper.example"
        return ArticleCapture(
            url=lead.url, publisher=host, origin=host,
            published_at=NOW - 2400, captured_at=NOW - 100,
            kind="official_record" if host == "agency.gov" else "independent_reporting",
            copyright_basis="official_public_record" if host == "agency.gov" else "permissioned_short_excerpt",
            document_sha256="1" * 64, excerpts=(
                "The document states a coastal review is pending the next decision date.",
                "The review does not establish a safety failure and requires further assessment.",
            ),
        )


def get_provider():
    media = FictionalDiscovery((SourceLead(
        "gdelt", "https://paper.example/story", "Civic account of coastal barrier review",
        NOW - 1500, "paper.example"),))
    social = FictionalDiscovery((SourceLead(
        "bluesky", "https://bsky.app/profile/example.test/post/abc123",
        "A local observer speculates about the barrier costs", NOW - 400, "public_user"),))
    chat = FictionalDiscovery((SourceLead(
        "polymarket_comment_unverified", "https://polymarket.com/event/fictional-barrier",
        "Speculation about the barrier on market chat", NOW - 200),))
    capture = FictionalPageCapturer()
    provider = MultiSourceResearchProvider({
        "official_feeds": OfficialFeedSearch(("https://agency.gov/news.rss",), FictionalFeedTransport()),
        "gdelt_news": media, "bluesky": social, "polymarket_chat": chat,
    }, capture)
    return provider, capture, media, social, chat


class ScriptedEvidenceReviewer:
    def __init__(self, verdict="supported", wrong_excerpt=False):
        self.verdict, self.wrong_excerpt = verdict, wrong_excerpt
        self.payloads = []

    def assess(self, claims, sources, coverage_summary):
        self.payloads.append((claims, sources, coverage_summary))
        index = {s.source_id: s for s in sources}
        return tuple(ClaimJudgment(
            claim_id=c["claim_id"], verdict=self.verdict, source_id=c["source_ids"][0],
            exact_evidence="Nonexistent exact quote" if self.wrong_excerpt else
                           index[c["source_ids"][0]].excerpt[:40],
            rationale="The original excerpt supports or disputes this attributable claim.",
        ) for c in claims)


class ResearchAndOversightTests(unittest.TestCase):
    def test_multi_source_retrieval_keeps_comments_as_discovery_only(self):
        provider, capture, media, social, chat = get_provider()
        batch = provider.search("coastal barrier engineering review", as_of=NOW, limit=4)
        self.assertIsInstance(batch, ResearchBatch)
        self.assertEqual(len(batch.captures), 2)
        self.assertEqual(len(batch.leads), 4)
        self.assertEqual({c.source_kind for c in batch.captures},
                         {"official_record", "independent_reporting"})
        self.assertEqual({lead.source_role for lead in batch.leads},
                         {"official_lead", "coverage", "discussion"})
        self.assertFalse(any("bsky.app" in row.url or "polymarket.com" in row.url
                             for row in batch.captures))
        self.assertEqual(provider.coverage_audit()["score"], 100)
        self.assertEqual(len(capture.calls), 2)
        self.assertTrue(all(adapter.calls for adapter in (media, social, chat)))

    def test_research_catalog_explicitly_gates_x_and_reddit(self):
        policy = {p.connector_id: p for p in SOURCE_CATALOG}
        self.assertEqual(policy["x_search"].access, "permission_required")
        self.assertEqual(policy["reddit"].launch_status, "deferred")
        with self.assertRaises(ValueError):
            MultiSourceResearchProvider({"reddit": FictionalDiscovery(())}, FictionalPageCapturer())
        with self.assertRaises(ValueError):
            PublicOfficialFeedTransport(("localhost",))
        transport = PublicOfficialFeedTransport(("agency.gov",))
        with self.assertRaises(ValueError):
            transport.get("https://private.example/feed")

    def test_scholarly_metadata_is_a_lead_not_original_document_proof(self):
        transport = FictionalCrossrefTransport()
        results = CrossrefSearch(transport).search("coastal resilience science", NOW - 86400 * 3,
                                                    NOW, limit=3)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].platform, "crossref")
        self.assertEqual(transport.endpoint, "https://api.crossref.org/works")
        self.assertFalse(next(p for p in SOURCE_CATALOG
                              if p.connector_id == "crossref").allowed_to_capture)

    def test_provider_does_not_extend_research_network_budget(self):
        provider, *_ = get_provider()
        provider.max_provider_calls = 2
        batch = provider.search("coastal barrier engineering review", as_of=NOW, limit=4)
        self.assertEqual(batch.sources_attempted, ("official_feeds", "gdelt_news"))
        self.assertIn("provider_budget_exhausted", batch.source_errors)
        self.assertEqual(provider.coverage_audit()["source_calls"], 2)

    def test_social_search_is_rate_bounded_without_suppressing_official_checks(self):
        provider, *_ = get_provider()
        for _ in range(3):
            latest = provider.search("coastal barrier engineering review", as_of=NOW, limit=4)
        self.assertEqual(provider.calls_by_source["official_feeds"], 3)
        self.assertEqual(provider.calls_by_source["gdelt_news"], 3)
        self.assertEqual(provider.calls_by_source["bluesky"], 2)
        self.assertEqual(provider.calls_by_source["polymarket_chat"], 2)
        self.assertIn("bluesky:discussion_budget_exhausted", latest.source_errors)

    def test_cross_domain_mock_cases_do_not_promote_discovery_to_facts(self):
        # Deliberately different topical/source conditions; no model journalism.
        for label, sources, captured in (
            ("public_health", {"official_feeds": (SourceLead(
                "official_rss", "https://agency.gov/health-order",
                "Agency health order published", NOW - 3000),),
                "gdelt_news": (SourceLead("gdelt", "https://paper.example/health",
                                          "Independent health policy reporting", NOW - 2000),)}, 2),
            ("sports_rumor", {"bluesky": (SourceLead(
                "bluesky", "https://bsky.app/profile/sports.test/post/p",
                "Rumor about manager departure", NOW - 100),)}, 0),
            ("research_preprint", {"crossref": (SourceLead(
                "crossref", "https://doi.org/10.1234/preprint",
                "New study of natural hazards", NOW - 2500),)}, 0),
        ):
            with self.subTest(topic=label):
                provider = MultiSourceResearchProvider(
                    {name: FictionalDiscovery(items) for name, items in sources.items()},
                    FictionalPageCapturer())
                result = provider.search("public facts and primary reporting", as_of=NOW, limit=4)
                self.assertEqual(len(result.captures), captured)
                self.assertEqual(len(result.leads), sum(map(len, sources.values())))
                if label != "public_health":
                    self.assertFalse(provider.coverage_audit()["checks"]["official_record_captured"]["passed"])

    def test_contract_is_structural_and_verifier_owns_claim_interpretation(self):
        investigation, _, _ = run_scenario("valid_story")
        captures = (source("seed_record"), source("initial_report", "independent_reporting"),
                    source("deep_record", "original_research"))
        contract = HandoffContractGateway().validate(investigation, captures, as_of=NOW)
        self.assertEqual(contract.status, "to_verifier")
        self.assertEqual(contract.claims_checked, 3)
        self.assertEqual(contract.check_kind, "deterministic_contract_only")
        missing = EvidenceVerifier().verify(
            investigation, captures, contract, coverage_summary="Prior reporting compared")
        self.assertEqual(missing.status, "awaiting_independent_verifier")
        reviewer = ScriptedEvidenceReviewer()
        approved = EvidenceVerifier(reviewer).verify(
            investigation, captures, contract, coverage_summary="Prior reporting compared")
        self.assertEqual(approved.status, "provisionally_verified")
        self.assertFalse(approved.publication_enabled)
        self.assertFalse(approved.authenticated_human_factcheck)
        self.assertEqual(approved.claims_reviewed, 3)
        self.assertTrue(all("scores" not in c for c in reviewer.payloads[0][0]))
        contradicted = EvidenceVerifier(ScriptedEvidenceReviewer("contradicted")).verify(
            investigation, captures, contract, coverage_summary="Prior reporting compared")
        self.assertEqual(contradicted.status, "return_to_investigator")
        self.assertEqual(len(contradicted.issues), 3)
        broken = EvidenceVerifier(ScriptedEvidenceReviewer(wrong_excerpt=True)).verify(
            investigation, captures, contract, coverage_summary="Prior reporting compared")
        self.assertTrue(any(issue.reason_code == "verifier_citation_invalid"
                            for issue in broken.issues))
        tampered = HandoffContractGateway().validate(
            investigation, (replace(captures[0], excerpt=captures[0].excerpt + " changed"),) +
            captures[1:], as_of=NOW)
        self.assertTrue(any(issue.reason_code == "source_manifest_mismatch"
                            for issue in tampered.issues))

    def test_overseer_diagnoses_distinct_cases_without_becoming_verifier(self):
        events = tuple(ProcessFailureEvent(f"case_{n}", "contract_gateway",
                                           "source_manifest_mismatch", occurred_at=NOW)
                       for n in range(5))
        diagnosis = ProcessOverseer().diagnose(events)
        self.assertEqual(len(diagnosis["proposals"]), 1)
        self.assertTrue(diagnosis["proposals"][0]["owner_approval_required"])
        self.assertFalse(diagnosis["automatic_prompt_edits"])
        self.assertEqual(diagnosis["proposals"][0]["distinct_affected_cases"], 5)
        self.assertIn("held_out_regression_cases", diagnosis["proposals"][0]["required_tests"])
        # Repeated failures within one case are notable, but not cross-case evidence.
        repeated = ProcessOverseer().diagnose(events[:1] * 5)
        self.assertFalse(repeated["proposals"])
        self.assertEqual(repeated["repeated_case_failures"][0]["count"], 5)
        suspicious = tuple(ProcessFailureEvent(
            f"suspicious_{n}", "investigator_v3", "provisional_dossier_ready",
            investigator_self_score=100, source_count=0, finding_count=0)
            for n in range(3))
        diagnostics = ProcessOverseer().diagnose(suspicious)
        self.assertEqual(diagnostics["proposals"][0]["failure_code"],
                         "self_score_evidence_mismatch")
        self.assertFalse(diagnostics["semantic_truth_certified"])

    def test_gateway_rejects_invented_ids_future_sources_and_social_claims(self):
        investigation, _, _ = run_scenario("valid_story")
        captures = (source("seed_record"), source("initial_report", "independent_reporting"),
                    source("deep_record", "original_research"))
        invented = {**investigation, "dossier": {
            **investigation["dossier"], "findings": [
                {**investigation["dossier"]["findings"][0], "source_ids": ["invented_id"]},
                *investigation["dossier"]["findings"][1:]]}}
        result = HandoffContractGateway().validate(invented, captures, as_of=NOW)
        self.assertIn("unavailable_cited_source", {i.reason_code for i in result.issues})
        future = HandoffContractGateway().validate(investigation, captures, as_of=NOW - 1000000)
        self.assertIn("source_postdates_case_as_of", {i.reason_code for i in future.issues})
        bad_timeline = {**investigation, "dossier": {
            **investigation["dossier"], "timeline": [{"at": NOW + 1,
                                                      "claim_ids": ["invented_claim"]}]}}
        timeline = HandoffContractGateway().validate(bad_timeline, captures, as_of=NOW)
        self.assertIn("invalid_timeline_reference", {i.reason_code for i in timeline.issues})
        absent = {**investigation, "dossier": {**investigation["dossier"], "findings": []},
                  "completed_rubric": {"total": 100}}
        empty = HandoffContractGateway().validate(absent, captures, as_of=NOW)
        self.assertIn("missing_material_claims", {i.reason_code for i in empty.issues})

    def test_model_claim_review_is_owned_by_verifier_stage(self):
        class RecordingModel:
            def __init__(self):
                self.stages = []

            def complete(self, stage, payload):
                self.stages.append(stage)
                return {"judgments": []}

        model = RecordingModel()
        ModelClaimReview(model).assess((), (), "Prior coverage")
        self.assertEqual(model.stages, ["dossier_evidence_verifier"])

    def test_shadow_go_calls_only_one_semantic_dossier_verifier_after_contract(self):
        report, _, _ = run_scenario("valid_story")
        case = topic_context()
        report["case_id"] = case.story_id
        captures = (source("seed_record"), source("initial_report", "independent_reporting"),
                    source("deep_record", "original_research"))

        class FakeResearch:
            pass

        fake_research = FakeResearch()
        fake_research.captures = {s.source_id: s for s in captures[1:]}

        class FakeInvestigator:
            def __init__(self, model, research):
                pass

            def run(self, assignment):
                return report

        class StageModel:
            def __init__(self, verdict):
                self.verdict, self.calls = verdict, []

            def complete(self, stage, payload):
                self.calls.append(stage)
                if stage == "topic_lead":
                    return topic_proposal()
                if stage == "dossier_evidence_verifier":
                    lookup = {s["source_id"]: s["excerpt"] for s in payload["sources"]}
                    return {"judgments": [{
                        "claim_id": c["claim_id"], "verdict": self.verdict,
                        "source_id": c["source_ids"][0],
                        "exact_evidence": lookup[c["source_ids"][0]][:40],
                        "rationale": "A provisional, deliberately scripted source assessment.",
                    } for c in payload["claims"]]}
                raise AssertionError("Unexpected second semantic review: " + stage)

        with (patch("marketsignal.research_runtime.assignment_from_topic_lead",
                    return_value=SimpleNamespace(coverage_summary="Prior coverage")),
              patch("marketsignal.research_runtime.configure_research_sources",
                    return_value=fake_research),
              patch("marketsignal.research_runtime.InvestigatorV3", FakeInvestigator)):
            for verdict, expected in (("supported", "provisionally_verified_for_editorial_review"),
                                      ("contradicted", "held_pending_research_or_review")):
                model = StageModel(verdict)
                result = run_research_shadow(case, captures[:1], angle_id="timeline-delay",
                                             research_policy={}, model=model)
                self.assertEqual(model.calls, ["topic_lead", "dossier_evidence_verifier"])
                self.assertEqual(result["handoff_contract"]["status"], "to_verifier")
                self.assertEqual(result["status"], expected)
                self.assertFalse(result["publication_enabled"])
                if verdict == "contradicted":
                    self.assertIn("claim_contradicted", {
                        e["reason_code"] for e in result["process_events"]})
            seeded_case = replace(case, quantitative_pitch=replace(
                case.quantitative_pitch, eligible_for_topic_review=False,
                changes_pp={}, baseline_times={}, reasons=("no_historical_baseline",)))
            fixture = ResearchTestFixture(seeded_case.story_id,
                                          seeded_case.quantitative_pitch.market_id,
                                          seeded_case.as_of,
                                          "Test-only human-selected subject without fabricated prices")
            seeded_model = StageModel("supported")
            seeded = run_research_shadow(seeded_case, captures[:1],
                                         angle_id="auto:first", research_policy={},
                                         model=seeded_model, test_fixture=fixture)
            self.assertEqual(seeded["status"], "provisionally_verified_for_editorial_review")
            self.assertTrue(seeded["evaluation_only"])
            self.assertEqual(seeded["topic_lead"]["selected_angle_id"], "timeline-delay")
            self.assertEqual(seeded_model.calls, ["topic_lead", "dossier_evidence_verifier"])
            with self.assertRaises(ValueError):
                run_research_shadow(case, captures[:1], angle_id="auto:first",
                                    research_policy={}, model=StageModel("supported"))

    def test_explicit_private_runtime_configuration_and_existing_capture_rows(self):
        provider = configure_research_sources({
            "publishers": [{"host": "paper.example", "kind": "independent_reporting",
                            "copyright_basis": "permissioned_short_excerpt"}],
            "enable_bluesky": False, "enable_crossref": False,
        })
        self.assertEqual(set(provider.connectors), {"gdelt_news"})
        with self.assertRaises(ValueError):
            configure_research_sources({"publishers": [], "x_search": True})
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, "captured-context.json")
            path.write_text(json.dumps({"source_rows": [{
                "source_id": "record_1", "url": "https://paper.example/story",
                "publisher": "paper.example", "independent_origin": "paper.example",
                "published_at": "2026-11-04T10:00:00Z", "captured_at": NOW - 100,
                "kind": "independent_reporting",
                "captured_excerpt": "A properly dated original paragraph from the public example source.",
            }]}), encoding="utf-8")
            loaded = load_seed_captures(path)
            self.assertEqual(len(loaded), 1)
            self.assertEqual(loaded[0].source_kind, "independent_reporting")

    def test_live_shadow_does_not_research_topic_lead_holds(self):
        class HoldTopicModel:
            def __init__(self):
                self.calls = []

            def complete(self, stage, payload):
                self.calls.append(stage)
                response = topic_proposal()
                response["requested_disposition"] = "hold"
                return response

        model = HoldTopicModel()
        result = run_research_shadow(topic_context(), (), angle_id="timeline-delay",
                                     research_policy={}, model=model)
        self.assertEqual(result["status"], "topic_lead_held")
        self.assertEqual(model.calls, ["topic_lead"])
        self.assertFalse(result["publication_enabled"])
        self.assertEqual(result["process_events"][0]["stage"], "topic_lead")
        self.assertFalse(result["process_overseer"]["proposals"])


if __name__ == "__main__":
    unittest.main()
