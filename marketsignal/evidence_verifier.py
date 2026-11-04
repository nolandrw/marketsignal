"""Independent source-meaning review inside the Verifier stage.

This is a provisional machine judgment, never a human fact-check or a release
approval. Structural eligibility is checked by HandoffContractGateway first.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Protocol

from .handoff_contract import ContractIssue, HandoffContractResult
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
    """Model adapter for the single, independent dossier evidence Verifier."""

    def __init__(self, model):
        self.model = model

    def assess(self, claims: tuple[dict, ...], sources: tuple[ResearchCapture, ...],
               coverage_summary: str) -> tuple[ClaimJudgment, ...]:
        # Deliberately omit the Investigator's self-score, pitch and disposition.
        result = self.model.complete("dossier_evidence_verifier", {
            "claims": list(claims), "sources": [asdict(s) for s in sources],
            "coverage_summary": coverage_summary,
            "instruction": "Check entailment, contradictions and material omissions",
        })
        return tuple(ClaimJudgment(**item) for item in result["judgments"])


@dataclass(frozen=True)
class EvidenceReviewResult:
    case_id: str
    status: str  # provisionally_verified | return_to_investigator | awaiting_independent_verifier
    issues: tuple[ContractIssue, ...]
    claims_reviewed: int
    review_kind: str = "independent_provisional_model_not_human_attested"
    publication_enabled: bool = False
    authenticated_human_factcheck: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


class EvidenceVerifier:
    """Substantively inspect every finding after a passing contract gateway."""

    def __init__(self, reviewer: IndependentClaimReview | None = None):
        self.reviewer = reviewer

    def verify(self, investigation: dict, captures: tuple[ResearchCapture, ...],
               contract: HandoffContractResult, *, coverage_summary: str) -> EvidenceReviewResult:
        case_id = investigation.get("case_id", "")
        if (not isinstance(contract, HandoffContractResult) or contract.case_id != case_id or
                contract.status != "to_verifier" or contract.issues or
                contract.publication_enabled or investigation.get("disposition") != "ready_for_verifier"):
            return EvidenceReviewResult(case_id, "return_to_investigator", (
                ContractIssue("", "invalid_verifier_entry", "", "Pass a valid contract gateway first"),), 0)
        if self.reviewer is None:
            return EvidenceReviewResult(case_id, "awaiting_independent_verifier", (
                ContractIssue("", "independent_verifier_unavailable", "",
                              "Run an independent, source-first Verifier"),), 0)

        claims = investigation["dossier"]["findings"]
        source_map = {s.source_id: s for s in captures}
        issues: list[ContractIssue] = []
        try:
            judgments = self.reviewer.assess(tuple({
                "claim_id": c["claim_id"], "statement": c["statement"],
                "source_ids": c["source_ids"], "certainty": c["certainty"]} for c in claims),
                captures, coverage_summary)
            if (not isinstance(judgments, tuple) or
                    len(judgments) != len({r.claim_id for r in judgments}) or
                    {r.claim_id for r in judgments} != {c["claim_id"] for c in claims}):
                raise ValueError("Incomplete or duplicate verifier judgments")
            by_id = {r.claim_id: r for r in judgments}
            for claim in claims:
                result = by_id[claim["claim_id"]]
                src = source_map.get(result.source_id)
                if (result.verdict not in {"supported", "contradicted", "insufficient"} or
                        not isinstance(result.rationale, str) or
                        not 20 <= len(result.rationale.strip()) <= 750 or
                        result.source_id not in claim["source_ids"] or src is None or
                        not isinstance(result.exact_evidence, str) or
                        not result.exact_evidence.strip() or
                        result.exact_evidence not in src.excerpt):
                    issues.append(ContractIssue(claim["claim_id"], "verifier_citation_invalid",
                                                str(result.source_id),
                                                "Recheck original passage and attribution"))
                elif result.verdict != "supported":
                    issues.append(ContractIssue(claim["claim_id"], "claim_" + result.verdict,
                                                result.source_id,
                                                "Correct, qualify, or remove the finding"))
        except (KeyError, TypeError, ValueError, AttributeError, TimeoutError, RuntimeError, OSError):
            issues.append(ContractIssue("", "independent_verifier_failure", "",
                                        "Retry under the bounded verifier budget"))
        return EvidenceReviewResult(case_id,
                                    "return_to_investigator" if issues else "provisionally_verified",
                                    tuple(issues),
                                    0 if any(i.reason_code == "independent_verifier_failure" for i in issues)
                                    else len(claims))
