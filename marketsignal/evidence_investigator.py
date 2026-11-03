"""Conservative independent hypothesis review prior to any writing handoff."""

from __future__ import annotations

from dataclasses import dataclass

from .investigation import ResearchPacket


@dataclass(frozen=True)
class HypothesisFinding:
    source_url: str
    hypothesis: str
    discussion_observed: bool
    underlying_claim_verified: bool
    causal_link_verified: bool
    status: str
    followup_questions: tuple[str, ...]


@dataclass(frozen=True)
class EvidenceAssessment:
    candidate_id: str
    findings: tuple[HypothesisFinding, ...]
    writer_permissions: tuple[str, ...]
    required_disclosures: tuple[str, ...]
    handoff_status: str


class EvidenceInvestigator:
    """Fail-closed baseline.

    The current scout retrieves only discovery metadata. It has not fetched
    original source contents, validated social independence, or checked claims
    against primary documents. It MUST NOT mark any narrative as corroborated.
    A future LLM/content verifier must be added behind explicit new gates.
    """

    version = "evidence-investigator-v1"

    def assess(self, packet: ResearchPacket) -> EvidenceAssessment:
        findings = tuple(HypothesisFinding(
            source_url=h.source_url,
            hypothesis=h.headline_or_lead,
            discussion_observed=False,  # API discovery != independently checked
            underlying_claim_verified=False,
            causal_link_verified=False,
            status="investigate_only",
            followup_questions=(
                "Can this post/article be retrieved and its timestamp independently checked?",
                "Is there a primary source supporting or contradicting the underlying assertion?",
                "Is the timeline consistent with, but not proof of, the price movement?",
            ),
        ) for h in packet.hypotheses)
        return EvidenceAssessment(
            candidate_id=packet.candidate_id,
            findings=findings,
            writer_permissions=("market_movement_from_stored_signal_only",),
            required_disclosures=(
                "Market price movements do not confirm outcomes or their causes.",
                "Social and article discovery results are unverified investigative leads.",
            ),
            handoff_status="MOVEMENT_ONLY",
        )
