"""Multi-source read-only research, separating discovery from citeable captures.

Provider adapters are injected. No general-purpose arbitrary web fetch, paid
API, X/Reddit scraping, account access or automatic social-content archiving.
Newspaper stories and primary records become citeable only after approved
publisher capture. Social results are unverified hypothesis/coverage leads.
"""

from __future__ import annotations

import hashlib
import ipaddress
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Protocol
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from xml.etree import ElementTree

from .agent_sources import CommentPulse, SourceLead
from .context_discovery import ContextLead
from .investigator_v3 import ResearchBatch, ResearchCapture, ResearchLead
from .source_capture import ArticleCapture, CaptureError, SourceCaptureGateway


@dataclass(frozen=True)
class SourcePolicy:
    connector_id: str
    class_name: str  # official | journalism | research | discussion | market_discussion
    role: str  # official_lead | coverage | research_lead | discussion
    allowed_to_capture: bool
    access: str  # public | configured | permission_required
    launch_status: str = "configured"

    def __post_init__(self):
        if (not re.fullmatch(r"[a-z][a-z0-9_]{1,39}", self.connector_id) or
                self.class_name not in {"official", "journalism", "research", "discussion", "market_discussion"} or
                self.role not in {"official_lead", "coverage", "research_lead", "discussion"} or
                self.access not in {"public", "configured", "permission_required"} or
                self.launch_status not in {"configured", "deferred"} or
                (self.role == "discussion" and self.allowed_to_capture)):
            raise ValueError("Invalid research source policy")


# This is a product coverage map, not a claim that every access path is live.
SOURCE_CATALOG = (
    SourcePolicy("official_feeds", "official", "official_lead", True, "configured"),
    SourcePolicy("gdelt_news", "journalism", "coverage", True, "public"),
    SourcePolicy("crossref", "research", "research_lead", False, "public"),
    SourcePolicy("bluesky", "discussion", "discussion", False, "public"),
    SourcePolicy("polymarket_chat", "market_discussion", "discussion", False, "public"),
    SourcePolicy("x_search", "discussion", "discussion", False, "permission_required", "deferred"),
    SourcePolicy("reddit", "discussion", "discussion", False, "permission_required", "deferred"),
    SourcePolicy("scholarly_databases", "research", "research_lead", True, "configured", "deferred"),
    SourcePolicy("regulatory_dockets", "official", "official_lead", True, "configured", "deferred"),
)


class DiscoveryAdapter(Protocol):
    def search(self, query: str, since: int, until: int, limit: int = 4) -> tuple[SourceLead, ...]: ...


class OfficialFeedTransport(Protocol):
    def get(self, url: str) -> bytes: ...


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class PublicOfficialFeedTransport:
    """No-cookie, no-redirect RSS/Atom reads from explicitly approved hosts."""

    def __init__(self, allowed_hosts: tuple[str, ...], *, timeout: float = 8):
        if not 1 <= len(allowed_hosts) <= 24 or not 1 <= timeout <= 15:
            raise ValueError("Unsafe official feed transport budget")
        for host in allowed_hosts:
            if (not re.fullmatch(r"[a-z0-9-]+(?:\.[a-z0-9-]+)+", host) or
                    host.endswith((".internal", ".local", ".localhost", ".invalid", ".test"))):
                raise ValueError("Unsafe official feed host")
            try:
                ipaddress.ip_address(host)
            except ValueError:
                pass
            else:
                raise ValueError("IP literals are not official feed hosts")
        self.allowed_hosts = frozenset(allowed_hosts)
        self.timeout = timeout
        self.opener = build_opener(_NoRedirect)

    def get(self, url: str) -> bytes:
        parsed = urlsplit(url)
        if (not OfficialFeedSearch._safe_feed(url) or
                parsed.hostname not in self.allowed_hosts):
            raise ValueError("Feed URL outside exact official host allowlist")
        request = Request(url, headers={
            "User-Agent": "MarketSignalResearch/0.5 (public-readonly-feed)",
            "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml",
        })
        try:
            with self.opener.open(request, timeout=self.timeout) as response:
                raw = response.read(256_001)
                if len(raw) > 256_000:
                    raise ValueError("Official feed exceeds response cap")
                return raw
        except (OSError, TimeoutError):
            raise RuntimeError("Official feed read unavailable") from None


class OfficialFeedSearch:
    """Configured government/institutional RSS/Atom discovery (metadata only).

    Feed retrieval is delegated to an allowlisted, no-redirect transport.
    Its implementation must enforce network permissions and bounded response
    sizes; feeds must never be followed to arbitrary hosts.
    """

    def __init__(self, feeds: tuple[str, ...], transport: OfficialFeedTransport):
        if (not 1 <= len(feeds) <= 12 or len(set(feeds)) != len(feeds) or
                any(not self._safe_feed(url) for url in feeds)):
            raise ValueError("Unsafe or unbounded official feed registry")
        self.feeds = feeds
        self.transport = transport

    @staticmethod
    def _safe_feed(url: str) -> bool:
        parsed = urlsplit(url)
        return (parsed.scheme == "https" and bool(parsed.hostname) and
                parsed.username is None and parsed.password is None and
                parsed.port is None and not parsed.fragment and len(url) <= 600)

    def search(self, query: str, since: int, until: int, limit: int = 4) -> tuple[SourceLead, ...]:
        if not 1 <= limit <= 12 or not 2 <= len(query) <= 180 or since >= until:
            raise ValueError("Invalid official feed search")
        tokens = {t.lower() for t in re.findall(r"[\w'-]{4,}", query)[:12]}
        if not tokens:
            return ()
        leads = []
        for feed in self.feeds:
            data = self.transport.get(feed)
            if len(data) > 256_000:
                raise ValueError("Oversized official feed")
            root = ElementTree.fromstring(data)
            entries = root.findall(".//item") + root.findall(".//{*}entry")
            for row in entries[:100]:
                title = (row.findtext("title") or row.findtext("{*}title") or "").strip()[:240]
                link = (row.findtext("link") or "").strip()
                if not link:
                    element = row.find("{*}link")
                    link = element.attrib.get("href", "") if element is not None else ""
                date_str = (row.findtext("pubDate") or row.findtext("{*}published") or
                            row.findtext("{*}updated") or "")
                try:
                    dt = parsedate_to_datetime(date_str) if "," in date_str else \
                         datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                    date = int(dt.timestamp()) if dt.tzinfo else 0
                except (TypeError, ValueError, OverflowError):
                    continue
                if (not since <= date <= until or not self._safe_feed(link) or
                        not any(t in title.lower() for t in tokens)):
                    continue
                leads.append(SourceLead("official_rss", link, title, date,
                                        urlsplit(feed).hostname or ""))
                if len(leads) >= limit:
                    return tuple(leads)
        return tuple(leads)


class PolymarketDiscussionSearch:
    """Optional event-specific chat hints, never population sentiment."""

    def __init__(self, comments, event_id: str, event_slug: str):
        self.comments, self.event_id, self.event_slug = comments, event_id, event_slug

    def search(self, query: str, since: int, until: int, limit: int = 4) -> tuple[SourceLead, ...]:
        pulse: CommentPulse = self.comments.pulse(self.event_id, self.event_slug, until,
                                                  limit=min(30, max(5, limit * 5)))
        return tuple(lead for lead in pulse.theory_leads if since <= lead.posted_at <= until)[:limit]


class MultiSourceResearchProvider:
    """Bounded fan-out, role-aware source retrieval for Investigator v3.

    Only official/research/journalism leads are eligible for permitted page
    capture, and even then a configured SourceCaptureGateway must approve the
    host and robots policy. X/Reddit require separate lawful integrations.
    """

    def __init__(self, connectors: dict[str, DiscoveryAdapter],
                 capture_gateway: SourceCaptureGateway, *,
                 max_provider_calls: int = 20, recent_days: int = 30,
                 coverage_days: int = 180, discussion_calls_per_source: int = 2):
        if (not 1 <= max_provider_calls <= 40 or not 1 <= recent_days <= 90 or
                not 30 <= coverage_days <= 365 or not 1 <= len(connectors) <= 6 or
                not 0 <= discussion_calls_per_source <= 4):
            raise ValueError("Unbounded source coverage budget")
        policies = {p.connector_id: p for p in SOURCE_CATALOG}
        if any(name not in policies or policies[name].launch_status != "configured"
               for name in connectors):
            raise ValueError("Unavailable or permission-gated connector")
        self.connectors, self.capture_gateway = dict(connectors), capture_gateway
        self.max_provider_calls = max_provider_calls
        self.recent_days, self.coverage_days = recent_days, coverage_days
        self.discussion_calls_per_source = discussion_calls_per_source
        self.calls = 0
        self.calls_by_source: dict[str, int] = {}
        self.captures: dict[str, ResearchCapture] = {}
        self.batches: list[ResearchBatch] = []

    def coverage_audit(self) -> dict:
        """A source-coverage rubric, NOT a measure of factual accuracy."""
        sources = [s for batch in self.batches for s in batch.sources_attempted]
        leads = [lead for batch in self.batches for lead in batch.leads]
        policies = {p.connector_id: p for p in SOURCE_CATALOG}
        captures = tuple(self.captures.values())
        checks = {
            "official_search_attempted": (10, any(policies[s].class_name == "official" for s in sources)),
            "official_record_captured": (20, any(s.source_kind == "official_record" for s in captures)),
            "journalism_search_attempted": (10, any(policies[s].class_name == "journalism" for s in sources)),
            "independent_reporting_captured": (15, any(s.source_kind == "independent_reporting" for s in captures)),
            "coverage_discovery_logged": (10, any(l.source_role == "coverage" for l in leads)),
            "multiple_original_origins": (10, len({s.origin_key for s in captures}) >= 2),
            "discussion_is_non_evidentiary": (10, all(l.source_role == "discussion"
                                                     for l in leads if policies[l.platform].class_name in
                                                     {"discussion", "market_discussion"})),
            "source_rights_boundary": (10, bool(captures) and all(s.source_kind in
                                              {"official_record", "original_research", "independent_reporting"}
                                              for s in captures)),
            "attempt_and_error_trail": (5, bool(self.batches) and bool(sources)),
        }
        return {
            "score": sum(weight for weight, passed in checks.values() if passed),
            "maximum": 100,
            "checks": {name: {"maximum": weight, "passed": passed}
                       for name, (weight, passed) in checks.items()},
            "captures": len(captures), "leads": len(leads),
            "source_calls": self.calls,
            "meaning": "source_coverage_diagnostic_not_fact_or_sentiment_validation",
            "publication_enabled": False,
        }

    def search(self, query: str, *, as_of: int, limit: int) -> ResearchBatch:
        if not 8 <= len(query.strip()) <= 180 or not 1 <= limit <= 4 or as_of <= 0:
            raise ValueError("Invalid multi-source query")
        policies = {p.connector_id: p for p in SOURCE_CATALOG}
        # Prioritize authoritative records and coverage; use conversation as
        # discovery only, not as a shortcut to verifying external events.
        priority = {"official": 0, "journalism": 1, "research": 2,
                    "discussion": 3, "market_discussion": 4}
        ordered = sorted(self.connectors, key=lambda name: priority[policies[name].class_name])
        captured = []
        leads = []
        attempted = []
        errors = []
        seen_urls = set()
        for name in ordered:
            if self.calls >= self.max_provider_calls:
                errors.append("provider_budget_exhausted")
                break
            policy = policies[name]
            if (policy.class_name in {"discussion", "market_discussion"} and
                    self.calls_by_source.get(name, 0) >= self.discussion_calls_per_source):
                errors.append(name + ":discussion_budget_exhausted")
                continue
            since = max(1, as_of - 86400 * (
                self.coverage_days if policy.class_name in {"official", "journalism", "research"}
                else self.recent_days))
            self.calls += 1
            self.calls_by_source[name] = self.calls_by_source.get(name, 0) + 1
            attempted.append(name)
            try:
                discovered = self.connectors[name].search(query, since, as_of, limit=limit)
                if not isinstance(discovered, (list, tuple)) or len(discovered) > limit:
                    raise ValueError("Unbounded discovery response")
            except (OSError, RuntimeError, TimeoutError, ValueError, TypeError, AttributeError) as exc:
                errors.append(name + ":" + type(exc).__name__)
                continue
            for item in discovered:
                if not isinstance(item, SourceLead) or item.url in seen_urls or not (
                        0 < item.posted_at <= as_of and item.url.startswith("https://")):
                    continue
                seen_urls.add(item.url)
                leads.append(ResearchLead(
                    platform=name, url=item.url, title=(item.title or "(untitled discovery)")[:300],
                    published_at=item.posted_at, source_role=policy.role,
                    origin_key=(hashlib.sha256(item.author_key.encode("utf-8")).hexdigest()[:20]
                                if policy.role == "discussion" and item.author_key else
                                item.author_key[:150]),
                ))
                if not policy.allowed_to_capture or len(captured) >= limit:
                    continue
                if item.url in self.captures:
                    captured.append(self.captures[item.url])
                    continue
                try:
                    page = self.capture_gateway.capture(ContextLead(
                        lead_id="lead" + hashlib.sha256(item.url.encode()).hexdigest()[:15],
                        role="contemporaneous_reporting", url=item.url,
                        title=item.title[:240], publisher=item.author_key[:150],
                        published_at=item.posted_at,
                        publication_date_basis=("first_party_official_feed"
                                                if name == "official_feeds" else "discovery_only")),
                        observed_at=as_of)
                    if not isinstance(page, ArticleCapture) or not page.excerpts:
                        raise CaptureError("Unusable capture")
                    capture = ResearchCapture(
                        source_id="s" + hashlib.sha256(item.url.encode()).hexdigest()[:20],
                        url=page.url, publisher=page.publisher, origin_key=page.origin,
                        published_at=page.published_at, captured_at=page.captured_at,
                        source_kind=page.kind,
                        excerpt="\n".join(page.excerpts)[:2500],
                        document_sha256=page.document_sha256,
                        content_location=";".join(page.excerpt_locations)[:500],
                        mime_type=page.mime_type,
                        publication_date_basis=page.publication_date_basis,
                    )
                    if capture.captured_at > as_of + 30 * 60:
                        # The v3 orchestrator applies the tighter historical
                        # replay rule; this layer rejects late live captures.
                        raise CaptureError("Capture postdates case as-of clock")
                    self.captures[item.url] = capture
                    captured.append(capture)
                except (CaptureError, ValueError, TypeError) as exc:
                    errors.append(name + ":capture_" + type(exc).__name__)
        batch = ResearchBatch(tuple(captured[:limit]), tuple(leads[:24]),
                              tuple(attempted), tuple(errors))
        self.batches.append(batch)
        return batch
