"""Explicit, opt-in test-only story injection for newsroom evaluations.

This never changes production quantitative triage, fabricates a price baseline,
or grants editorial/publication authority. Human-selected subjects are fixtures.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .topic_lead import TopicLeadAgent, TopicLeadContext, TopicLeadAssessment


@dataclass(frozen=True)
class ResearchTestFixture:
    case_id: str
    market_id: str
    as_of: int
    purpose: str
    mode: str = "test_only_manual_subject"
    publication_enabled: bool = False

    def __post_init__(self):
        if (not isinstance(self.case_id, str) or not self.case_id.strip() or
                not isinstance(self.market_id, str) or not self.market_id.strip() or
                type(self.as_of) is not int or self.as_of <= 0 or
                not isinstance(self.purpose, str) or not 20 <= len(self.purpose.strip()) <= 500 or
                self.mode != "test_only_manual_subject" or self.publication_enabled is not False):
            raise ValueError("Invalid or unsafe evaluation fixture")


def load_test_fixture(path: str | Path) -> ResearchTestFixture:
    """An explicitly named, private JSON file, never a production config flag."""
    file = Path(path)
    if (file.suffix != ".json" or "private" not in file.parts or
            file.stat().st_size > 4_000):
        raise ValueError("Test fixture must be a small private JSON artifact")
    raw = json.loads(file.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or set(raw) != {
            "case_id", "market_id", "as_of", "purpose", "mode", "publication_enabled"}:
        raise ValueError("Unknown test fixture schema")
    return ResearchTestFixture(**raw)


def evaluate_topic_fixture(model, context: TopicLeadContext,
                           fixture: ResearchTestFixture) -> TopicLeadAssessment:
    """Bypass quantitative eligibility; permit explicitly incomplete research.

    Authentic source and editorial gates still run. Missing coverage is
    surfaced as a pending research task, not misrepresented as reviewed.
    """
    if (not isinstance(fixture, ResearchTestFixture) or fixture.case_id != context.story_id or
            fixture.market_id != context.quantitative_pitch.market_id or
            fixture.as_of != context.as_of):
        raise ValueError("Fixture identity or clock mismatch")
    result = TopicLeadAgent(model)._assess(context, test_fixture_reason=fixture.purpose)
    if not result.evaluation_only or result.publication_enabled:
        raise AssertionError("Test fixture leaked into production eligibility")
    return result
