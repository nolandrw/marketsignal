"""Small synthetic panel and evidence-based, permissioned process oversight.

Synthetic reviews are diagnostics, never real audience data. Auto adjustments
may change only pre-approved operational knobs; substantive agent instructions,
news thresholds and release policies require owner approval and evaluation.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from collections.abc import Sequence


DEFAULT_PERSONAS = (
    "time_constrained_reader", "topic_newcomer", "skeptical_reader",
    "quantitative_reader", "directly_affected_reader", "policy_specialist",
    "context_seeker", "evidence_focused_reader",
)


@dataclass(frozen=True)
class AudienceFeedback:
    segment: str
    usefulness: int
    # One real respondent, not an LLM call; the caller must enforce consent.
    source: str = "human"


class SyntheticAudiencePanel:
    def __init__(self, weights: dict[str, float] | None = None):
        self.weights = dict(weights or {name: 1.0 for name in DEFAULT_PERSONAS})
        if set(self.weights) != set(DEFAULT_PERSONAS) or any(
                not 0.5 <= weight <= 1.5 for weight in self.weights.values()):
            raise ValueError("Panel must contain eight bounded persona weights")

    def examine(self, headline: str, article: str, cited_paragraphs: int,
                paragraph_count: int) -> dict:
        """Transparent structural checks; not human or model quality ratings."""
        issues = []
        if len(headline.strip()) < 15 or len(headline.strip()) > 130:
            issues.append("headline_length")
        if any(term in headline.lower() for term in ("polymarket", "odds", "market price")):
            issues.append("market_centered_headline")
        word_count = len(article.split())
        if word_count < 120:
            issues.append("little_explanatory_depth")
        if word_count > 1100:
            issues.append("possible_excessive_length")
        if not 0 < paragraph_count <= 40 or not 0 <= cited_paragraphs <= paragraph_count:
            issues.append("invalid_paragraph_provenance")
        elif cited_paragraphs != paragraph_count:
            issues.append("uncited_paragraph")
        return {"source": "synthetic_structural_heuristics",
                "independent_human_rating": False, "persona_count": len(self.weights),
                "personas": list(DEFAULT_PERSONAS), "issues": issues,
                "word_count": word_count, "publication_approval": False}

    def propose_reweight(self, feedback: list[AudienceFeedback]) -> dict:
        """Only genuine human feedback can motivate modest panel reweighting."""
        if len(feedback) < 30 or any(f.source != "human" or
                                    f.segment not in self.weights or
                                    not 1 <= f.usefulness <= 5 for f in feedback):
            return {"status": "insufficient_valid_human_feedback", "proposed": self.weights}
        counts = {key: [] for key in self.weights}
        for item in feedback:
            counts[item.segment].append(item.usefulness)
        proposed = dict(self.weights)
        for name, values in counts.items():
            if len(values) < 5:
                continue
            # Propose a small sampling adjustment, not an editorial rewrite.
            delta = 0.1 if sum(values) / len(values) < 3.0 else -0.1
            proposed[name] = round(max(0.5, min(1.5, proposed[name] + delta)), 2)
        return {"status": "bespoke_approval_required", "proposed": proposed,
                "feedback_samples": len(feedback)}


@dataclass(frozen=True)
class OversightProposal:
    tranche: str  # automatic | bespoke | conceptual
    subject: str
    diagnosis: str
    action: str
    sample_size: int
    applied: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class IndependentEvaluation:
    """Caller-attested independent editorial label, not an agent's self-score.

    The ingestion layer must authenticate reviewers and retain the linked
    editorial evidence. An ID by itself is not proof of independence.
    """

    case_id: str
    agent: str
    passed: bool
    reviewer_id: str
    evidence_ref: str
    rubric_version: str
    source: str = "human_editor"

    def __post_init__(self):
        if (not all((self.case_id.strip(), self.agent.strip(), self.reviewer_id.strip(),
                     self.evidence_ref.strip(), self.rubric_version.strip())) or
                self.source != "human_editor" or
                self.agent == self.reviewer_id or not isinstance(self.passed, bool)):
            raise ValueError("Independent evaluations require an attributable human review")


def _evaluation_counts(evaluations: Sequence[IndependentEvaluation]) -> dict[str, tuple[int, int]]:
    """One reviewer-attested grade per distinct story/agent; reject duplicates.

    Metrics derived from this function are advisory until authentication and
    identity checks are integrated with an editorial review system.
    """
    seen: set[tuple[str, str]] = set()
    totals: dict[str, list[int]] = {}
    for evaluation in evaluations:
        if not isinstance(evaluation, IndependentEvaluation):
            raise ValueError("Unattributed aggregate quality metrics are not evaluations")
        key = (evaluation.case_id, evaluation.agent)
        if key in seen:
            raise ValueError("Duplicate independent evaluation case")
        seen.add(key)
        totals.setdefault(evaluation.agent, [0, 0])[0 if evaluation.passed else 1] += 1
    return {agent: (counts[0], counts[1]) for agent, counts in totals.items()}


class OversightAgent:
    """Diagnose aggregates, make proposals, never rewrite prompts or publish."""

    AUTO_KEYS = {"source_retry_backoff_seconds": (0.0, 2.0)}

    def assess(self, ledger_metrics: dict,
               evaluations: Sequence[IndependentEvaluation] = ()) -> tuple[OversightProposal, ...]:
        agents = ledger_metrics.get("agents", {})
        suggestions = []
        labeled = _evaluation_counts(evaluations)
        for name, (passes, failures) in labeled.items():
            if failures + passes >= 20 and failures / (failures + passes) >= 0.2:
                suggestions.append(OversightProposal(
                    "bespoke", name, "High human-editor-attested failure rate; verify sample provenance",
                    "Prepare versioned instructions and held-out evaluation for owner review",
                    failures + passes))
        for name, counts in agents.items():
            source_errors = int(counts.get("source_timeout", 0))
            if source_errors >= 5:
                suggestions.append(OversightProposal(
                    "automatic", name, "Repeated transient source timeouts",
                    "Increase bounded source retry backoff only", source_errors))
        if not suggestions:
            suggestions.append(OversightProposal(
                "conceptual", "newsroom", "Insufficient evidence of a recurring failure",
                "Keep observing; do not modify prompts or thresholds", 
                int(ledger_metrics.get("event_count", 0))))
        return tuple(suggestions)

    def apply_automatic(self, settings: dict[str, float], proposal: OversightProposal) -> dict[str, float]:
        if proposal.tranche != "automatic" or proposal.action != "Increase bounded source retry backoff only":
            raise ValueError("No authority for substantive auto-adjustments")
        key = "source_retry_backoff_seconds"
        lower, upper = self.AUTO_KEYS[key]
        value = float(settings.get(key, 0.25))
        if not lower <= value <= upper:
            raise ValueError("Existing setting outside approved safety bounds")
        return {**settings, key: round(min(upper, value + 0.25), 2)}


def grade_agents(ledger_metrics: dict, minimum_samples: int = 20,
                 evaluations: Sequence[IndependentEvaluation] = ()) -> dict[str, dict]:
    """Only distinct reviewer-attested cases produce advisory letter grades.

    `ledger_metrics` is *operational telemetry*, even if its reason codes say
    'quality_pass'. It is never evidence that an independent editor approved.
    """
    if minimum_samples < 20:
        raise ValueError("A letter grade requires at least 20 distinct editorial cases")
    output = {}
    labeled = _evaluation_counts(evaluations)
    for agent in set(ledger_metrics.get("agents", {})) | set(labeled):
        passed, failed = labeled.get(agent, (0, 0))
        n = passed + failed
        rate = passed / n if n else None
        indicative = None
        if n >= minimum_samples:
            indicative = "A" if rate >= .90 else "B" if rate >= .80 else \
                     "C" if rate >= .70 else "D" if rate >= .60 else "F"
        output[agent] = {"grade": "unrated", "indicative_unverified_grade": indicative,
                         "samples": n,
                         "editor_attested_success_rate": round(rate, 3) if rate is not None else None,
                         "authentication_integrated": False,
                         "operational_events_used_for_quality": False}
    return output
