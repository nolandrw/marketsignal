"""Two-tier, evidence-bounded Investigator v3 orchestration (private shadow only).

The research adapter is read-only and explicitly injected. This module cannot
contact people, browse by itself, authenticate claims, certify model scores or
publish. It validates handoffs and saves provisional scoring evidence; actual
research retrieval and human/editorial grading are separate integrations.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass
from typing import Protocol
from urllib.parse import urlsplit


PRELIMINARY_CRITERIA = {
    "unanswered_question": 10, "credible_evidence_path": 10,
    "material_information_gain": 10, "specific_development": 10,
    "distinct_angle": 10, "reader_premise": 5,
    "alternative_explanation": 8, "discriminating_test": 8,
    "abandonment_condition": 4, "affected_parties": 5,
    "impact_magnitude": 5, "timely_relevance": 5,
    "source_access": 4, "bounded_scope": 3, "ethical_access": 3,
}
COMPLETED_CRITERIA = {
    "claim_provenance": 10, "timeline_integrity": 8, "independent_origins": 7,
    "meaningful_finding_or_negative_result": 10, "coverage_delta": 10,
    "reproducible_analysis": 5, "alternative_theories": 6,
    "actual_disconfirmation": 10, "residual_uncertainty": 4,
    "concrete_consequences": 8, "defensible_editorial_decision": 8,
    "contextual_timeliness": 4, "source_log": 4,
    "resource_proportionality": 3, "actionable_tickets": 3,
}
assert sum(PRELIMINARY_CRITERIA.values()) == 100
assert sum(COMPLETED_CRITERIA.values()) == 100

PRELIMINARY_GUIDANCE = {
    "unanswered_question": "A specific material question not resolved by existing reporting; cite the coverage comparison.",
    "credible_evidence_path": "A named public record, dataset or reputable independent source likely to answer the question.",
    "material_information_gain": "A plausible answer would substantively change understanding; not a new phrasing of known facts.",
    "specific_development": "A dated real-world development or testable original analysis, independent of trading movement.",
    "distinct_angle": "A concrete contribution different from previously reported angles, with coverage comparison.",
    "reader_premise": "A specific honest question/headline about the world, not market mechanics or unexplained uncertainty.",
    "alternative_explanation": "A realistic rival or null explanation, without manufacturing false equivalence.",
    "discriminating_test": "An observable document/data check capable of distinguishing explanations.",
    "abandonment_condition": "The specific observation that would invalidate or seriously weaken the original thesis.",
    "affected_parties": "Identifiable people, institutions or communities with direct exposure, not 'the public'.",
    "impact_magnitude": "Concrete potential stakes with a supported or explicitly bounded scale; not generic importance.",
    "timely_relevance": "Why a new decision, deadline or change matters now, independent of market price.",
    "source_access": "A lawful accessible route to relevant primary or independent sources; name actual leads.",
    "bounded_scope": "A focused test answerable within remaining read-only search, time and tool budgets.",
    "ethical_access": "Identify exposure to privacy, allegations, access limits, licensing and vulnerable parties.",
}
COMPLETED_GUIDANCE = {
    "claim_provenance": "Each material conclusion points to captured original or attributable evidence; check entailment.",
    "timeline_integrity": "Event ordering and prior expectations have dated source support, including no future leakage.",
    "independent_origins": "Important findings use genuinely independent origins where appropriate, not copied coverage.",
    "meaningful_finding_or_negative_result": "New supported insight OR a well-supported disproof of the starting story thesis.",
    "coverage_delta": "Names the exact incremental finding versus previously available reporting.",
    "reproducible_analysis": "A reviewer can retrace comparison, calculations and source references.",
    "alternative_theories": "Credible rival/null accounts are articulated in proportion to their evidence.",
    "actual_disconfirmation": "Specific evidence was inspected to test/reject theories; proposed checks alone are insufficient.",
    "residual_uncertainty": "Known unknowns and dissenting evidence are clearly distinguished from established findings.",
    "concrete_consequences": "Specific affected parties, mechanisms and magnitudes are supported or qualified.",
    "defensible_editorial_decision": "Ready/HOLD/SPIKE/return-for-new-topic follows from evidence, not the model's enthusiasm.",
    "contextual_timeliness": "The factual 'why now' and prior view are clear without inferring causation from odds.",
    "source_log": "Search paths, source IDs, capture dates and failed avenues are inspectable for review.",
    "resource_proportionality": "Research effort is justified by information gained, rather than simply minimizing calls.",
    "actionable_tickets": "Outstanding work has a testable question, required evidence and retry/revisit trigger.",
}
assert set(PRELIMINARY_GUIDANCE) == set(PRELIMINARY_CRITERIA)
assert set(COMPLETED_GUIDANCE) == set(COMPLETED_CRITERIA)

SCORING_ANCHORS = {
    "none": "0 points: criterion absent, contradicted or merely asserted with no traceable support.",
    "partial": "Half points: a material part is supported, with a specific remaining gap.",
    "full": "Full points: the specified outcome is substantiated by linked evidence and no material gap remains.",
}


def rubric_contract(stage: str) -> dict:
    """Stable, visible criterion descriptions supplied to model and evaluator."""
    if stage == "preliminary":
        weights, definitions = PRELIMINARY_CRITERIA, PRELIMINARY_GUIDANCE
    elif stage == "completed":
        weights, definitions = COMPLETED_CRITERIA, COMPLETED_GUIDANCE
    else:
        raise ValueError("Unknown Investigator rubric stage")
    return {"rubric_version": "investigator-v3.0", "stage": stage,
            "anchor_policy": SCORING_ANCHORS,
            "criteria": {key: {"maximum": value, "full_credit_definition": definitions[key]}
                         for key, value in weights.items()},
            "independent_editorial_grading": False}

DEEP_THRESHOLD = 70
COMPLETED_REVIEW_THRESHOLD = 75
MAX_LIVE_CAPTURE_DELAY = 30 * 60
RELIABLE_SOURCE_KINDS = {"official_record", "original_research", "independent_reporting", "statement"}
ALLOWED_SOURCE_KINDS = RELIABLE_SOURCE_KINDS | {"social_comment", "market_comment"}
ARTIFACT_EVIDENCE_REFS = {"artifact:research_plan", "artifact:coverage_index", "artifact:research_log"}


@dataclass(frozen=True)
class ResearchCapture:
    source_id: str
    url: str
    publisher: str
    origin_key: str
    published_at: int
    captured_at: int
    source_kind: str
    excerpt: str
    document_sha256: str = ""
    content_location: str = ""
    mime_type: str = ""
    publication_date_basis: str = ""

    def __post_init__(self):
        try:
            parts = urlsplit(self.url)
            safe_url = parts.scheme == "https" and bool(parts.hostname) and not (
                parts.username or parts.password or parts.fragment)
        except ValueError:
            safe_url = False
        if (not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,59}", self.source_id) or
                not safe_url or len(self.url) > 1500 or
                not self.publisher.strip() or not self.origin_key.strip() or
                self.source_kind not in ALLOWED_SOURCE_KINDS or
                not 0 < self.published_at <= self.captured_at or
                not 30 <= len(self.excerpt) <= 2500 or
                (self.document_sha256 and not re.fullmatch(r"[0-9a-f]{64}", self.document_sha256)) or
                len(self.content_location) > 500 or len(self.mime_type) > 80 or
                len(self.publication_date_basis) > 90):
            raise ValueError("Invalid dated investigative source capture")


@dataclass(frozen=True)
class InvestigatorAssignment:
    case_id: str
    as_of: int
    topic: str
    topic_lead_angle: str
    topic_lead_disposition: str
    topic_lead_score: int
    coverage_summary: str
    seed_sources: tuple[ResearchCapture, ...]
    research_questions: tuple[str, ...] = ()
    research_mode: str = "historical_replay"  # or live_shadow

    def __post_init__(self):
        if (not self.case_id or not self.topic.strip() or
                not self.topic_lead_angle.strip() or
                not isinstance(self.as_of, int) or self.as_of <= 0 or
                self.research_mode not in {"historical_replay", "live_shadow"} or
                len(self.seed_sources) > 15 or
                len(self.research_questions) > 12 or
                any(not isinstance(q, str) or not q.strip() or len(q) > 500
                    for q in self.research_questions) or
                any(s.published_at > self.as_of or
                    s.captured_at > self.as_of + (MAX_LIVE_CAPTURE_DELAY
                                                  if self.research_mode == "live_shadow" else 0)
                    for s in self.seed_sources) or
                len({s.source_id for s in self.seed_sources}) != len(self.seed_sources)):
            raise ValueError("Invalid Investigator assignment or source clock")


def assignment_from_topic_lead(context, assessment, captures: tuple[ResearchCapture, ...],
                               *, angle_id: str,
                               research_mode: str = "historical_replay") -> InvestigatorAssignment:
    """Create a typed investigation brief without upgrading metadata to evidence.

    Source IDs must match the captured, dated material already shown to the
    Topic Lead. This bridge does not fetch documents or choose among angles.
    """
    if (assessment.disposition != "go" or context.story_id != assessment.story_id or
            not context.coverage_checked or not angle_id):
        raise ValueError("Unapproved or unreviewed Topic Lead handoff")
    selected = [a for a in assessment.angles if a.angle_id == angle_id]
    if len(selected) != 1:
        raise ValueError("Investigator angle must be explicitly selected")
    angle = selected[0]
    metadata = {s.source_id: s for s in context.sources}
    captured = {s.source_id: s for s in captures}
    source_kind_map = {
        "primary_record": "official_record",
        "independent_reporting": "independent_reporting",
        "public_statement": "statement",
        "social_comment": "social_comment", "market_comment": "market_comment",
    }
    if len(captures) != len(captured) or not set(angle.source_ids) <= set(captured):
        raise ValueError("Angle references evidence missing from the capture packet")
    for source in captures:
        lead = metadata.get(source.source_id)
        if (lead is None or source.url != lead.url or
                source.published_at != lead.published_at or
                source.origin_key != lead.origin_key or
                source.publisher != lead.publisher or
                source.source_kind != source_kind_map.get(lead.source_type)):
            raise ValueError("Topic Lead metadata differs from captured evidence")
    coverage = assessment.coverage_analysis + "\n" + "\n".join(
        f"{item.story_id}: {item.title} ({item.overlap})"
        for item in context.coverage_matches)
    return InvestigatorAssignment(
        case_id=context.story_id, as_of=context.as_of,
        topic=angle.central_question, topic_lead_angle=angle.working_headline,
        topic_lead_disposition=assessment.disposition,
        topic_lead_score=assessment.score, coverage_summary=coverage,
        seed_sources=captures, research_questions=assessment.research_questions,
        research_mode=research_mode,
    )


class InvestigatorModel(Protocol):
    def complete(self, stage: str, payload: dict) -> dict: ...


class ReadOnlyResearchProvider(Protocol):
    def search(self, query: str, *, as_of: int, limit: int) -> tuple[ResearchCapture, ...] | ResearchBatch: ...


@dataclass(frozen=True)
class ResearchLead:
    """Unverified search result: useful for hypothesis generation, never claim proof."""

    platform: str
    url: str
    title: str
    published_at: int
    source_role: str  # coverage | official_lead | research_lead | discussion
    origin_key: str = ""

    def __post_init__(self):
        if (self.source_role not in {"coverage", "official_lead", "research_lead", "discussion"}
                or not self.platform.strip() or not self.title.strip()
                or len(self.title) > 300 or not 0 < self.published_at
                or not self.url.startswith("https://") or len(self.url) > 1500):
            raise ValueError("Invalid discovery-only lead")


@dataclass(frozen=True)
class ResearchBatch:
    """Discovery hints and independently captured documents are kept separate."""

    captures: tuple[ResearchCapture, ...]
    leads: tuple[ResearchLead, ...]
    sources_attempted: tuple[str, ...] = ()
    source_errors: tuple[str, ...] = ()


def validate_scorecard(raw: object, weights: dict[str, int],
                       known_evidence: set[str],
                       source_ids: set[str] | None = None) -> dict:
    """Score anchors are mechanical; their journalistic merit remains unverified.

    Positive scores require actual referenced source/artifact IDs and rationales.
    A model cannot replace citations with its own confidence statement.
    """
    if not isinstance(raw, dict) or set(raw) != set(weights):
        raise ValueError("Missing or extra investigative rubric criteria")
    total = 0.0
    evaluated = {}
    source_required = {"credible_evidence_path", "specific_development", "source_access",
                       "claim_provenance", "timeline_integrity", "independent_origins"}
    for criterion, maximum in weights.items():
        item = raw[criterion]
        if not isinstance(item, dict) or set(item) != {"grade", "rationale", "evidence_refs"}:
            raise ValueError("Malformed rubric criterion")
        grade, rationale, references = item["grade"], item["rationale"], item["evidence_refs"]
        if (grade not in {"none", "partial", "full"} or not isinstance(rationale, str) or
                not 15 <= len(rationale.strip()) <= 600 or
                not isinstance(references, list) or len(references) > 8 or
                len(set(references)) != len(references) or
                any(not isinstance(ref, str) or ref not in known_evidence for ref in references) or
                (grade != "none" and not references)):
            raise ValueError("Unexplained, ungrounded or out-of-range rubric score")
        if (grade != "none" and criterion in source_required and source_ids is not None and
                not set(references) & source_ids):
            raise ValueError("Source-dependent score is not grounded in a source capture")
        points = maximum * {"none": 0, "partial": 0.5, "full": 1}[grade]
        total += points
        evaluated[criterion] = {"points": points, "maximum": maximum,
                                "grade": grade, "rationale": rationale,
                                "evidence_refs": tuple(references)}
    return {"total": total, "criteria": evaluated,
            "independently_validated": False, "type": "provisional_model_scoring"}


def _bounded_queries(raw: object, limit: int) -> tuple[str, ...]:
    if (not isinstance(raw, list) or not 1 <= len(raw) <= limit or
            len(set(raw)) != len(raw) or
            any(not isinstance(q, str) or not 8 <= len(q.strip()) <= 180 for q in raw)):
        raise ValueError("Invalid or unbounded research query plan")
    return tuple(raw)


def _validate_dossier(raw: object, sources: tuple[ResearchCapture, ...],
                      assignment: InvestigatorAssignment) -> tuple[str, ...]:
    """Deterministic claim/provenance and output-shape checks, NOT fact checking."""
    if not isinstance(raw, dict):
        return ("malformed_dossier",)
    issues = []
    ids = {s.source_id for s in sources}
    reliable = {s.source_id for s in sources if s.source_kind in RELIABLE_SOURCE_KINDS}
    try:
        findings = raw["findings"]
        timeline = raw["timeline"]
        hypotheses = raw["hypotheses"]
        pitches = raw["pitches"]
        open_questions = raw["open_questions"]
        departure = raw["departure_reason"]
        if not isinstance(raw["novelty_vs_coverage"], str) or len(raw["novelty_vs_coverage"].strip()) < 20:
            issues.append("missing_coverage_differentiation")
        if (not isinstance(findings, list) or len(findings) > 30 or
                not isinstance(timeline, list) or len(timeline) > 25 or
                not isinstance(hypotheses, list) or len(hypotheses) > 5 or
                not isinstance(pitches, list) or len(pitches) > 3 or
                not isinstance(open_questions, list) or len(open_questions) > 15 or
                not isinstance(departure, str) or len(departure) > 1500):
            return ("malformed_dossier",)
        claim_ids = set()
        for finding in findings:
            cid = finding["claim_id"]
            evidence = finding["source_ids"]
            if (not isinstance(cid, str) or not cid.isidentifier() or cid in claim_ids or
                    not isinstance(finding["statement"], str) or
                    len(finding["statement"].strip()) < 25 or
                    not isinstance(evidence, list) or not evidence or
                    not set(evidence) <= reliable or
                    finding["certainty"] not in {"reported", "attributed_hypothesis"}):
                issues.append("unsupported_or_duplicate_finding")
            claim_ids.add(cid)
        for event in timeline:
            if (not isinstance(event["at"], int) or not 0 < event["at"] <= assignment.as_of or
                    not isinstance(event["claim_ids"], list) or not event["claim_ids"] or
                    not set(event["claim_ids"]) <= claim_ids):
                issues.append("invalid_or_future_timeline")
        for hypothesis in hypotheses:
            if (not isinstance(hypothesis["theory"], str) or
                    len(hypothesis["theory"].strip()) < 20 or
                    not isinstance(hypothesis["test"], str) or
                    len(hypothesis["test"].strip()) < 20 or
                    not isinstance(hypothesis["supporting_claim_ids"], list) or
                    not isinstance(hypothesis["counter_claim_ids"], list) or
                    not set(hypothesis["supporting_claim_ids"] +
                            hypothesis["counter_claim_ids"]) <= claim_ids):
                issues.append("invalid_or_unsupported_hypothesis")
        for pitch in pitches:
            claim_refs = pitch["supporting_claim_ids"] + pitch["contrary_claim_ids"]
            if (not isinstance(pitch["working_headline"], str) or
                    not 15 <= len(pitch["working_headline"].strip()) <= 135 or
                    not isinstance(claim_refs, list) or not set(claim_refs) <= claim_ids or
                    not pitch["supporting_claim_ids"] or not pitch["contrary_claim_ids"] or
                    any(term in pitch["working_headline"].lower()
                        for term in ("polymarket", "kalshi", "betting odds"))):
                issues.append("unlinked_or_market_centered_pitch")
        if (raw["departure_type"] not in {"original", "reframed", "new_case"} or
                (raw["departure_type"] != "original" and not departure.strip())):
            issues.append("unexplained_assignment_departure")
        if raw["departure_type"] == "new_case" and raw["disposition"] == "ready_for_verifier":
            issues.append("unreviewed_new_topic")
        if (raw["disposition"] == "ready_for_verifier" and
                (not pitches or len(findings) < 3 or len(timeline) < 2 or
                 len({s.origin_key for s in sources if s.source_id in {
                     source_id for f in findings for source_id in f["source_ids"]
                 }}) < 2)):
            issues.append("insufficient_dossier_for_verifier")
        if raw["disposition"] == "spike" and (not findings or
                not isinstance(raw["reason"], str) or len(raw["reason"].strip()) < 25):
            issues.append("unsubstantiated_spike_decision")
        if (raw["disposition"] in {"hold", "spike"} and pitches):
            issues.append("uncommissionable_dossier_contains_pitches")
        if any(not isinstance(q, str) or not q.strip() for q in open_questions):
            issues.append("invalid_open_question")
    except (KeyError, TypeError, ValueError, AttributeError):
        issues.append("malformed_dossier")
    return tuple(sorted(set(issues)))


class InvestigatorV3:
    """Research-plan -> preliminary gate -> deep research -> source-bound dossier.

    Source discovery occurs only through a caller-provided read-only provider;
    this class has no credential or external-publication interfaces.
    """

    def __init__(self, model: InvestigatorModel, provider: ReadOnlyResearchProvider):
        self.model = model
        self.provider = provider

    def run(self, assignment: InvestigatorAssignment) -> dict:
        sources = {s.source_id: s for s in assignment.seed_sources}
        leads: dict[str, ResearchLead] = {}
        queries: list[str] = []
        trace: list[dict] = []

        def finish(disposition: str, reason: str, preliminary: dict | None = None,
                   completed: dict | None = None, dossier: dict | None = None) -> dict:
            return {"case_id": assignment.case_id, "disposition": disposition,
                    "rubric_version": "investigator-v3.0",
                    "reason": reason, "preliminary_rubric": preliminary,
                    "completed_rubric": completed, "dossier": dossier,
                    "source_ids": sorted(sources), "research_queries": queries,
                    "discovery_lead_counts": {
                        role: sum(lead.source_role == role for lead in leads.values())
                        for role in ("coverage", "official_lead", "research_lead", "discussion")
                    },
                    "source_manifest": [{"source_id": s.source_id, "published_at": s.published_at,
                                         "captured_at": s.captured_at, "source_kind": s.source_kind,
                                         "captured_after_case_as_of": s.captured_at > assignment.as_of,
                                         "origin_key": s.origin_key,
                                         "excerpt_sha256": hashlib.sha256(
                                             s.excerpt.encode("utf-8")).hexdigest()}
                                        for s in sources.values()],
                    "trace": trace, "publication_enabled": False,
                    "source_coverage_audit": (self.provider.coverage_audit()
                                              if callable(getattr(self.provider, "coverage_audit", None))
                                              else None),
                    "semantic_accuracy_certified": False}

        def search(batch: tuple[str, ...], stage: str) -> None:
            for query in batch:
                if len(queries) >= 8:
                    raise ValueError("Research call ceiling exceeded")
                retrieved = self.provider.search(query, as_of=assignment.as_of, limit=4)
                if isinstance(retrieved, ResearchBatch):
                    rows = retrieved.captures
                    if len(retrieved.leads) > 24 or len(leads) > 80:
                        raise ValueError("Unbounded discovery-only lead packet")
                    for lead in retrieved.leads:
                        if not isinstance(lead, ResearchLead) or lead.published_at > assignment.as_of:
                            raise ValueError("Undated discovery-only lead")
                        leads[lead.url] = lead
                    if len(leads) > 80:
                        raise ValueError("Discovery-only lead budget exhausted")
                else:
                    rows = retrieved
                if not isinstance(rows, (tuple, list)) or len(rows) > 4:
                    raise ValueError("Research provider returned unbounded results")
                queries.append(query)
                for row in rows:
                    if (not isinstance(row, ResearchCapture) or row.published_at > assignment.as_of or
                            row.captured_at > assignment.as_of + (MAX_LIVE_CAPTURE_DELAY
                                if assignment.research_mode == "live_shadow" else 0)):
                        raise ValueError("Undated or future research source")
                    if row.source_id in sources and sources[row.source_id] != row:
                        raise ValueError("Source ID changed meaning across research rounds")
                    if len(sources) >= 30 and row.source_id not in sources:
                        raise ValueError("Source capture budget exhausted")
                    sources[row.source_id] = row
                trace.append({"stage": stage, "query_count": 1,
                              "captures_seen": len(rows), "known_source_count": len(sources),
                              "discovery_leads_seen": len(retrieved.leads) if isinstance(retrieved, ResearchBatch) else 0,
                              "sources_attempted": list(retrieved.sources_attempted) if isinstance(retrieved, ResearchBatch) else [],
                              "source_errors": list(retrieved.source_errors) if isinstance(retrieved, ResearchBatch) else []})

        if assignment.topic_lead_disposition != "go" or assignment.topic_lead_score < 65:
            return finish("hold", "topic_lead_assignment_not_authorized")
        try:
            planning = self.model.complete("investigator_plan_v3", asdict(assignment))
            if not isinstance(planning, dict) or not planning.get("research_goal", "").strip():
                raise ValueError("Invalid investigation planning response")
            initial = _bounded_queries(planning["queries"], 3)
            search(initial, "initial_research")
            evidence = {**asdict(assignment), "sources": [asdict(s) for s in sources.values()],
                        "unverified_discovery_leads": [asdict(lead) for lead in leads.values()],
                        "research_plan": planning, "research_queries": queries,
                        "rubric_contract": rubric_contract("preliminary")}
            prelim_raw = self.model.complete("investigator_preliminary_v3", evidence)
            prelim = validate_scorecard(prelim_raw["scores"], PRELIMINARY_CRITERIA,
                                        set(sources) | ARTIFACT_EVIDENCE_REFS,
                                        set(sources))
            if prelim_raw["requested_disposition"] not in {"deep", "hold", "spike"}:
                raise ValueError("Unknown preliminary decision")
            if prelim_raw["requested_disposition"] != "deep":
                if not prelim_raw["reason"].strip():
                    raise ValueError("No rationale for stopping research")
                return finish(prelim_raw["requested_disposition"],
                              prelim_raw["reason"], prelim)
            # Self-reported scores cannot override these deterministic gates.
            if prelim["total"] < DEEP_THRESHOLD:
                return finish("hold", "below_preliminary_research_threshold", prelim)
            if any(prelim["criteria"][key]["grade"] == "none" for key in (
                "unanswered_question", "credible_evidence_path", "material_information_gain",
                "specific_development", "discriminating_test", "affected_parties"
            )):
                return finish("hold", "missing_critical_preliminary_criterion", prelim)
            if not any(s.source_kind in RELIABLE_SOURCE_KINDS for s in sources.values()):
                return finish("hold", "no_credible_external_research_path", prelim)
            if len(prelim_raw["discriminating_test"].strip()) < 25:
                return finish("hold", "no_falsifiable_deep_research_plan", prelim)
            deep = _bounded_queries(prelim_raw["next_queries"], 5)
            before_deep = set(sources)
            search(deep, "deep_research")
            # Until a separately executed/reproducible analysis artifact is
            # supported, model prose alone does not count as new deep evidence.
            if set(sources) == before_deep:
                return finish("hold", "deep_research_no_new_evidence", prelim)
            report_input = {**evidence, "sources": [asdict(s) for s in sources.values()],
                            "unverified_discovery_leads": [asdict(lead) for lead in leads.values()],
                            "deep_research_queries": deep,
                            "rubric_contract": rubric_contract("completed")}
            result = self.model.complete("investigator_dossier_v3", report_input)
            completed = validate_scorecard(result["scores"], COMPLETED_CRITERIA,
                                           set(sources) | ARTIFACT_EVIDENCE_REFS |
                                           {f["claim_id"] for f in result["findings"]},
                                           set(sources))
            issues = _validate_dossier(result, tuple(sources.values()), assignment)
            if issues:
                return finish("hold", "dossier_gate:" + ",".join(issues), prelim, completed)
            status = result["disposition"]
            if status not in {"ready_for_verifier", "hold", "spike"}:
                return finish("hold", "unknown_completed_disposition", prelim, completed)
            if status == "ready_for_verifier" and completed["total"] < COMPLETED_REVIEW_THRESHOLD:
                return finish("hold", "below_completed_dossier_threshold", prelim, completed)
            return finish(status, "provisional_dossier_ready" if status == "ready_for_verifier"
                          else result.get("reason", "research_concluded"),
                          prelim, completed, result)
        except (KeyError, TypeError, ValueError, AttributeError,
                TimeoutError, OSError, RuntimeError) as exc:
            trace.append({"stage": "fail_closed", "error_class": type(exc).__name__})
            return finish("hold", "investigator_contract_or_research_failure")
