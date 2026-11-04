"""Explicit story-angle handoff between investigation, verification and editing.

These are deterministic completeness/provenance checks, NOT an AI verdict on
originality, newsworthiness, factual accuracy or publishability. Those require
independent source review and reader/editor assessments.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Mapping, Sequence


RUBRIC_WEIGHTS = {
    "central_conflict": 20,
    "public_significance": 20,
    "surprise_or_reversal": 15,
    "specificity": 15,
    "evidence_strength": 15,
    "original_value": 10,
    "narrative_depth": 5,
}


@dataclass(frozen=True)
class StoryPitch:
    pitch_id: str
    working_headline: str
    thesis: str
    conflict: str
    surprise: str
    why_now: str
    stakes: str
    original_value: str
    supporting_claim_ids: tuple[str, ...]
    contrary_claim_ids: tuple[str, ...]


@dataclass(frozen=True)
class EditorialSelection:
    selected_pitch_id: str
    headline: str
    rationale: str
    evidence_review: str = "provisional_shadow"


def headline_issues(headline: str) -> tuple[str, ...]:
    """A conservative lint check; it cannot tell whether a headline is good."""
    issues = []
    if not isinstance(headline, str) or not 20 <= len(headline.strip()) <= 120:
        issues.append("headline_invalid_length")
    if not isinstance(headline, str):
        return tuple(issues)
    if re.search(r"polymarket|\bodds\b|market price|\d+(?:\.\d+)?%|percentage points",
                 headline, re.I):
        issues.append("market_centered_headline")
    # These are useful warnings about a demonstrably weak form of headline.
    # They do not replace a critical editor's judgment.
    if re.search(r"\braises? (?:the |a )?question\b|\bwe don.t know\b|"
                 r"\bno one (?:can |yet )?knows?\b|\bwhat we don.t know\b",
                 headline, re.I):
        issues.append("epistemic_nonstory_headline")
    return tuple(issues)


def audit_story_selection(
    pitches: Sequence[StoryPitch],
    selection: EditorialSelection | None,
    claims_by_id: Mapping[str, str],
    *,
    article_headline: str | None = None,
) -> tuple[str, ...]:
    """Require genuine alternative pitches and a traceable editorial decision.

    Claims are passed as ID -> role so distinct sources can be checked by the
    parent dossier audit. A field-trial story cannot be commissioned without
    a supported development, prior view, stakes and counterevidence.
    """
    issues: list[str] = []
    if len(pitches) < 2 or len({p.pitch_id for p in pitches}) != len(pitches):
        issues.append("missing_competing_story_pitches")
    by_id = {p.pitch_id: p for p in pitches}
    for pitch in pitches:
        if not re.fullmatch(r"[a-z][a-z0-9_-]{2,60}", pitch.pitch_id):
            issues.append("invalid_story_pitch_id")
        if any(not getattr(pitch, key).strip() or len(getattr(pitch, key)) < 22
               for key in ("thesis", "conflict", "surprise", "why_now", "stakes", "original_value")):
            issues.append("incomplete_story_pitch")
        if headline_issues(pitch.working_headline):
            issues.append("weak_pitch_headline")
        linked = set(pitch.supporting_claim_ids) | set(pitch.contrary_claim_ids)
        if (not pitch.supporting_claim_ids or not pitch.contrary_claim_ids or
                not linked <= set(claims_by_id)):
            issues.append("unsubstantiated_story_pitch")
    if selection is None or selection.selected_pitch_id not in by_id:
        issues.append("no_editorially_selected_story")
        return tuple(sorted(set(issues)))
    if selection.evidence_review != "provisional_shadow":
        issues.append("unrecognized_evidence_review_status")
    if len(selection.rationale.strip()) < 45:
        issues.append("selection_without_editorial_rationale")
    issues.extend(headline_issues(selection.headline))
    if article_headline is not None and selection.headline != article_headline:
        issues.append("headline_changed_without_editorial_review")
    pitch = by_id[selection.selected_pitch_id]
    selected_roles = {claims_by_id[c] for c in pitch.supporting_claim_ids}
    role_groups = (
        {"development", "new_development"},
        {"prior_view", "prior_expectations"},
        {"stakes"},
    )
    if any(not selected_roles.intersection(role_group) for role_group in role_groups):
        issues.append("selected_pitch_missing_news_spine")
    counter_roles = {claims_by_id[c] for c in pitch.contrary_claim_ids}
    if not counter_roles.intersection({"counterpoint"}):
        issues.append("selected_pitch_missing_counterevidence")
    if len(pitch.supporting_claim_ids) < 3:
        issues.append("selected_pitch_insufficient_support")
    return tuple(sorted(set(issues)))


def parse_story_pitches(values: object) -> tuple[StoryPitch, ...]:
    """Parse the portable JSON handoff without accepting arbitrary extra data."""
    if not isinstance(values, list) or len(values) > 6:
        raise ValueError("Expected a bounded story-pitch array")
    result = []
    for value in values:
        if not isinstance(value, dict):
            raise ValueError("Invalid story pitch")
        result.append(StoryPitch(
            pitch_id=value["pitch_id"], working_headline=value["working_headline"],
            thesis=value["thesis"], conflict=value["conflict"],
            surprise=value["surprise"], why_now=value["why_now"],
            stakes=value["stakes"], original_value=value["original_value"],
            supporting_claim_ids=tuple(value["supporting_claim_ids"]),
            contrary_claim_ids=tuple(value["contrary_claim_ids"]),
        ))
    return tuple(result)


def parse_editorial_selection(value: object) -> EditorialSelection:
    if not isinstance(value, dict):
        raise ValueError("Missing editorial selection")
    return EditorialSelection(
        selected_pitch_id=value["selected_pitch_id"], headline=value["headline"],
        rationale=value["rationale"],
        evidence_review=value.get("evidence_review", "provisional_shadow"),
    )
