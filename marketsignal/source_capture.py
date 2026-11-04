"""Conservative multi-format source capture from an explicit publisher allowlist.

GDELT and social results are *leads*. This gateway separately retrieves a
bounded public page after checking the site's robots policy. It persists only
small verbatim excerpts plus provenance; it does not verify their truth,
authorize republication, or bypass access controls.
"""

from __future__ import annotations

import hashlib
import html
import ipaddress
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from urllib.robotparser import RobotFileParser

from .context_discovery import ContextDiscoveryPacket, ContextLead
from .document_ingestion import (MAX_DOCUMENT_BYTES, SUPPORTED_MIME,
                                 ExtractionHold, extract_document, parse_date)


USER_AGENT = "MarketSignalResearchBot"
MAX_HTML_BYTES = 240_000
MAX_ROBOTS_BYTES = 40_000


class CaptureError(RuntimeError):
    """Sanitized capture failure; never includes retrieved text or user URLs."""


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


@dataclass(frozen=True)
class HostPermission:
    host: str
    kind: str  # official_record | original_research | independent_reporting
    copyright_basis: str  # official_public_record | permissioned_short_excerpt
    max_capture_bytes: int = 2_000_000

    def __post_init__(self):
        if (not re.fullmatch(r"[a-z0-9.-]{5,120}", self.host) or
                self.host.startswith(".") or ".." in self.host or
                self.host in ("localhost", "metadata.google.internal") or
                self.host.endswith((".localhost", ".local", ".internal", ".invalid", ".test")) or
                self.kind not in {"official_record", "original_research", "independent_reporting"} or
                self.copyright_basis not in {"official_public_record", "permissioned_short_excerpt"} or
                type(self.max_capture_bytes) is not int or not 64_000 <= self.max_capture_bytes <= MAX_DOCUMENT_BYTES):
            raise ValueError("Invalid publisher permission")
        if self.kind == "independent_reporting" and self.copyright_basis != "permissioned_short_excerpt":
            raise ValueError("Reporting requires explicit short-excerpt permission")
        if self.kind == "independent_reporting" and self.max_capture_bytes > 2_000_000:
            raise ValueError("Independent reporting capture cannot use large-document allowance")


class HTTPContent(Protocol):
    def get(self, url: str, *, max_bytes: int, media: str) -> str: ...


@dataclass(frozen=True)
class FetchedDocument:
    content: bytes
    mime_type: str


class PublicHTMLTransport:
    """No redirects/auth/cookies; bounded MIME-aware source fetch."""

    def __init__(self, timeout: float = 8):
        if not 1 <= timeout <= 20:
            raise ValueError("Unbounded HTTP timeout")
        self.timeout = timeout
        self._opener = build_opener(_NoRedirect)

    def _read(self, url: str, *, max_bytes: int, accept: str) -> FetchedDocument:
        try:
            request = Request(url, headers={
                "User-Agent": USER_AGENT + "/0.1 (+research; private short excerpts)",
                "Accept": accept,
            })
            with self._opener.open(request, timeout=self.timeout) as response:
                ctype = response.headers.get("Content-Type", "").split(";", 1)[0].lower().strip()
                declared = int(response.headers.get("Content-Length", "0"))
                pdf_download = (ctype == "application/octet-stream" and
                                urlsplit(url).path.lower().endswith(".pdf") and
                                accept != "text/plain")
                if (ctype not in SUPPORTED_MIME and not pdf_download or
                        declared < 0 or declared > max_bytes):
                    raise CaptureError("Publisher returned unsupported content or size")
                raw = response.read(max_bytes + 1)
                if len(raw) > max_bytes:
                    raise CaptureError("Publisher content exceeded budget")
            if pdf_download and raw.startswith(b"%PDF-"):
                ctype = "application/pdf"
            if ctype not in SUPPORTED_MIME:
                raise CaptureError("Publisher returned unsupported content type")
            return FetchedDocument(raw, ctype)
        except (HTTPError, URLError, TimeoutError, ValueError, OSError) as exc:
            raise CaptureError("Publisher retrieval failed: " + type(exc).__name__) from None

    def get(self, url: str, *, max_bytes: int, media: str) -> str:
        """Legacy exact-MIME text path (including robots.txt)."""
        if media not in ("text/html", "text/plain") or not 1 <= max_bytes <= MAX_HTML_BYTES:
            raise CaptureError("Invalid content request")
        document = self._read(url, max_bytes=max_bytes, accept=media)
        if document.mime_type != media:
            raise CaptureError("Publisher returned unsupported content type")
        try:
            return document.content.decode("utf-8")
        except UnicodeError:
            raise CaptureError("Publisher returned unsupported text encoding") from None

    def fetch_document(self, url: str, *, max_bytes: int) -> FetchedDocument:
        if not 1 <= max_bytes <= MAX_DOCUMENT_BYTES:
            raise CaptureError("Invalid document size budget")
        return self._read(url, max_bytes=max_bytes,
                          accept="text/html,application/pdf,application/json,text/csv,application/xml,"
                                 "application/rss+xml,application/atom+xml,text/plain")


class _ArticleParser(HTMLParser):
    """Extract bounded blocks; broad fallback is for approved official records."""

    def __init__(self, *, require_article: bool = True):
        super().__init__(convert_charrefs=True)
        self.require_article = require_article
        self._container = 0
        self._skip = 0
        self._paragraph = 0
        self._current: list[str] = []
        self.paragraphs: list[str] = []
        self.publisher_date: str | None = None

    def handle_starttag(self, tag: str, attrs):
        attributes = dict(attrs)
        if tag == "meta" and (attributes.get("property", "") or
                               attributes.get("name", "")).lower() in (
                "article:published_time", "datepublished", "date",
                "citation_publication_date", "dc.date.issued", "pubdate"):
            self.publisher_date = attributes.get("content", "")[:80]
        if tag == "time" and attributes.get("datetime") and not self.publisher_date:
            self.publisher_date = attributes["datetime"][:80]
        if tag in ("script", "style", "nav", "footer", "header", "aside", "form"):
            self._skip += 1
        if tag in ("main", "article"):
            self._container += 1
        if tag in (("p", "blockquote", "h1", "h2") if self.require_article else
                   ("p", "blockquote", "h1", "h2", "h3", "li", "td", "th")) and (self._container or not self.require_article) and not self._skip:
            self._paragraph += 1
            if self._paragraph == 1:
                self._current = []

    def handle_endtag(self, tag: str):
        if tag in ("p", "blockquote", "h1", "h2", "h3", "li", "td", "th") and self._paragraph:
            self._paragraph -= 1
            if self._paragraph == 0 and self._current:
                text = re.sub(r"\s+", " ", "".join(self._current)).strip()
                if len(text) >= 35:
                    self.paragraphs.append(text)
                self._current = []
        if tag in ("main", "article"):
            self._container = max(0, self._container - 1)
        if tag in ("script", "style", "nav", "footer", "header", "aside", "form"):
            self._skip = max(0, self._skip - 1)

    def handle_data(self, data: str):
        if (self._container or not self.require_article) and self._paragraph and not self._skip:
            self._current.append(data)


def _safe_host(url: str, permissions: dict[str, HostPermission]) -> str:
    if not isinstance(url, str) or not 1 <= len(url) <= 1100 or any(c.isspace() for c in url):
        raise CaptureError("Invalid URL metadata")
    try:
        parts = urlsplit(url)
        host = (parts.hostname or "").lower()
        if (parts.scheme != "https" or host not in permissions or
                parts.username is not None or parts.password is not None or
                parts.port is not None or parts.fragment or
                any(char in host for char in ("@", "_"))):
            raise CaptureError("Publisher is not approved")
        try:
            ipaddress.ip_address(host)
        except ValueError:
            pass
        else:
            raise CaptureError("IP literal hosts are not permitted")
        return host
    except ValueError:
        raise CaptureError("Malformed publisher URL") from None


@dataclass(frozen=True)
class ArticleCapture:
    url: str
    publisher: str
    published_at: int
    captured_at: int
    origin: str
    kind: str
    copyright_basis: str
    document_sha256: str
    excerpts: tuple[str, ...]
    publication_date_basis: str = "publisher_page_metadata"
    robots_decision: str = "allowed"
    verified_truth: bool = False
    permission_to_republish: bool = False
    mime_type: str = "text/html"
    excerpt_locations: tuple[str, ...] = ()
    extraction_method: str = "html_paragraphs"
    partial_extraction: bool = False

    def source_rows(self) -> list[dict]:
        rows = []
        prefix = "s" + hashlib.sha256(self.url.encode()).hexdigest()[:16]
        for index, excerpt in enumerate(self.excerpts, 1):
            rows.append({
                "source_id": f"{prefix}p{index}",
                "publisher": self.publisher,
                "url": self.url,
                "published_at": datetime.fromtimestamp(self.published_at, timezone.utc).isoformat().replace("+00:00", "Z"),
                "independent_origin": self.origin,
                "kind": self.kind,
                "captured_excerpt": excerpt,
                "captured_at": self.captured_at,
                "publication_date_basis": self.publication_date_basis,
                "document_sha256": self.document_sha256,
                "copyright_basis": self.copyright_basis,
                "robots_decision": self.robots_decision,
                "mime_type": self.mime_type,
                "content_location": (self.excerpt_locations[index - 1]
                                     if index <= len(self.excerpt_locations) else "unknown"),
                "extraction_method": self.extraction_method,
                "partial_extraction": self.partial_extraction,
            })
        return rows


class SourceCaptureGateway:
    """Accesses only explicitly approved hosts, subject to robots and limits."""

    def __init__(self, permissions: tuple[HostPermission, ...],
                 transport: HTTPContent | None = None):
        if not 1 <= len(permissions) <= 30 or len({p.host for p in permissions}) != len(permissions):
            raise ValueError("Invalid publisher allowlist")
        self.permissions = {p.host: p for p in permissions}
        self.transport = transport or PublicHTMLTransport()
        self._robots: dict[str, RobotFileParser] = {}

    def _permission(self, host: str, url: str) -> None:
        robot = self._robots.get(host)
        if robot is None:
            robots_url = f"https://{host}/robots.txt"
            raw = self.transport.get(robots_url, max_bytes=MAX_ROBOTS_BYTES, media="text/plain")
            if len(raw) > MAX_ROBOTS_BYTES:
                raise CaptureError("Publisher robots policy exceeded budget")
            robot = RobotFileParser()
            robot.set_url(robots_url)
            robot.parse(raw.splitlines())
            self._robots[host] = robot
        if not robot.can_fetch(USER_AGENT, url):
            raise CaptureError("Publisher robots policy denied capture")
        crawl_delay = robot.crawl_delay(USER_AGENT)
        if crawl_delay is not None and crawl_delay > 10:
            raise CaptureError("Publisher crawl-delay exceeds research budget")

    def capture(self, lead: ContextLead, *, observed_at: int) -> ArticleCapture:
        host = _safe_host(lead.url, self.permissions)
        if not 0 < lead.published_at <= observed_at or lead.factual_status != "discovery_only":
            raise CaptureError("Lead date/status is not eligible for capture")
        self._permission(host, lead.url)
        if hasattr(self.transport, "fetch_document"):
            document = self.transport.fetch_document(
                lead.url, max_bytes=self.permissions[host].max_capture_bytes)
        else:
            legacy = self.transport.get(lead.url, max_bytes=MAX_HTML_BYTES, media="text/html")
            document = FetchedDocument(legacy.encode("utf-8"), "text/html")
        trusted_feed_date = (lead.published_at if
                             getattr(lead, "publication_date_basis", "") == "first_party_official_feed" and
                             self.permissions[host].kind == "official_record" and
                             lead.publisher.lower() == host else None)
        mime = document.mime_type
        try:
            if mime in {"text/html", "application/xhtml+xml"}:
                raw = document.content.decode("utf-8")
                parser = _ArticleParser()
                parser.feed(raw)
                published_at = parse_date(parser.publisher_date)
                basis = "publisher_page_metadata" if published_at is not None else None
                if published_at is None and trusted_feed_date is not None:
                    published_at, basis = trusted_feed_date, "first_party_official_feed"
                paragraphs = [html.unescape(p) for p in parser.paragraphs]
                selected_with_locations = [(f"html:paragraph:{i}", p[:370])
                                           for i, p in enumerate(paragraphs, 1) if len(p) >= 45][:3]
                if (self.permissions[host].kind == "official_record" and
                        (sum(map(len, paragraphs)) < 220 or len(selected_with_locations) < 2)):
                    broad = _ArticleParser(require_article=False)
                    broad.feed(raw)
                    paragraphs = [html.unescape(p) for p in broad.paragraphs]
                    selected_with_locations = [(f"html:paragraph:{i}", p[:370])
                                               for i, p in enumerate(paragraphs, 1) if len(p) >= 45][:3]
                    method = "html_official_record_blocks"
                else:
                    method = "html_paragraphs"
                if sum(map(len, paragraphs)) < 220 or len(selected_with_locations) < 2:
                    raise CaptureError("Insufficient dated publisher HTML text")
                locations = tuple(place for place, _ in selected_with_locations)
                selected = [text for _, text in selected_with_locations]
                partial = False
            else:
                extracted = extract_document(document.content, mime,
                                             trusted_feed_date=trusted_feed_date)
                published_at, basis = extracted.published_at, extracted.date_basis
                selected, locations = extracted.excerpts, extracted.locations
                method, partial = extracted.extraction_method, extracted.partial_extraction
        except (UnicodeError, ExtractionHold) as exc:
            raise CaptureError("Unsupported or unextractable document: " + type(exc).__name__) from None
        if published_at is None or not 0 < published_at <= observed_at:
            raise CaptureError("Publisher publication timestamp unavailable or future")
        return ArticleCapture(
            url=lead.url, publisher=host,
            published_at=published_at,
            captured_at=int(datetime.now(timezone.utc).timestamp()),
            origin=host, kind=self.permissions[host].kind,
            copyright_basis=self.permissions[host].copyright_basis,
            document_sha256=hashlib.sha256(document.content).hexdigest(),
            excerpts=tuple(selected),
            publication_date_basis=basis or "unavailable",
            mime_type=mime, excerpt_locations=tuple(locations),
            extraction_method=method, partial_extraction=partial,
        )


def capture_discovery(packet: ContextDiscoveryPacket, gateway: SourceCaptureGateway,
                      *, observed_at: int, max_pages: int = 6) -> dict:
    """Produce a bounded private evidence inventory, never factual claims."""
    if not 1 <= max_pages <= 10:
        raise ValueError("Unbounded capture request")
    captured: list[ArticleCapture] = []
    status_counts: dict[str, int] = {}
    seen: set[str] = set()
    for lead in packet.leads:
        if len(captured) >= max_pages:
            break
        if lead.url in seen:
            continue
        seen.add(lead.url)
        try:
            captured.append(gateway.capture(lead, observed_at=observed_at))
        except CaptureError as exc:
            reason = str(exc)
            status_counts[reason] = status_counts.get(reason, 0) + 1
    sources = [row for capture in captured for row in capture.source_rows()]
    origins = {row["independent_origin"] for row in sources}
    checks = {
        "multiple_captured_pages": len(captured) >= 3,
        "three_independent_origins": len(origins) >= 3,
        "primary_record_included": any(row["kind"] in ("official_record", "original_research") for row in sources),
        "independent_reporting_included": any(row["kind"] == "independent_reporting" for row in sources),
        "publisher_date_recorded": bool(sources) and all(row["publication_date_basis"] in {
            "publisher_page_metadata", "embedded_json_metadata", "embedded_xml_metadata",
            "first_party_official_feed"} for row in sources),
        "robots_policy_allowed": bool(sources) and all(row["robots_decision"] == "allowed" for row in sources),
        "full_document_digest": bool(sources) and all(len(row["document_sha256"]) == 64 for row in sources),
        "bounded_excerpt_size": bool(sources) and all(45 <= len(row["captured_excerpt"]) <= 370 for row in sources),
        "approved_https_source": bool(sources) and all(row["url"].startswith("https://") for row in sources),
        "no_publication_authority": True,
    }
    return {
        "schema_version": 1,
        "candidate_id": packet.candidate_id,
        "as_of_utc": datetime.fromtimestamp(observed_at, timezone.utc).isoformat().replace("+00:00", "Z"),
        "source_rows": sources,
        "capture_counts": {"leads_considered": len(seen), "pages_captured": len(captured),
                           "excerpts_saved": len(sources), "held_reasons": status_counts},
        "source_contents_retrieved": bool(sources),
        "claims_semantically_verified": False,
        "publication_enabled": False,
        "capture_process_rubric": {"score": 10 * sum(checks.values()),
                                   "threshold": 90, "checks": checks,
                                   "measures": "capture_contract_coverage_not_fact_accuracy"},
    }
