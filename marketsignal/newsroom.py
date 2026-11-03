"""Shadow newsroom orchestration and immutable agent-to-agent handoffs."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from .editorial import (
    Candidate, EditorialResult, EditorAgent, MarketRecordResearcher,
    TemplateWriter, TriageAgent, VerificationAgent,
)
from .evidence_investigator import EvidenceAssessment, EvidenceInvestigator
from .investigation import NarrativeScout, ResearchPacket
from .models import Market, Signal


@dataclass(frozen=True)
class NewsroomResult:
    schema_version: int
    candidate_id: str
    outcome: str  # shadow_ready | held
    research: ResearchPacket | None
    assessment: EvidenceAssessment | None
    editorial: EditorialResult | None
    stages: tuple[str, ...]
    publication_enabled: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


class ShadowNewsroom:
    """No publisher or model keys. Stage handoffs do not confer authority."""

    def __init__(self, scout: NarrativeScout):
        self.scout = scout
        self.investigator = EvidenceInvestigator()
        self.market_researcher = MarketRecordResearcher()
        self.writer = TemplateWriter()
        self.verifier = VerificationAgent()
        self.editor = EditorAgent()

    def run(self, candidate: Candidate) -> NewsroomResult:
        stages = ["ingest"]
        problems = TriageAgent().check(candidate)
        if problems:
            stages.append("triage_hold")
            # Do not spend network requests investigating an invalid quote.
            return NewsroomResult(1, candidate.candidate_id, "held", None,
                                  None,
                                  EditorialResult(candidate.candidate_id, "held",
                                                  problems, tuple(stages), (), None),
                                  tuple(stages))
        stages.append("triage_pass")
        try:
            research = self.scout.investigate(candidate)
            if research.candidate_id != candidate.candidate_id:
                stages.append("research_id_mismatch")
                return NewsroomResult(1, candidate.candidate_id, "held",
                                      None, None, None, tuple(stages))
            stages.append("narrative_scout_handoff")
            assessment = self.investigator.assess(research)
            if (assessment.candidate_id != candidate.candidate_id or
                    assessment.handoff_status != "MOVEMENT_ONLY"):
                stages.append("investigator_handoff_invalid")
                return NewsroomResult(1, candidate.candidate_id, "held",
                                      research, None, None, tuple(stages))
        except Exception as exc:
            stages.append(f"research_failure:{type(exc).__name__}")
            return NewsroomResult(1, candidate.candidate_id, "held", None,
                                  None, None, tuple(stages))
        stages.append("evidence_investigator_handoff")
        # The writer MUST consume explicit permissions from the investigator.
        # No model can self-declare that a social narrative was corroborated.
        if (assessment.writer_permissions !=
                ("market_movement_from_stored_signal_only",)):
            stages.append("writer_permission_hold")
            return NewsroomResult(1, candidate.candidate_id, "held", research,
                                  assessment, None, tuple(stages))
        try:
            evidence = self.market_researcher.research(candidate)
            draft = self.writer.write(candidate, evidence)
            stages.append("movement_draft_handoff")
            issues = self.verifier.check(candidate, evidence, draft)
            stages.append("fact_verification_handoff")
            disposition, reasons = self.editor.decide(candidate, issues,
                                                       trusted_template=True)
            editorial = EditorialResult(candidate.candidate_id, disposition,
                                        reasons, tuple(stages), evidence, draft)
        except Exception as exc:
            stages.append(f"editorial_failure:{type(exc).__name__}")
            return NewsroomResult(1, candidate.candidate_id, "held", research,
                                  assessment, None, tuple(stages))
        stages.append("editorial_" + editorial.status)
        return NewsroomResult(1, candidate.candidate_id, editorial.status,
                              research, assessment, editorial, tuple(stages))


def replay_archive(path: str | Path, scout: NarrativeScout, *,
                   max_candidates: int = 5) -> list[NewsroomResult]:
    """Rehydrate selected live signals without modifying the source record."""
    if not 1 <= max_candidates <= 20:
        raise ValueError("Unbounded candidate count")
    record = json.loads(Path(path).read_text(encoding="utf-8"))
    if record.get("schema_version") != 1 or not isinstance(record.get("signals"), list):
        raise ValueError("Invalid daily archive")
    markets = {item["market_id"]: Market(**item) for item in record.get("markets", [])}
    newsroom = ShadowNewsroom(scout)
    output = []
    for data in record["signals"][:max_candidates]:
        signal = Signal(**data)
        market = markets.get(signal.market_id)
        if market is not None:
            # Live topics default to unknown risk; no automatic article release.
            output.append(newsroom.run(Candidate(market, signal)))
    return output


def safe_report(results: list[NewsroomResult]) -> dict:
    """Compact reporting: avoid dumping raw social text/user identifiers."""
    return {
        "schema_version": 1, "mode": "shadow", "publication_enabled": False,
        "candidates": [{
            "candidate_id": item.candidate_id, "status": item.outcome,
            "source_errors": list(item.research.source_errors) if item.research else [],
            "hypothesis_count": len(item.research.hypotheses) if item.research else 0,
            "research_handoff": item.assessment.handoff_status if item.assessment else "none",
            "stages": list(item.stages),
            "hold_reasons": list(item.editorial.reasons) if item.editorial else
            ["invalid_research_handoff"],
        } for item in results],
    }
