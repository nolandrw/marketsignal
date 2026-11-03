"""Offline editorial-agent contracts and a fail-closed shadow workflow.

This module deliberately makes no model, web, or publication calls. It gives
future research/writer/verifier adapters narrow typed interfaces to implement
without allowing those adapters to control the publication decision.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import asdict, dataclass
from typing import Protocol
from urllib.parse import urlsplit

from .detection import MIN_LIQUIDITY_USD, MIN_VOLUME_24H_USD
from .models import Market, Signal


@dataclass(frozen=True)
class Candidate:
    market: Market
    signal: Signal
    # Classification must come from a separate, reviewed policy. Incoming
    # market metadata never confers low-risk status by itself.
    risk: str = "unknown"

    @property
    def candidate_id(self) -> str:
        identity = f"{self.market.market_id}:{self.signal.baseline_at}:{self.signal.observed_at}"
        return hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20]


@dataclass(frozen=True)
class Evidence:
    evidence_id: str
    url: str
    title: str
    captured_at: int
    kind: str  # market_snapshot | primary_source | independent_reporting
    content_sha256: str


@dataclass(frozen=True)
class NumericFact:
    market_id: str
    baseline_at: int
    observed_at: int
    previous_price: float
    current_price: float
    change_pp: float


@dataclass(frozen=True)
class Claim:
    text: str
    kind: str  # market_movement | verified_context | causal_explanation
    evidence_ids: tuple[str, ...]


@dataclass(frozen=True)
class StoryDraft:
    headline: str
    summary: str
    numeric_fact: NumericFact
    claims: tuple[Claim, ...]
    writer_version: str


@dataclass(frozen=True)
class EditorialResult:
    candidate_id: str
    status: str  # shadow_ready | held
    reasons: tuple[str, ...]
    trace: tuple[str, ...]
    evidence: tuple[Evidence, ...]
    draft: StoryDraft | None

    def to_dict(self) -> dict:
        return asdict(self)


class ResearchAgent(Protocol):
    def research(self, candidate: Candidate) -> tuple[Evidence, ...]: ...


class WritingAgent(Protocol):
    def write(self, candidate: Candidate, evidence: tuple[Evidence, ...]) -> StoryDraft: ...


class MarketRecordResearcher:
    """Supplies provenance for stored quotes, NOT independent news context."""

    def research(self, candidate: Candidate) -> tuple[Evidence, ...]:
        record = {
            "market": asdict(candidate.market),
            "signal": asdict(candidate.signal),
        }
        digest = hashlib.sha256(json.dumps(record, sort_keys=True).encode("utf-8")).hexdigest()
        return (Evidence(
            evidence_id=f"snapshot-{candidate.candidate_id}",
            url=candidate.market.source_url,
            title=candidate.market.question,
            captured_at=candidate.signal.observed_at,
            kind="market_snapshot",
            content_sha256=digest,
        ),)


class TemplateWriter:
    """A deterministic movement-only baseline; never asserts a catalyst."""

    version = "movement-template-v1"

    def write(self, candidate: Candidate, evidence: tuple[Evidence, ...]) -> StoryDraft:
        signal = candidate.signal
        direction = "rose" if signal.change_pp > 0 else "fell"
        previous = signal.previous_price * 100
        current = signal.current_price * 100
        headline = f"{candidate.market.question} — Yes price {direction} {abs(signal.change_pp):.1f} points"
        summary = (
            f"The observed Yes price moved from {previous:.1f}% to {current:.1f}% "
            f"across {signal.window_hours} hours. This is a snapshot comparison, "
            "not confirmation of the event or an explanation for the move."
        )
        return StoryDraft(
            headline=headline,
            summary=summary,
            numeric_fact=NumericFact(
                market_id=signal.market_id,
                baseline_at=signal.baseline_at,
                observed_at=signal.observed_at,
                previous_price=signal.previous_price,
                current_price=signal.current_price,
                change_pp=signal.change_pp,
            ),
            claims=(Claim(
                text="A change in the observed Yes market price occurred.",
                kind="market_movement",
                evidence_ids=(f"snapshot-{candidate.candidate_id}",),
            ),),
            writer_version=self.version,
        )


def _valid_source_url(url: str) -> bool:
    """Structural citation check only; never represents a live URL fetch."""
    try:
        parsed = urlsplit(url)
        return (parsed.scheme == "https" and bool(parsed.hostname)
                and parsed.username is None and parsed.password is None
                and not any(char.isspace() for char in url))
    except ValueError:
        return False


class TriageAgent:
    """Recompute numeric observations independently of any language model."""

    def check(self, candidate: Candidate) -> tuple[str, ...]:
        market, signal = candidate.market, candidate.signal
        issues = []
        if market.market_id != signal.market_id:
            issues.append("market_id_mismatch")
        if not all(math.isfinite(value) for value in (
                market.yes_price, market.volume_24h, market.liquidity,
                signal.previous_price, signal.current_price, signal.change_pp,
                signal.volume_24h, signal.liquidity)):
            issues.append("nonfinite_numeric_input")
        if not (0 <= signal.previous_price <= 1 and 0 <= signal.current_price <= 1
                and 0 <= market.yes_price <= 1):
            issues.append("invalid_price")
        if abs(signal.current_price - market.yes_price) > 0.000001:
            issues.append("current_quote_mismatch")
        if abs(round((signal.current_price - signal.previous_price) * 100, 3) - signal.change_pp) > 0.001:
            issues.append("nonrecomputable_change")
        if signal.observed_at <= signal.baseline_at:
            issues.append("invalid_observation_window")
        elif abs(round((signal.observed_at - signal.baseline_at) / 3600) - signal.window_hours) > 1:
            issues.append("window_mismatch")
        if (market.volume_24h < MIN_VOLUME_24H_USD or
                market.liquidity < MIN_LIQUIDITY_USD):
            issues.append("insufficient_market_depth")
        if (abs(signal.volume_24h - market.volume_24h) > 0.01 or
                abs(signal.liquidity - market.liquidity) > 0.01):
            issues.append("depth_evidence_mismatch")
        threshold = 15.0 if signal.window_hours >= 12 else 8.0
        if abs(signal.change_pp) < threshold:
            issues.append("below_movement_threshold")
        if not re.fullmatch(r"[a-zA-Z0-9-]+", market.event_slug):
            issues.append("invalid_market_slug")
        return tuple(issues)


class VerificationAgent:
    """Conservative structural checks; cannot substitute for source reading."""

    def check(self, candidate: Candidate, evidence: tuple[Evidence, ...],
              draft: StoryDraft) -> tuple[str, ...]:
        issues = []
        if not evidence:
            issues.append("missing_evidence")
        ids = [item.evidence_id for item in evidence]
        if len(ids) != len(set(ids)):
            issues.append("duplicate_evidence_id")
        for item in evidence:
            if (not _valid_source_url(item.url) or
                    not re.fullmatch(r"[a-f0-9]{64}", item.content_sha256) or
                    item.captured_at <= 0):
                issues.append("invalid_evidence_provenance")
        if not draft.headline.strip() or not draft.summary.strip() or not draft.claims:
            issues.append("incomplete_draft")
        fact = draft.numeric_fact
        signal = candidate.signal
        if (fact.market_id != signal.market_id or fact.baseline_at != signal.baseline_at
                or fact.observed_at != signal.observed_at or
                abs(fact.previous_price - signal.previous_price) > 0.000001 or
                abs(fact.current_price - signal.current_price) > 0.000001 or
                abs(fact.change_pp - signal.change_pp) > 0.001):
            issues.append("draft_numeric_claim_mismatch")
        for claim in draft.claims:
            if not claim.evidence_ids or not set(claim.evidence_ids).issubset(ids):
                issues.append("unsupported_citation")
            if claim.kind != "market_movement":
                # Extra context and causal assertions require a real research
                # and separate factual-verification layer, not present in v0.
                issues.append("non_market_claim_requires_review")
        if not any(item.kind == "market_snapshot" for item in evidence):
            issues.append("missing_market_record")
        return tuple(sorted(set(issues)))


class EditorAgent:
    def decide(self, candidate: Candidate, issues: tuple[str, ...],
               *, trusted_template: bool) -> tuple[str, tuple[str, ...]]:
        reasons = list(issues)
        if candidate.risk != "low":
            reasons.append("risk_classification_requires_review")
        if not trusted_template:
            reasons.append("model_or_custom_writer_requires_language_verification")
        if reasons:
            return "held", tuple(sorted(set(reasons)))
        # Never means publicly approved. No publisher is attached to this flow.
        return "shadow_ready", ()


class EditorialPipeline:
    """Fixed orchestration: triage -> research -> write -> verify -> edit.

    Agent adapters cannot skip the deterministic gate or write public output.
    """

    def __init__(self, researcher: ResearchAgent | None = None,
                 writer: WritingAgent | None = None):
        self.researcher = researcher or MarketRecordResearcher()
        self.writer = writer or TemplateWriter()
        self.triage = TriageAgent()
        self.verifier = VerificationAgent()
        self.editor = EditorAgent()

    def run(self, candidate: Candidate) -> EditorialResult:
        trace = ["candidate_received"]
        issues = self.triage.check(candidate)
        trace.append("triage_passed" if not issues else "triage_failed")
        if issues:
            return EditorialResult(candidate.candidate_id, "held", issues, tuple(trace), (), None)
        evidence: tuple[Evidence, ...] = ()
        draft: StoryDraft | None = None
        try:
            evidence = self.researcher.research(candidate)
            trace.append("research_completed")
            draft = self.writer.write(candidate, evidence)
            trace.append("draft_completed")
            issues = self.verifier.check(candidate, evidence, draft)
            trace.append("verification_passed" if not issues else "verification_failed")
            status, reasons = self.editor.decide(
                candidate, issues, trusted_template=type(self.writer) is TemplateWriter
            )
            trace.append("shadow_ready" if status == "shadow_ready" else "editorial_hold")
            return EditorialResult(candidate.candidate_id, status, reasons, tuple(trace), evidence, draft)
        except Exception as exc:
            # Network/provider errors may contain sensitive strings; do not
            # expose their messages in audit output or public pages.
            trace.append(f"agent_error:{type(exc).__name__}")
            return EditorialResult(candidate.candidate_id, "held", ("agent_execution_failed",),
                                   tuple(trace), evidence, None)
