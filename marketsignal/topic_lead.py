"""Evidence-bounded Topic Lead for the private newsroom v3 workflow.

An opt-in model may propose angles and scores, but only deterministic policy
can commission investigation. This stage does not browse, certify facts or
publish. Source captures and the coverage index must come from other systems.
"""

from __future__ import annotations

import re
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol

from .newsroom_control import TopicRubric
from .quantitative import QuantitativePitch


GO_THRESHOLD = 65
HOLD_THRESHOLD = 45
VALID_SOURCE_TYPES = {
    "primary_record", "independent_reporting", "public_statement",
    "article_metadata", "social_comment", "market_comment",
}
RESEARCH_LEAD_TYPES = {"primary_record", "independent_reporting", "public_statement"}
RUBRIC_FIELDS = (
    "news_peg", "consequences", "editorial_potential", "originality",
    "research_feasibility", "timeliness",
)


@dataclass(frozen=True)
class TopicSourceLead:
    source_id: str
    publisher: str
    url: str
    origin_key: str
    published_at: int
    source_type: str
    captured_excerpt: str = ""

    def __post_init__(self) -> None:
        if (not self.source_id or not self.publisher.strip() or not self.origin_key or
                not self.url.startswith("https://") or
                not isinstance(self.published_at, int) or self.published_at <= 0 or
                self.source_type not in VALID_SOURCE_TYPES or
                len(self.captured_excerpt) > 1800):
            raise ValueError("Invalid Topic Lead source metadata")


@dataclass(frozen=True)
class CoverageMatch:
    story_id: str
    title: str
    overlap: str  # partial | complete; assessed against named proposed angles
    angle_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if (not self.story_id or not self.title or self.overlap not in {"partial", "complete"}
                or not self.angle_ids):
            raise ValueError("Invalid prior coverage match")


@dataclass(frozen=True)
class TopicLeadContext:
    story_id: str
    as_of: int
    market_question: str
    resolution_terms: str
    quantitative_pitch: QuantitativePitch
    sources: tuple[TopicSourceLead, ...]
    coverage_checked: bool
    coverage_matches: tuple[CoverageMatch, ...] = ()
    primary_has_independent_test: bool = False

    def __post_init__(self) -> None:
        if (not self.story_id or not isinstance(self.as_of, int) or self.as_of <= 0 or
                not self.market_question.strip() or
                self.quantitative_pitch.observed_at != self.as_of or
                len(self.sources) > 15 or len(self.coverage_matches) > 20):
            raise ValueError("Invalid Topic Lead context")
        if len({s.source_id for s in self.sources}) != len(self.sources):
            raise ValueError("Duplicate Topic Lead source IDs")
        if any(s.published_at > self.as_of for s in self.sources):
            raise ValueError("Future-dated context source would leak into historical replay")

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class TopicAngle:
    angle_id: str
    working_headline: str
    central_question: str
    thesis_to_test: str
    disconfirmation_test: str
    novel_contribution: str
    source_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if not all((self.angle_id.strip(), self.working_headline.strip(),
                    self.central_question.strip(), self.thesis_to_test.strip(),
                    self.disconfirmation_test.strip(), self.novel_contribution.strip())):
            raise ValueError("Incomplete Topic Lead angle")
        if re.search(r"\b(polymarket|kalshi|prediction markets?|betting odds|market odds)\b|%",
                     self.working_headline, re.IGNORECASE):
            raise ValueError("Working headline leads with market mechanics")


@dataclass(frozen=True)
class TopicLeadAssessment:
    story_id: str
    disposition: str  # go | hold | spike
    requested_disposition: str
    score: int
    rubric: TopicRubric
    score_rationales: dict[str, str]
    reason_codes: tuple[str, ...]
    news_peg_type: str
    news_peg: str
    prior_expectation: str
    public_stakes: str
    coverage_analysis: str
    angles: tuple[TopicAngle, ...]
    counterevidence: tuple[str, ...]
    research_questions: tuple[str, ...]
    uncertainties: tuple[str, ...]
    sensitivity_flags: tuple[str, ...]
    revisit_condition: str
    referenced_source_ids: tuple[str, ...]
    publication_enabled: bool = False
    evaluation_only: bool = False
    test_fixture_reason: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


class TopicLeadModel(Protocol):
    def complete(self, stage: str, payload: dict) -> dict: ...


def _strings(value: object, *, max_items: int = 12) -> tuple[str, ...]:
    if (not isinstance(value, list) or len(value) > max_items or
            any(not isinstance(item, str) or len(item) > 1000 for item in value)):
        raise ValueError("Invalid bounded Topic Lead list")
    return tuple(value)


class TopicLeadAgent:
    """Generate a provisional assignment, then enforce independent gates."""

    def __init__(self, model: TopicLeadModel):
        self.model = model

    def assess(self, context: TopicLeadContext) -> TopicLeadAssessment:
        """Production entry: ineligible quantitative pitches always remain held."""
        return self._assess(context)

    def _assess(self, context: TopicLeadContext, *, test_fixture_reason: str = "") -> TopicLeadAssessment:
        """Private test-only hook; only evaluation_harness should set a reason."""
        context_packet = context.to_dict()
        if test_fixture_reason:
            context_packet["test_only_evaluation"] = {
                "quantitative_gate_override": True,
                "reason": test_fixture_reason,
                "original_quantitative_eligibility": context.quantitative_pitch.eligible_for_topic_review,
                "original_quantitative_reasons": list(context.quantitative_pitch.reasons),
                "publication_enabled": False,
            }
        raw = self.model.complete("topic_lead", context_packet)
        if not isinstance(raw, dict):
            raise ValueError("Topic Lead model must return an object")
        scores = raw["scores"]
        rationales = raw["score_rationales"]
        if (not isinstance(scores, dict) or not isinstance(rationales, dict) or
                set(scores) != set(RUBRIC_FIELDS) or set(rationales) != set(RUBRIC_FIELDS) or
                any(type(scores[k]) is not int for k in RUBRIC_FIELDS) or
                any(not isinstance(rationales[k], str) or not rationales[k].strip()
                    for k in RUBRIC_FIELDS)):
            raise ValueError("Invalid Topic Lead rubric or unexplained scores")

        raw_angles = raw["angles"]
        if not isinstance(raw_angles, list) or len(raw_angles) > 3:
            raise ValueError("Topic Lead may propose at most three angles")
        angles = tuple(TopicAngle(
            angle_id=a["angle_id"], working_headline=a["working_headline"],
            central_question=a["central_question"], thesis_to_test=a["thesis_to_test"],
            disconfirmation_test=a["disconfirmation_test"],
            novel_contribution=a["novel_contribution"],
            source_ids=_strings(a["source_ids"]),
        ) for a in raw_angles)
        if len({a.angle_id for a in angles}) != len(angles):
            raise ValueError("Duplicate story angle IDs")

        known_sources = {source.source_id for source in context.sources}
        peg_ids = _strings(raw["news_peg_source_ids"])
        prior_ids = _strings(raw["prior_expectation_source_ids"])
        stake_ids = _strings(raw["public_stakes_source_ids"])
        referenced = set(peg_ids + prior_ids + stake_ids)
        for angle in angles:
            referenced.update(angle.source_ids)
        if not referenced.issubset(known_sources):
            raise ValueError("Topic Lead cited unknown or invented source ID")

        rubric = TopicRubric(**scores, source_ids=tuple(sorted(referenced)))
        requested = raw["requested_disposition"]
        peg_type = raw["news_peg_type"]
        if requested not in {"go", "hold", "spike"} or peg_type not in {
            "documented_development", "original_analysis", "emerging_signal", "none"
        }:
            raise ValueError("Invalid Topic Lead disposition or news peg type")
        for key in ("news_peg", "prior_expectation", "public_stakes",
                    "coverage_analysis", "revisit_condition"):
            if not isinstance(raw[key], str) or len(raw[key]) > 2500:
                raise ValueError("Invalid Topic Lead narrative field")
        counterevidence = _strings(raw["counterevidence"])
        research_questions = _strings(raw["research_questions"])
        uncertainties = _strings(raw["uncertainties"])
        sensitivity_flags = _strings(raw["sensitivity_flags"])

        reason_codes: list[str] = []
        disposition = requested
        if requested == "go":
            def hold(reason: str) -> None:
                nonlocal disposition
                if disposition != "spike":
                    disposition = "hold"
                reason_codes.append(reason)

            if rubric.score < HOLD_THRESHOLD:
                if rubric.consequences >= 4:
                    hold("high_consequence_exception")
                else:
                    disposition = "spike"
                    reason_codes.append("score_below_research_floor")
            elif rubric.score < GO_THRESHOLD:
                hold("score_below_go_threshold")
            if not context.quantitative_pitch.eligible_for_topic_review and not test_fixture_reason:
                hold("quantitative_triage_not_eligible")
            if not context.resolution_terms.strip():
                hold("unresolved_market_terms")
            if peg_type in {"none", "emerging_signal"} or not raw["news_peg"].strip():
                hold("unexplained_market_movement")
            if not raw["public_stakes"].strip():
                hold("stakes_not_established")
            if not angles or not research_questions:
                hold("no_actionable_research_assignment")
            # A pending coverage search is an explicit research assignment,
            # not grounds to prevent the Investigator from searching at all.
            # It must remain visible downstream; no publication is authorized.
            if not context.coverage_checked:
                reason_codes.append("coverage_review_pending")
            if not peg_ids and peg_type != "original_analysis":
                hold("unsubstantiated_news_peg")

            usable_origins = {source.origin_key for source in context.sources
                              if source.source_id in referenced and
                              source.source_type in RESEARCH_LEAD_TYPES and
                              source.captured_excerpt}
            if not usable_origins:
                hold("no_authentic_research_seed")

            covered = {angle_id for match in context.coverage_matches
                       if match.overlap == "complete" for angle_id in match.angle_ids}
            if angles and all(angle.angle_id in covered for angle in angles):
                disposition = "spike"
                reason_codes.append("all_angles_duplicative")

        if disposition == "hold" and not raw["revisit_condition"].strip():
            # Never archive an indefinite HOLD without an explicit reopening condition.
            raise ValueError("Held Topic Lead pitch lacks a revisit condition")
        if not reason_codes:
            reason_codes = [f"topic_lead_{disposition}"]
        if test_fixture_reason:
            reason_codes.append("test_fixture_only_quantitative_override")

        return TopicLeadAssessment(
            story_id=context.story_id, disposition=disposition,
            requested_disposition=requested, score=rubric.score, rubric=rubric,
            score_rationales=dict(rationales), reason_codes=tuple(reason_codes),
            news_peg_type=peg_type, news_peg=raw["news_peg"],
            prior_expectation=raw["prior_expectation"],
            public_stakes=raw["public_stakes"],
            coverage_analysis=raw["coverage_analysis"], angles=angles,
            counterevidence=counterevidence, research_questions=research_questions,
            uncertainties=uncertainties, sensitivity_flags=sensitivity_flags,
            revisit_condition=raw["revisit_condition"],
            referenced_source_ids=tuple(sorted(referenced)),
            evaluation_only=bool(test_fixture_reason), test_fixture_reason=test_fixture_reason,
        )


def load_topic_context(path: str | Path) -> TopicLeadContext:
    """Load an explicitly curated, private source packet; never scrape URLs."""
    file = Path(path)
    if file.stat().st_size > 120_000:
        raise ValueError("Oversized Topic Lead input")
    payload = json.loads(file.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1:
        raise ValueError("Unsupported Topic Lead input version")
    return TopicLeadContext(
        story_id=payload["story_id"], as_of=payload["as_of"],
        market_question=payload["market_question"],
        resolution_terms=payload["resolution_terms"],
        quantitative_pitch=QuantitativePitch(**payload["quantitative_pitch"]),
        sources=tuple(TopicSourceLead(**source) for source in payload["sources"]),
        coverage_checked=payload["coverage_checked"],
        coverage_matches=tuple(CoverageMatch(
            story_id=row["story_id"], title=row["title"],
            overlap=row["overlap"], angle_ids=tuple(row["angle_ids"]),
        ) for row in payload.get("coverage_matches", [])),
        primary_has_independent_test=payload.get("primary_has_independent_test", False),
    )
