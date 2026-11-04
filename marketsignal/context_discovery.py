"""Broader historical/contextual article discovery after a market signal.

GDELT supplies metadata (URLs/titles/dates), not independently verified quotes
or source contents. All leads remain unverified and are never auto-published.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .agent_sources import SourceLead
from .editorial import Candidate, TriageAgent
from .investigation import search_terms
from .models import Market, Signal


class ArticleDiscovery(Protocol):
    def search(self, query: str, since: int, until: int, limit: int = 20) -> tuple[SourceLead, ...]: ...


@dataclass(frozen=True)
class ContextLead:
    lead_id: str
    role: str  # prior_reporting | contemporaneous_reporting | broader_stakes_search
    url: str
    title: str
    publisher: str
    published_at: int
    factual_status: str = "discovery_only"
    publication_date_basis: str = "discovery_only"


@dataclass(frozen=True)
class ContextDiscoveryPacket:
    candidate_id: str
    search_windows: tuple[str, ...]
    leads: tuple[ContextLead, ...]
    source_errors: tuple[str, ...]
    source_contents_retrieved: bool = False
    independent_claims_verified: bool = False
    publication_enabled: bool = False


class ContextDiscoveryAgent:
    """Three bounded searches; historical context is not 'public sentiment'."""

    def __init__(self, source: ArticleDiscovery):
        self.source = source

    def discover(self, candidate: Candidate) -> ContextDiscoveryPacket:
        if TriageAgent().check(candidate):
            return ContextDiscoveryPacket(candidate.candidate_id, (), (), ("invalid_signal",))
        subject = search_terms(candidate.market.event_title)[:90]
        question = search_terms(candidate.market.question)[:90]
        signal = candidate.signal
        windows = (
            ("prior_reporting", subject, max(1, signal.baseline_at - 45 * 86400),
             signal.baseline_at),
            ("contemporaneous_reporting", question,
             max(1, signal.baseline_at - 2 * 86400), signal.observed_at + 3600),
            ("broader_stakes_search", subject,
             max(1, signal.observed_at - 90 * 86400), signal.observed_at),
        )
        leads: list[ContextLead] = []
        errors: list[str] = []
        visited = set()
        for role, query, since, until in windows:
            if not query:
                continue
            try:
                results = self.source.search(query, since, until, limit=12)
            except Exception as exc:
                errors.append(f"{role}:{type(exc).__name__}")
                continue
            for found in results:
                if (found.url in visited or found.posted_at < since or
                        found.posted_at > until or not found.url.startswith("https://")):
                    continue
                visited.add(found.url)
                leads.append(ContextLead(
                    lead_id=hashlib.sha256(found.url.encode("utf-8")).hexdigest()[:20],
                    role=role, url=found.url, title=found.title[:240],
                    publisher=found.author_key[:150], published_at=found.posted_at,
                ))
        return ContextDiscoveryPacket(candidate.candidate_id,
                                      tuple(item[0] for item in windows),
                                      tuple(leads[:36]), tuple(errors))


def discover_archive(path: str | Path, source: ArticleDiscovery, *,
                     max_candidates: int = 2) -> dict:
    """Artifact intentionally excludes article titles, full URLs and authors."""
    if not 1 <= max_candidates <= 10:
        raise ValueError("Unbounded context candidate count")
    archive = Path(path)
    if archive.stat().st_size > 5_000_000:
        raise ValueError("Oversized archive")
    record = json.loads(archive.read_text(encoding="utf-8"))
    if record.get("schema_version") != 1 or not isinstance(record.get("signals"), list):
        raise ValueError("Malformed daily record")
    markets = {row["market_id"]: Market(**row) for row in record.get("markets", [])}
    agent = ContextDiscoveryAgent(source)
    results = []
    for item in record["signals"][:max_candidates]:
        signal = Signal(**item)
        if market := markets.get(signal.market_id):
            packet = agent.discover(Candidate(market, signal))
            results.append({
                "candidate_id": packet.candidate_id,
                "windows_attempted": len(packet.search_windows),
                "discovery_leads": len(packet.leads),
                "source_errors": list(packet.source_errors),
                "source_contents_retrieved": False,
                "independent_claims_verified": False,
                "publication_enabled": False,
            })
    return {"schema_version": 1, "mode": "context_discovery_shadow",
            "publication_enabled": False, "results": results}
