"""Explicit opt-in public-research shadow run: no publication or outreach."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

from .agent_sources import (BlueskySearch, CrossrefSearch, GDELTSearch,
                            PolymarketComments, PublicJSONTransport)
from .handoff_contract import HandoffContractGateway
from .evidence_verifier import EvidenceVerifier, ModelClaimReview
from .investigator_v3 import (InvestigatorV3, ResearchCapture,
                              assignment_from_topic_lead)
from .research_retrieval import (MultiSourceResearchProvider, OfficialFeedSearch,
                                 PolymarketDiscussionSearch, PublicOfficialFeedTransport)
from .source_capture import HostPermission, SourceCaptureGateway
from .topic_lead import TopicLeadAgent
from .oversight import ProcessFailureEvent, ProcessOverseer
from .evaluation_harness import ResearchTestFixture, evaluate_topic_fixture


def load_seed_captures(path: str | Path) -> tuple[ResearchCapture, ...]:
    """Consume either explicit captures or the existing private source-capture rows."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    rows = raw if isinstance(raw, list) else raw.get("source_rows", raw.get("captures", []))
    if not isinstance(rows, list) or not 1 <= len(rows) <= 15:
        raise ValueError("Invalid or unbounded seed-capture packet")
    captures = []
    for item in rows:
        if not isinstance(item, dict):
            raise ValueError("Malformed capture entry")
        if "source_kind" in item:
            captures.append(ResearchCapture(**item))
        else:
            published = item["published_at"]
            if isinstance(published, str):
                published = int(datetime.fromisoformat(
                    published.replace("Z", "+00:00")).timestamp())
            captures.append(ResearchCapture(
                source_id=item["source_id"], url=item["url"], publisher=item["publisher"],
                origin_key=item["independent_origin"], published_at=published,
                captured_at=item["captured_at"], source_kind=item["kind"],
                excerpt=item["captured_excerpt"],
                document_sha256=item.get("document_sha256", ""),
                content_location=item.get("content_location", ""),
                mime_type=item.get("mime_type", ""),
                publication_date_basis=item.get("publication_date_basis", ""),
            ))
    return tuple(captures)


def configure_research_sources(policy: dict) -> MultiSourceResearchProvider:
    """Build bounded adapters from a strictly validated owner-supplied policy."""
    if not isinstance(policy, dict) or set(policy) - {
            "publishers", "official_feeds", "enable_bluesky", "enable_crossref",
            "polymarket_event_id", "polymarket_event_slug"}:
        raise ValueError("Unknown research policy key")
    publishers = policy.get("publishers", [])
    feeds = tuple(policy.get("official_feeds", ()))
    if (not isinstance(publishers, list) or not 1 <= len(publishers) <= 30 or
            any(not isinstance(row, dict) or
                not {"host", "kind", "copyright_basis"} <= set(row) or
                set(row) - {"host", "kind", "copyright_basis", "max_capture_bytes"}
                for row in publishers) or
            not isinstance(policy.get("enable_bluesky", True), bool) or
            not isinstance(policy.get("enable_crossref", True), bool)):
        raise ValueError("Invalid publisher or social source policy")
    gateway = SourceCaptureGateway(tuple(HostPermission(**row) for row in publishers))
    transport = PublicJSONTransport(timeout=8, retries=0)
    connectors = {"gdelt_news": GDELTSearch(transport)}
    if feeds:
        if any(not isinstance(feed, str) for feed in feeds):
            raise ValueError("Invalid official feed list")
        allowed_hosts = tuple(sorted({urlsplit(url).hostname or "" for url in feeds}))
        connectors["official_feeds"] = OfficialFeedSearch(
            feeds, PublicOfficialFeedTransport(allowed_hosts))
    if policy.get("enable_bluesky", True):
        connectors["bluesky"] = BlueskySearch(transport)
    if policy.get("enable_crossref", True):
        connectors["crossref"] = CrossrefSearch(transport)
    event_id, event_slug = policy.get("polymarket_event_id"), policy.get("polymarket_event_slug")
    if event_id or event_slug:
        if not (isinstance(event_id, str) and isinstance(event_slug, str)):
            raise ValueError("Polymarket event requires ID and slug")
        connectors["polymarket_chat"] = PolymarketDiscussionSearch(
            PolymarketComments(transport), event_id, event_slug)
    return MultiSourceResearchProvider(connectors, gateway)


def run_research_shadow(context, captures: tuple[ResearchCapture, ...],
                        *, angle_id: str, research_policy: dict, model,
                        test_fixture: ResearchTestFixture | None = None) -> dict:
    """Live-readonly source collection + model stages only when caller opts in."""
    if angle_id == "auto:first" and test_fixture is None:
        raise ValueError("Automatic angle choice is permitted only in evaluation fixtures")
    events: list[ProcessFailureEvent] = []

    def log(stage: str, reason: str, *, score=None, sources=None, findings=None):
        events.append(ProcessFailureEvent(
            case_id=context.story_id, stage=stage, reason_code=reason,
            investigator_self_score=score, source_count=sources, finding_count=findings))

    def annotated(payload: dict) -> dict:
        # Observational sidecar: its output never changes the return disposition.
        return {**payload, "process_events": [asdict(e) for e in events],
                "process_overseer": ProcessOverseer().diagnose(events)}

    topic = (evaluate_topic_fixture(model, context, test_fixture)
             if test_fixture is not None else TopicLeadAgent(model).assess(context))
    if topic.disposition != "go":
        log("topic_lead", "topic_lead_" + topic.disposition)
        return annotated({"case_id": context.story_id, "topic_lead": topic.to_dict(),
                          "investigator": None, "handoff_contract": None,
                          "evidence_verifier": None, "status": "topic_lead_held",
                          "publication_enabled": False,
                          "evaluation_only": bool(test_fixture)})
    # Evaluation should test what the Topic Lead actually proposes. Select its
    # first candidate deterministically; do not invent or guess its angle ID.
    selected_angle_id = topic.angles[0].angle_id if angle_id == "auto:first" else angle_id
    assignment = assignment_from_topic_lead(context, topic, captures,
                                            angle_id=selected_angle_id, research_mode="live_shadow")
    research = configure_research_sources(research_policy)
    investigation = InvestigatorV3(model, research).run(assignment)
    all_captures = tuple({s.source_id: s for s in captures + tuple(research.captures.values())}.values())
    findings = ((investigation.get("dossier") or {}).get("findings") or [])
    log("investigator_v3", str(investigation.get("disposition", "unavailable")),
        score=(investigation.get("completed_rubric") or {}).get("total"),
        sources=len(all_captures), findings=len(findings))
    contract = HandoffContractGateway().validate(investigation, all_captures,
                                                  as_of=context.as_of,
                                                  expected_case_id=context.story_id)
    for issue in contract.issues:
        log("contract_gateway", issue.reason_code)
    if not contract.issues:
        log("contract_gateway", "contract_passed")
    # Only the Verifier performs semantic review; it never runs on a rejected
    # handoff. Neither its provisional judgment nor a contract pass publishes.
    verification = (EvidenceVerifier(ModelClaimReview(model)).verify(
        investigation, all_captures, contract, coverage_summary=assignment.coverage_summary)
        if contract.status == "to_verifier" else None)
    if verification:
        for issue in verification.issues:
            log("dossier_verifier", issue.reason_code)
        if not verification.issues:
            log("dossier_verifier", "provisionally_verified")
    return annotated({"case_id": context.story_id, "topic_lead": {
                "disposition": topic.disposition, "score": topic.score,
                "selected_angle_id": selected_angle_id},
            "investigator": investigation,
            "handoff_contract": contract.to_dict(),
            "evidence_verifier": verification.to_dict() if verification else None,
            "status": "provisionally_verified_for_editorial_review"
                      if verification and verification.status == "provisionally_verified"
                      else "held_pending_research_or_review",
            "publication_enabled": False, "human_factcheck_attested": False,
            "evaluation_only": bool(test_fixture)})
