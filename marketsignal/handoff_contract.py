"""Deterministic Investigator -> Verifier contract validation.

This gateway checks artifact identity, provenance, and references. It never
decides whether quoted evidence *entails* a claim; that is Verifier work.
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass

from .investigator_v3 import RELIABLE_SOURCE_KINDS, ResearchCapture


@dataclass(frozen=True)
class ContractIssue:
    claim_id: str
    reason_code: str
    evidence_ref: str
    next_check: str


@dataclass(frozen=True)
class HandoffContractResult:
    case_id: str
    status: str  # to_verifier | return_to_investigator
    issues: tuple[ContractIssue, ...]
    claims_checked: int
    check_kind: str = "deterministic_contract_only"
    publication_enabled: bool = False
    authenticated_human_factcheck: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


class HandoffContractGateway:
    """Fail-closed structure and provenance checks, with zero model calls."""

    def validate(self, investigation: dict, captures: tuple[ResearchCapture, ...],
                 *, as_of: int | None = None,
                 expected_case_id: str | None = None) -> HandoffContractResult:
        if not isinstance(investigation, dict):
            return HandoffContractResult("", "return_to_investigator", (
                ContractIssue("", "invalid_investigation_packet", "",
                              "Supply a typed Investigator artifact"),), 0)
        case_id = investigation.get("case_id", "")
        issues: list[ContractIssue] = []

        def issue(code: str, *, claim_id: str = "", source_id: str = "", next_check: str = ""):
            issues.append(ContractIssue(claim_id, code, source_id, next_check or
                                        "Correct the source-bound handoff and retry"))

        if not isinstance(case_id, str) or not case_id.strip():
            issue("invalid_case_identity")
            case_id = ""
        if expected_case_id is not None and case_id != expected_case_id:
            issue("case_identity_mismatch")
        if (investigation.get("disposition") != "ready_for_verifier" or
                investigation.get("publication_enabled") is not False):
            issue("investigation_not_ready")
        if (as_of is not None and (not isinstance(as_of, int) or as_of <= 0)):
            issue("invalid_as_of")
            as_of = None

        if (not isinstance(captures, tuple) or not captures or len(captures) > 30 or
                any(not isinstance(s, ResearchCapture) for s in captures)):
            issue("invalid_source_packet")
            captures = ()
        source_map = {s.source_id: s for s in captures}
        if len(source_map) != len(captures):
            issue("duplicate_source_identity")
        if as_of is not None and any(s.published_at > as_of for s in captures):
            issue("source_postdates_case_as_of")

        source_ids = investigation.get("source_ids")
        manifest_rows = investigation.get("source_manifest")
        if (not isinstance(source_ids, list) or
                any(not isinstance(sid, str) for sid in source_ids) or
                len(source_ids) != len(set(source_ids)) or set(source_ids) != set(source_map)):
            issue("source_id_set_mismatch")
        if (not isinstance(manifest_rows, list) or
                any(not isinstance(row, dict) or not isinstance(row.get("source_id"), str)
                    for row in manifest_rows)):
            issue("source_manifest_mismatch")
            manifest_rows = []
        manifest = {row["source_id"]: row for row in manifest_rows}
        if (len(manifest) != len(manifest_rows) or set(manifest) != set(source_map) or
                any(row.get("excerpt_sha256") != hashlib.sha256(
                    source_map[sid].excerpt.encode("utf-8")).hexdigest() or
                    row.get("published_at") != source_map[sid].published_at or
                    row.get("captured_at") != source_map[sid].captured_at or
                    row.get("source_kind") != source_map[sid].source_kind or
                    row.get("origin_key") != source_map[sid].origin_key or
                    (as_of is not None and row.get("captured_after_case_as_of") !=
                     (source_map[sid].captured_at > as_of))
                    for sid, row in manifest.items() if sid in source_map)):
            issue("source_manifest_mismatch")

        dossier = investigation.get("dossier")
        findings = dossier.get("findings") if isinstance(dossier, dict) else None
        if not isinstance(findings, list) or not findings or len(findings) > 30:
            issue("missing_material_claims")
            findings = []
        seen_claims: set[str] = set()
        for claim in findings:
            if not isinstance(claim, dict):
                issue("malformed_claim")
                continue
            cid = claim.get("claim_id")
            if (not isinstance(cid, str) or not cid.isidentifier() or cid in seen_claims or
                    not isinstance(claim.get("statement"), str) or
                    len(claim["statement"].strip()) < 25 or
                    claim.get("certainty") not in {"reported", "attributed_hypothesis"}):
                issue("malformed_or_duplicate_claim", claim_id=str(cid or ""))
            if isinstance(cid, str):
                seen_claims.add(cid)
            citations = claim.get("source_ids")
            if (not isinstance(citations, list) or not citations or
                    any(not isinstance(sid, str) for sid in citations) or
                    len(citations) != len(set(citations)) or
                    not set(citations) <= set(source_map) or
                    any(source_map[sid].source_kind not in RELIABLE_SOURCE_KINDS
                        for sid in citations if sid in source_map)):
                issue("unavailable_cited_source", claim_id=str(cid or ""))

        # Catch broken cross-references and time fields introduced after the
        # Investigator's original schema validation. Do not judge claim truth.
        if isinstance(dossier, dict):
            def valid_refs(refs, *, require_nonempty=False):
                return (isinstance(refs, list) and
                        (not require_nonempty or bool(refs)) and
                        all(isinstance(cid, str) for cid in refs) and
                        set(refs) <= seen_claims)

            timeline = dossier.get("timeline")
            if (not isinstance(timeline, list) or len(timeline) < 2 or
                    any(not isinstance(row, dict) or
                        not isinstance(row.get("at"), int) or row["at"] <= 0 or
                        (as_of is not None and row["at"] > as_of) or
                        not valid_refs(row.get("claim_ids"), require_nonempty=True)
                        for row in timeline)):
                issue("invalid_timeline_reference")
            hypotheses = dossier.get("hypotheses")
            if (not isinstance(hypotheses, list) or not hypotheses or
                    any(not isinstance(row, dict) or
                        not valid_refs(row.get("supporting_claim_ids"), require_nonempty=True) or
                        not valid_refs(row.get("counter_claim_ids"))
                        for row in hypotheses)):
                issue("invalid_hypothesis_reference")
            pitches = dossier.get("pitches")
            if (not isinstance(pitches, list) or not pitches or
                    any(not isinstance(row, dict) or
                        not valid_refs(row.get("supporting_claim_ids"), require_nonempty=True) or
                        not valid_refs(row.get("contrary_claim_ids"), require_nonempty=True)
                        for row in pitches)):
                issue("invalid_pitch_reference")

        return HandoffContractResult(case_id,
                                     "return_to_investigator" if issues else "to_verifier",
                                     tuple(issues), len(findings))
