"""Narrative discovery handoff: separate potential leads from established facts."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Protocol

from .agent_sources import PricePoint, SourceLead
from .editorial import Candidate


STOPWORDS = frozenset("""
will the a an is are it at for to in on of or by before after this that
become be becomes with from under over how who what when where why if does
there any next year month week day end beginning happen take place
""".split())


class HistorySource(Protocol):
    def between(self, token_id: str, since: int, until: int) -> tuple[PricePoint, ...]: ...


class DiscoverySource(Protocol):
    def search(self, query: str, since: int, until: int, limit: int = 20) -> tuple[SourceLead, ...]: ...


@dataclass(frozen=True)
class MoveWindow:
    start_at: int
    end_at: int
    confidence: str  # sampled_interval | sparse_history
    source: str


@dataclass(frozen=True)
class NarrativeHypothesis:
    headline_or_lead: str
    source_url: str
    source_platform: str
    posted_at: int
    discussion_strength: str  # one_observation | multiple_independent_origins
    factual_status: str  # unverified
    investigator_instruction: str


@dataclass(frozen=True)
class ResearchPacket:
    schema_version: int
    candidate_id: str
    move_window: MoveWindow
    search_query: str
    social_observations: int
    news_observations: int
    hypotheses: tuple[NarrativeHypothesis, ...]
    source_errors: tuple[str, ...]
    trace: tuple[str, ...]
    recommended_angle: str
    publication_rights: str = "SHADOW_ONLY"

    def to_dict(self) -> dict:
        return asdict(self)


def search_terms(question: str) -> str:
    """Deterministic search seed. Agent adapters can later refine it."""
    words = re.findall(r"[\w'-]+", question.lower(), flags=re.UNICODE)
    meaningful = [word for word in words
                  if (len(word) > 2 or word.isdecimal()) and word not in STOPWORDS]
    return " ".join(meaningful[:7])[:110] or "prediction market"


def identify_move_window(candidate: Candidate, prices: tuple[PricePoint, ...]) -> MoveWindow:
    signal = candidate.signal
    points = [point for point in prices if signal.baseline_at <= point.timestamp <= signal.observed_at]
    if len(points) >= 2:
        a, b = max(zip(points, points[1:]),
                   key=lambda pair: abs(pair[1].yes_price - pair[0].yes_price))
        if a.timestamp < b.timestamp:
            return MoveWindow(a.timestamp, b.timestamp, "sampled_interval", "polymarket_clob")
    return MoveWindow(signal.baseline_at, signal.observed_at,
                      "sparse_history", "daily_snapshots")


def _token_relevance(seed: str, lead: SourceLead) -> int:
    tokens = {word for word in seed.lower().split() if len(word) > 2}
    found = set(re.findall(r"[\w'-]+", lead.title.lower()))
    return len(tokens & found)


class NarrativeScout:
    """One bounded pass across public sources; never certifies hypotheses."""

    def __init__(self, history: HistorySource, bluesky: DiscoverySource,
                 news: DiscoverySource):
        self.history = history
        self.bluesky = bluesky
        self.news = news

    def investigate(self, candidate: Candidate) -> ResearchPacket:
        trace = ["candidate_received"]
        errors = []
        signal = candidate.signal
        try:
            history = self.history.between(
                candidate.market.yes_token_id, signal.baseline_at, signal.observed_at
            )
            trace.append("price_history_collected")
        except Exception as exc:
            # Never propagate raw network errors or URL/token values.
            errors.append(f"history:{type(exc).__name__}")
            history = ()
            trace.append("price_history_unavailable")
        movement = identify_move_window(candidate, history)
        query = search_terms(candidate.market.question)
        # Include a small margin because posts can precede the initial trade.
        since = max(1, movement.start_at - 3 * 3600)
        until = min(signal.observed_at + 3600, movement.end_at + 3 * 3600)
        outputs: list[tuple[str, tuple[SourceLead, ...]]] = []
        for name, source in (("bluesky", self.bluesky), ("gdelt", self.news)):
            try:
                results = source.search(query, since, until, limit=20)
                outputs.append((name, results))
                trace.append(f"{name}_searched")
            except Exception as exc:
                errors.append(f"{name}:{type(exc).__name__}")
                outputs.append((name, ()))
                trace.append(f"{name}_unavailable")
        social = next(results for name, results in outputs if name == "bluesky")
        news = next(results for name, results in outputs if name == "gdelt")
        leads: list[SourceLead] = []
        seen = set()
        for _, group in outputs:
            for lead in group:
                if (lead.url in seen or lead.posted_at < since or lead.posted_at > until
                        or not lead.url.startswith("https://")):
                    continue
                seen.add(lead.url)
                if _token_relevance(query, lead) == 0:
                    continue
                leads.append(lead)
        leads.sort(key=lambda lead: (-_token_relevance(query, lead),
                                     abs(lead.posted_at - movement.start_at), lead.url))
        # Duplicate/reshared statements and same-author posts do not count as
        # independent corroboration. This field ONLY describes discussion.
        unique_origins = {lead.author_key for lead in leads if lead.author_key}
        attention = ("multiple_independent_origins" if len(unique_origins) >= 2
                     else "one_observation")
        hypotheses = tuple(NarrativeHypothesis(
            headline_or_lead=lead.title[:240],
            source_url=lead.url,
            source_platform=lead.platform,
            posted_at=lead.posted_at,
            discussion_strength=attention,
            factual_status="unverified",
            investigator_instruction=(
                "Identify original primary evidence, check timing and event rules, "
                "find contradictory evidence, and do not infer a catalyst."
            ),
        ) for lead in leads[:3])
        trace.append("candidate_hypotheses_ranked")
        return ResearchPacket(
            schema_version=1, candidate_id=candidate.candidate_id,
            move_window=movement, search_query=query,
            social_observations=len(social), news_observations=len(news),
            hypotheses=hypotheses, source_errors=tuple(errors), trace=tuple(trace),
            recommended_angle=(
                "Describe only the verified market movement. Treat all discovered "
                "posts/article headlines as unverified leads until primary-source "
                "verification succeeds. No causal assertion or auto-publication."
            ),
        )
