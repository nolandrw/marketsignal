"""Evidence-first overseer at the Investigator -> Verifier boundary.

Its separate assessment is not Investigator self-grading, nor is it a human
fact-check. The automation cannot authorize publication or rewrite prompts.
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from collections import Counter
from typing import Protocol, Sequence

from .investigator_v3 import ResearchCapture


@dataclass(frozen=True)
class ClaimJudgment:
    claim_id: str
    verdict: str  # supported | contradicted | insufficient
    source_id: str
    exact_evidence: str
    rationale: str


class IndependentClaimReview(Protocol):
    def assess(self, claims: tuple[dict, ...], sources: tuple[ResearchCapture, ...],
               coverage_summary: str) -> tuple[ClaimJudgment, ...]: ...


class ModelClaimReview:
    """Independent *model-stage* view of originals, not a human editorial label."""

    def __init__(self, model):
        self.model = model

    def assess(self, claims: tuple[dict, ...], sources: tuple[ResearchCapture, ...],
               coverage_summary: str) -> tuple[ClaimJudgment, ...]:
        # Crucially: no Investigator self-rubric, disposition, pitch or score.
        result = self.model.complete("handoff_evidence_review", {
            "claims": list(claims), "sources": [asdict(s) for s in sources],
            "coverage_summary": coverage_summary,
            "instruction": "Consider material omissions and contradictory passages independently",
        })
        return tuple(ClaimJudgment(**item) for item in result["judgments"])


@dataclass(frozen=True)
class HandoffIssue:
    claim_id: str
    reason_code: str
    evidence_ref: str
    next_check: str


@dataclass(frozen=True)
class HandoffReviewResult:
    case_id: str
    status: str  # to_verifier | return_to_investigator | awaiting_independent_review
    issues: tuple[HandoffIssue, ...]
    claims_reviewed: int
    review_kind: str
    publication_enabled: bool = False
    authenticated_human_factcheck: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


class HandoffOverseer:
    """Requires a source-first review; missing reviewer always fails closed."""

    def __init__(self, reviewer: IndependentClaimReview | None = None):
        self.reviewer = reviewer

    def review(self, investigation: dict, captures: tuple[ResearchCapture, ...],
               *, coverage_summary: str) -> HandoffReviewResult:
        case_id = investigation.get("case_id", "")
        if investigation.get("disposition") != "ready_for_verifier":
            return HandoffReviewResult(case_id, "return_to_investigator",
                                       (HandoffIssue("", "investigation_not_ready", "",
                                                     "Resolve the investigator hold or spike decision"),),
                                       0, "structural_only")
        dossier = investigation.get("dossier") or {}
        claims = dossier.get("findings") or []
        source_map = {s.source_id: s for s in captures}
        manifest = {row.get("source_id"): row for row in
                    investigation.get("source_manifest", ()) if isinstance(row, dict)}
        issues = []
        if (len(source_map) != len(captures) or
                set(investigation.get("source_ids", ())) != set(source_map) or
                set(manifest) != set(source_map) or
                any(row.get("excerpt_sha256") != hashlib.sha256(
                    source_map[sid].excerpt.encode("utf-8")).hexdigest() or
                    row.get("published_at") != source_map[sid].published_at or
                    row.get("captured_at") != source_map[sid].captured_at or
                    row.get("source_kind") != source_map[sid].source_kind or
                    row.get("origin_key") != source_map[sid].origin_key
                    for sid, row in manifest.items())):
            issues.append(HandoffIssue("", "source_manifest_mismatch", "",
                                       "Reconcile dossier captures with immutable source manifest"))
        if not isinstance(claims, list) or not claims:
            issues.append(HandoffIssue("", "missing_material_claims", "",
                                       "Supply material, source-linked findings"))
            claims = []
        for claim in claims:
            if (not isinstance(claim, dict) or
                    not isinstance(claim.get("source_ids"), list) or
                    not set(claim.get("source_ids", ())) <= set(source_map)):
                issues.append(HandoffIssue(str(claim.get("claim_id", "") if isinstance(claim, dict) else ""),
                                           "unavailable_cited_source", "",
                                           "Retrieve and independently inspect cited document"))
        if issues:
            return HandoffReviewResult(case_id, "return_to_investigator", tuple(issues),
                                       0, "structural_only")
        if self.reviewer is None:
            return HandoffReviewResult(case_id, "awaiting_independent_review",
                                       (HandoffIssue("", "no_independent_source_reviewer", "",
                                                     "Run a separate source-first review before handoff"),),
                                       0, "unavailable")
        try:
            # Do not send the Investigator's self-score or preferred pitch.
            judgments = self.reviewer.assess(tuple({
                "claim_id": c["claim_id"], "statement": c["statement"],
                "source_ids": c["source_ids"], "certainty": c["certainty"]} for c in claims),
                captures, coverage_summary)
            judged = {item.claim_id: item for item in judgments}
            if len(judgments) != len(judged) or set(judged) != {c["claim_id"] for c in claims}:
                raise ValueError("Review incomplete or duplicate")
            for claim in claims:
                result = judged[claim["claim_id"]]
                src = source_map.get(result.source_id)
                if (result.verdict not in {"supported", "contradicted", "insufficient"} or
                        not 20 <= len(result.rationale.strip()) <= 750 or
                        result.source_id not in claim["source_ids"] or src is None or
                        not result.exact_evidence.strip() or
                        result.exact_evidence not in src.excerpt):
                    issues.append(HandoffIssue(claim["claim_id"], "review_citation_invalid",
                                               result.source_id,
                                               "Re-review the original text and cite an exact passage"))
                elif result.verdict != "supported":
                    issues.append(HandoffIssue(claim["claim_id"],
                                               "claim_" + result.verdict, result.source_id,
                                               "Correct, qualify, or remove this material finding"))
        except (KeyError, TypeError, ValueError, AttributeError, TimeoutError, RuntimeError, OSError):
            issues.append(HandoffIssue("", "independent_review_failure", "",
                                       "Retry independent source-first review under budget"))
        return HandoffReviewResult(
            case_id, "return_to_investigator" if issues else "to_verifier",
            tuple(issues), len(claims) if not any(i.reason_code == "independent_review_failure"
                                                   for i in issues) else 0,
            "separate_model_or_review_adapter_not_human_attested",
        )


def diagnose_handoff_failures(reviews: Sequence[HandoffReviewResult], *,
                              minimum_cases: int = 5) -> dict:
    """Aggregate failures into versioned *proposals*, never self-modify prompts."""
    if minimum_cases < 3 or len({r.case_id for r in reviews}) != len(reviews):
        raise ValueError("Oversight needs distinct cases")
    counts = Counter(code for review in reviews for code in
                     {issue.reason_code for issue in review.issues})
    recurring = {code: count for code, count in counts.items() if count >= minimum_cases}
    return {"cases": len(reviews), "reason_counts": dict(counts),
            "review_kind": "handoff_operational_diagnostics_not_human_truth_labels",
            "proposals": [{"failure": code, "sample_count": count,
                           "action": "Investigate root cause; propose versioned policy/prompt change",
                           "owner_approval_required": True} for code, count in sorted(recurring.items())],
            "automatic_prompt_edits": False, "publication_enabled": False}
