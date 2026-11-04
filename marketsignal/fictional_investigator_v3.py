"""Fictional, zero-network v3 integration fixture for the active shadow demo.

This intentionally uses scripted answers to test Topic Lead -> Investigator v3
-> Contract Gateway -> Verifier without API charges. A scripted Verifier is
NEVER evidence that automated fact checking or real reporting has succeeded.
"""

from __future__ import annotations

from .handoff_contract import HandoffContractGateway
from .evidence_verifier import ClaimJudgment, EvidenceVerifier
from .investigator_v3 import (
    COMPLETED_CRITERIA, PRELIMINARY_CRITERIA, InvestigatorV3,
    ResearchBatch, ResearchCapture, ResearchLead, assignment_from_topic_lead,
)


KIND_MAP = {"primary_record": "official_record",
            "independent_reporting": "independent_reporting",
            "public_statement": "statement"}


def _grades(weights, source_id):
    return {key: {"grade": "full", "rationale":
                  "Fictional scripted evidence satisfies the structural criterion for this replay.",
                  "evidence_refs": [source_id]}
            for key in weights}


class FictionalResearch:
    def __init__(self, as_of):
        self.as_of = as_of
        self.new_document = ResearchCapture(
            "docket_2026", "https://example.org/fictional/docket-update",
            "Crescent Bay Clerk", "city-clerk", as_of - 1100, as_of,
            "official_record",
            "The city clerk's updated agenda confirms that the approval vote was deferred "
            "until the foundation assessment is completed and no replacement date has been set.",
        )

    def search(self, query, *, as_of, limit):
        if "updated docket" in query:
            return ResearchBatch((self.new_document,), (), ("fictional_docket",))
        return ResearchBatch((), (
            ResearchLead("fictional_bluesky", "https://bsky.app/profile/demo.test/post/1",
                         "Speculation about the engineering delay", as_of - 200,
                         "discussion", "anonymous"),
            ResearchLead("fictional_coverage", "https://example.org/fictional/prior-article",
                         "Older coverage of the proposed flood barrier", as_of - 100000,
                         "coverage", "fictional_newspaper"),
        ), ("fictional_public_search",))


class FictionalV3Model:
    def complete(self, stage, payload):
        if stage == "investigator_plan_v3":
            return {"research_goal": "Test whether engineering review changed the vote schedule",
                    "queries": ["coastal barrier public research records"]}
        if stage == "investigator_preliminary_v3":
            return {"requested_disposition": "deep", "reason": "Official docket may distinguish timelines",
                    "discriminating_test": "Compare engineering notice to the updated council docket",
                    "next_queries": ["updated docket for coastal barrier"],
                    "scores": _grades(PRELIMINARY_CRITERIA, "notice-2026")}
        if stage == "investigator_dossier_v3":
            return {
                "disposition": "ready_for_verifier", "reason": "Fictional original record is traceable",
                "departure_type": "original", "departure_reason": "",
                "novelty_vs_coverage": "The newly updated meeting docket establishes a date not in prior coverage.",
                "findings": [
                    {"claim_id": "delay", "statement": "The city delayed a flood barrier vote for another foundation review.",
                     "source_ids": ["notice-2026"], "certainty": "reported"},
                    {"claim_id": "prior", "statement": "The prior city planning memorandum had expected a winter decision.",
                     "source_ids": ["plan-2026"], "certainty": "reported"},
                    {"claim_id": "docket", "statement": "The fictional docket confirms no new approval date has been set.",
                     "source_ids": ["docket_2026"], "certainty": "reported"},
                    {"claim_id": "counter", "statement": "The engineering panel says the review does not establish design failure.",
                     "source_ids": ["review-2026"], "certainty": "reported"},
                ],
                "timeline": [
                    {"at": payload["sources"][0]["published_at"],
                     "event": "Initial planning timetable", "claim_ids": ["prior"]},
                    {"at": self._source_time(payload, "notice-2026"),
                     "event": "Vote was postponed", "claim_ids": ["delay"]},
                ],
                "hypotheses": [{
                    "theory": "Engineering questions changed the approval calendar",
                    "test": "Inspect dated engineering notice and compare the official updated docket",
                    "supporting_claim_ids": ["delay", "docket"], "counter_claim_ids": ["counter"],
                }],
                "pitches": [{
                    "pitch_id": "review_delay", "working_headline": "Flood Barrier Vote Delayed As Engineers Review Foundations",
                    "thesis": "Fictional city approval timeline has changed",
                    "conflict": "Scheduled action depends on unfinished engineering review",
                    "surprise": "The promised decision date has passed without replacement",
                    "why_now": "New official docket clarifies the revised schedule",
                    "stakes": "Fictional residents face a delayed infrastructure decision",
                    "original_value": "Dated public-record comparison instead of odds analysis",
                    "supporting_claim_ids": ["delay", "prior", "docket"],
                    "contrary_claim_ids": ["counter"],
                }],
                "open_questions": ["Will the city set a new vote before winter?"],
                "scores": _grades(COMPLETED_CRITERIA, "docket_2026"),
            }
        raise ValueError("Unexpected fictional Investigator model stage")

    @staticmethod
    def _source_time(payload, source_id):
        return next(s["published_at"] for s in payload["sources"] if s["source_id"] == source_id)


class FictionalIndependentReview:
    """Scripted shape test, explicitly not a semantic fact-check."""

    def assess(self, claims, sources, coverage_summary):
        lookup = {s.source_id: s for s in sources}
        return tuple(ClaimJudgment(
            claim_id=c["claim_id"], verdict="supported", source_id=c["source_ids"][0],
            exact_evidence=lookup[c["source_ids"][0]].excerpt[:40],
            rationale="The fictional source is scripted to substantiate the corresponding role.",
        ) for c in claims)


def run_fictional_v3_handoff(context, topic, documents):
    captures = tuple(ResearchCapture(
        doc.source_id, doc.url, doc.publisher, doc.independent_origin,
        doc.published_at, doc.captured_at, KIND_MAP[doc.source_kind], doc.content,
    ) for doc in documents)
    assignment = assignment_from_topic_lead(context, topic, captures, angle_id="review-delay")
    provider = FictionalResearch(context.as_of)
    result = InvestigatorV3(FictionalV3Model(), provider).run(assignment)
    originals = captures + (provider.new_document,)
    contract = HandoffContractGateway().validate(
        result, originals, as_of=context.as_of, expected_case_id=context.story_id)
    review = EvidenceVerifier(FictionalIndependentReview()).verify(
        result, originals, contract, coverage_summary=assignment.coverage_summary)
    return result, contract, review
