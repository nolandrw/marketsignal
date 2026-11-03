"""Small synthetic panel and evidence-based, permissioned process oversight.

Synthetic reviews are diagnostics, never real audience data. Auto adjustments
may change only pre-approved operational knobs; substantive agent instructions,
news thresholds and release policies require owner approval and evaluation.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass


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


class OversightAgent:
    """Diagnose aggregates, make proposals, never rewrite prompts or publish."""

    AUTO_KEYS = {"source_retry_backoff_seconds": (0.0, 2.0)}

    def assess(self, ledger_metrics: dict) -> tuple[OversightProposal, ...]:
        agents = ledger_metrics.get("agents", {})
        suggestions = []
        for name, counts in agents.items():
            failures = int(counts.get("quality_fail", 0))
            passes = int(counts.get("quality_pass", 0))
            if failures + passes >= 20 and failures / (failures + passes) >= 0.2:
                suggestions.append(OversightProposal(
                    "bespoke", name, "High independently labeled failure rate",
                    "Prepare versioned instructions and held-out evaluation for owner review",
                    failures + passes))
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


def grade_agents(ledger_metrics: dict, minimum_samples: int = 20) -> dict[str, dict]:
    """Only independent quality results produce letter grades, not activity."""
    output = {}
    for agent, counts in ledger_metrics.get("agents", {}).items():
        passed, failed = int(counts.get("quality_pass", 0)), int(counts.get("quality_fail", 0))
        n = passed + failed
        rate = passed / n if n else None
        letter = "unrated"
        if n >= minimum_samples:
            letter = "A" if rate >= .90 else "B" if rate >= .80 else \
                     "C" if rate >= .70 else "D" if rate >= .60 else "F"
        output[agent] = {"grade": letter, "samples": n,
                         "verified_success_rate": round(rate, 3) if rate is not None else None}
    return output
