"""Explicit opt-in public-research shadow run: no publication or outreach."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

from .agent_sources import (BlueskySearch, CrossrefSearch, GDELTSearch,
                            PolymarketComments, PublicJSONTransport)
from .handoff_oversight import HandoffOverseer, ModelClaimReview
from .investigator_v3 import (InvestigatorV3, ResearchCapture,
                              assignment_from_topic_lead)
from .research_retrieval import (MultiSourceResearchProvider, OfficialFeedSearch,
                                 PolymarketDiscussionSearch, PublicOfficialFeedTransport)
from .source_capture import HostPermission, SourceCaptureGateway
from .topic_lead import TopicLeadAgent


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
            any(not isinstance(row, dict) or set(row) !=
                {"host", "kind", "copyright_basis"} for row in publishers) or
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
                        *, angle_id: str, research_policy: dict, model) -> dict:
    """Live-readonly source collection + model stages only when caller opts in."""
    topic = TopicLeadAgent(model).assess(context)
    if topic.disposition != "go":
        return {"case_id": context.story_id, "topic_lead": topic.to_dict(),
                "investigator": None, "handoff_overseer": None,
                "status": "topic_lead_held", "publication_enabled": False}
    assignment = assignment_from_topic_lead(context, topic, captures,
                                            angle_id=angle_id, research_mode="live_shadow")
    research = configure_research_sources(research_policy)
    investigation = InvestigatorV3(model, research).run(assignment)
    all_captures = tuple({s.source_id: s for s in captures + tuple(research.captures.values())}.values())
    overseer = HandoffOverseer(ModelClaimReview(model)).review(
        investigation, all_captures, coverage_summary=assignment.coverage_summary)
    return {"case_id": context.story_id, "topic_lead": {
                "disposition": topic.disposition, "score": topic.score,
                "selected_angle_id": angle_id},
            "investigator": investigation,
            "handoff_overseer": overseer.to_dict(),
            "status": "provisionally_ready_for_verifier" if overseer.status == "to_verifier"
                      else "held_pending_research_or_review",
            "publication_enabled": False, "human_factcheck_attested": False}
