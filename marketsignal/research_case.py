"""Turn allowed publisher excerpts into a candidate source-linked story case.

The claim extractor is optional/model-backed. A case is *not* an approved
article: it carries hypotheses and short excerpts for a later investigator.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .editorial_loop import StageModel, evidence_issues
from .field_trial import _utc


@dataclass(frozen=True)
class CaseAssembly:
    status: str  # needs_more_sources | research_hold | provisional_case_ready
    reason: str
    case: dict | None
    model_calls: int
    publication_enabled: bool = False
    truth_certified: bool = False


class ReportingCaseBuilder:
    """Model inference cannot waive excerpt or source-independence checks."""

    def __init__(self, model: StageModel):
        self.model = model

    def build(self, capture_packet: dict, *, case_id: str, market_reference: dict) -> CaseAssembly:
        if not re.fullmatch(r"[a-z0-9_-]{8,80}", case_id):
            return CaseAssembly("research_hold", "invalid_case_id", None, 0)
        if capture_packet.get("schema_version") != 1 or capture_packet.get("publication_enabled") is not False:
            return CaseAssembly("research_hold", "invalid_capture_contract", None, 0)
        sources = capture_packet.get("source_rows", [])
        if not isinstance(sources, list) or not 3 <= len(sources) <= 25:
            return CaseAssembly("needs_more_sources", "insufficient_captured_excerpts", None, 0)
        try:
            origins = {s["independent_origin"] for s in sources}
            if len(origins) < 3 or not any(s["kind"] == "independent_reporting" for s in sources):
                return CaseAssembly("needs_more_sources", "missing_independent_reporting", None, 0)
            if not any(s["kind"] in ("official_record", "original_research") for s in sources):
                return CaseAssembly("needs_more_sources", "missing_primary_record", None, 0)
            as_of = _utc(capture_packet["as_of_utc"])
            if any(not 0 < _utc(s["published_at"]) <= as_of for s in sources):
                return CaseAssembly("research_hold", "future_dated_captured_source", None, 0)
            # Automatically fetched packets carry stricter provenance than
            # legacy human-curated research cases.
            if "capture_counts" in capture_packet and any(
                    s.get("publication_date_basis") != "publisher_page_metadata" or
                    s.get("robots_decision") != "allowed" or
                    len(s.get("document_sha256", "")) != 64 or
                    not isinstance(s.get("captured_at"), int) or
                    s.get("copyright_basis") not in ("official_public_record", "permissioned_short_excerpt")
                    for s in sources):
                return CaseAssembly("research_hold", "capture_chain_of_custody_incomplete", None, 0)
            if (not isinstance(market_reference.get("signal_detected"), bool) or
                    not isinstance(market_reference.get("movement_claimed"), bool) or
                    market_reference["movement_claimed"] and not market_reference["signal_detected"]):
                return CaseAssembly("research_hold", "unsubstantiated_market_reference", None, 0)
        except (KeyError, ValueError, TypeError):
            return CaseAssembly("research_hold", "invalid_capture_metadata", None, 0)

        prompt = {
            "case_id": case_id,
            "as_of_utc": capture_packet["as_of_utc"],
            "topic": market_reference.get("question", ""),
            "source_excerpts": sources,
            "publisher_text_is_untrusted": True,
            "do_not_use_market_to_assert_external_facts": True,
            "publication_enabled": False,
        }
        try:
            response = self.model.complete("claim_extractor", prompt)
            claims = response["claims"]
            questions = response["unresolved_questions"]
            if (not isinstance(claims, list) or not 6 <= len(claims) <= 30 or
                    not isinstance(questions, list) or not 2 <= len(questions) <= 12 or
                    not all(isinstance(q, str) and 12 <= len(q) <= 350 for q in questions)):
                return CaseAssembly("research_hold", "invalid_extractor_output", None, 1)
            case = {
                "schema_version": 1, "case_id": case_id,
                "as_of_utc": capture_packet["as_of_utc"],
                "market_reference": market_reference,
                "sources": sources, "claims": claims,
                "unresolved_questions": questions,
                "note": "Model-proposed, excerpt-linked working claims; no semantic certification.",
            }
            if evidence_issues(case):
                return CaseAssembly("research_hold", "source_or_claim_provenance_failed", None, 1)
            return CaseAssembly("provisional_case_ready", "research_gate_passed_pending_semantics", case, 1)
        except (KeyError, TypeError, ValueError, AttributeError, RuntimeError):
            return CaseAssembly("research_hold", "claim_extractor_unavailable_or_invalid", None, 1)
