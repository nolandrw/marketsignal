"""Bounded public, read-only sources for the investigative shadow pipeline.

No authentication, paid APIs, arbitrary URL fetching, or raw social archives.
All endpoints are fixed; caller input is encoded as query parameters.
"""

from __future__ import annotations

import json
import hashlib
import math
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


MAX_RESPONSE_BYTES = 768 * 1024
ALLOWED_HOSTS = {
    "clob.polymarket.com",
    "gamma-api.polymarket.com",
    "external-api.kalshi.com",
    "public.api.bsky.app",
    "api.gdeltproject.org",
    "api.crossref.org",
}


class SourceError(RuntimeError):
    """An expected source failure with no sensitive URL or response body."""


class JSONTransport(Protocol):
    def get(self, base_url: str, params: dict[str, str | int]) -> object: ...


class _RejectRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class PublicJSONTransport:
    def __init__(self, timeout: float = 8.0, retries: int = 1):
        if not 0 < timeout <= 30 or not 0 <= retries <= 2:
            raise ValueError("Unbounded HTTP budget")
        self.timeout = timeout
        self.retries = retries
        self.opener = build_opener(_RejectRedirect)

    def get(self, base_url: str, params: dict[str, str | int]) -> object:
        parsed = urlsplit(base_url)
        if (parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS or
                parsed.port is not None or parsed.username is not None or
                parsed.password is not None or parsed.query or parsed.fragment):
            raise SourceError("Source host is not allowlisted")
        url = base_url + "?" + urlencode(params)
        request = Request(url, headers={
            "User-Agent": "MarketSignalResearch/0.4 (public portfolio project; read-only)",
            "Accept": "application/json",
        })
        for attempt in range(self.retries + 1):
            try:
                with self.opener.open(request, timeout=self.timeout) as response:
                    try:
                        declared = int(response.headers.get("Content-Length", "0"))
                    except ValueError:
                        raise SourceError("Malformed source response metadata") from None
                    if declared < 0 or declared > MAX_RESPONSE_BYTES:
                        raise SourceError("Source response exceeds cap")
                    raw = response.read(MAX_RESPONSE_BYTES + 1)
                    if len(raw) > MAX_RESPONSE_BYTES:
                        raise SourceError("Source response exceeds cap")
                    return json.loads(raw.decode("utf-8"))
            except HTTPError as exc:
                if exc.code in (429, 502, 503, 504) and attempt < self.retries:
                    time.sleep(0.25 * (attempt + 1))
                    continue
                raise SourceError(f"HTTP source failure {exc.code}") from None
            except (URLError, TimeoutError):
                if attempt < self.retries:
                    time.sleep(0.25 * (attempt + 1))
                    continue
                raise SourceError("Source network unavailable") from None
            except (UnicodeError, json.JSONDecodeError):
                if attempt < self.retries:
                    time.sleep(0.25 * (attempt + 1))
                    continue
                raise SourceError("Source response is not valid JSON") from None
        raise SourceError("Source retry budget exhausted")


@dataclass(frozen=True)
class PricePoint:
    timestamp: int
    yes_price: float


@dataclass(frozen=True)
class SourceLead:
    platform: str
    url: str
    title: str
    posted_at: int
    author_key: str = ""
    # These are DISCOVERY leads, not independently verified event facts.


@dataclass(frozen=True)
class CommentPulse:
    event_id: str
    observed_comments: int
    recent_comments_24h: int
    distinct_recent_accounts: int
    theory_leads: tuple[SourceLead, ...]
    evidence_grade: str = "unverified_discussion_only"


class PolymarketComments:
    """Read bounded event comments as *hypothesis seeds*, never fact evidence."""

    ENDPOINT = "https://gamma-api.polymarket.com/comments"

    def __init__(self, transport: JSONTransport):
        self.transport = transport

    def pulse(self, event_id: str, event_slug: str, observed_at: int,
              *, limit: int = 30) -> CommentPulse:
        if (not event_id.isdigit() or not 1 <= len(event_id) <= 30 or
                not re.fullmatch(r"[a-zA-Z0-9_-]{1,120}", event_slug) or
                not 1 <= limit <= 30 or observed_at <= 0):
            raise ValueError("Invalid comment lookup")
        rows = self.transport.get(self.ENDPOINT, {
            "parent_entity_type": "Event", "parent_entity_id": int(event_id),
            "limit": limit, "order": "createdAt", "ascending": "false",
        })
        if not isinstance(rows, list):
            raise SourceError("Unexpected comment response")
        ids: set[str] = set()
        authors: set[str] = set()
        leads = []
        recent_count = 0
        for item in rows[:limit]:
            if not isinstance(item, dict):
                continue
            comment_id = _text(item.get("id"), 90)
            if not comment_id or comment_id in ids:
                continue
            ids.add(comment_id)
            created = _timestamp(item.get("createdAt"))
            if not observed_at - 86400 <= created <= observed_at:
                continue
            recent_count += 1
            author = _text(item.get("userAddress"), 160)
            if author:
                # Only count distinct authors; do not return or archive IDs.
                authors.add(hashlib.sha256(author.encode()).hexdigest())
            body = _text(item.get("body"), 220)
            if len(body) >= 25 and len(leads) < 5:
                leads.append(SourceLead(
                    "polymarket_comment_unverified",
                    f"https://polymarket.com/event/{event_slug}", body, created,
                ))
        return CommentPulse(event_id, len(ids), recent_count, len(authors), tuple(leads))


def _text(value: object, length: int = 240) -> str:
    return str(value or "").replace("\x00", "").strip()[:length]


def _timestamp(value: object) -> int:
    if isinstance(value, (int, float)):
        return int(value) if math.isfinite(value) and value > 0 else 0
    if not isinstance(value, str) or not value:
        return 0
    try:
        return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp())
    except ValueError:
        pass
    for pattern in ("%Y%m%dT%H%M%SZ", "%Y-%m-%d %H:%M:%S"):
        try:
            return int(datetime.strptime(value, pattern).replace(tzinfo=timezone.utc).timestamp())
        except ValueError:
            continue
    return 0


def _https_public_url(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        url = urlsplit(value)
        return (url.scheme == "https" and bool(url.hostname) and
                not url.username and not url.password and
                not any(c.isspace() for c in value) and len(value) <= 1200)
    except ValueError:
        return False


class PolymarketHistory:
    ENDPOINT = "https://clob.polymarket.com/prices-history"

    def __init__(self, transport: JSONTransport):
        self.transport = transport

    def between(self, token_id: str, since: int, until: int) -> tuple[PricePoint, ...]:
        if (not re.fullmatch(r"[0-9]{10,120}", token_id) or until <= since or
                until - since > 7 * 86400):
            raise ValueError("Invalid historical price request")
        result = self.transport.get(self.ENDPOINT, {
            "market": token_id, "startTs": since, "endTs": until, "fidelity": 30,
        })
        history = result.get("history", []) if isinstance(result, dict) else []
        if not isinstance(history, list):
            raise SourceError("Malformed price history")
        points = []
        for row in history[:500]:
            if not isinstance(row, dict):
                continue
            t, p = row.get("t"), row.get("p")
            try:
                timestamp, price = int(t), float(p)
            except (ValueError, TypeError):
                continue
            if since <= timestamp <= until and math.isfinite(price) and 0 <= price <= 1:
                points.append(PricePoint(timestamp, price))
        return tuple(sorted({p.timestamp: p for p in points}.values(), key=lambda x: x.timestamp))


class BlueskySearch:
    ENDPOINT = "https://public.api.bsky.app/xrpc/app.bsky.feed.searchPosts"

    def __init__(self, transport: JSONTransport):
        self.transport = transport

    def search(self, query: str, since: int, until: int, limit: int = 20) -> tuple[SourceLead, ...]:
        if not 1 <= limit <= 30 or not 2 <= len(query) <= 120 or until <= since:
            raise ValueError("Invalid Bluesky search bounds")
        result = self.transport.get(self.ENDPOINT, {
            "q": query, "sort": "latest", "limit": limit,
            "since": datetime.fromtimestamp(since, timezone.utc).isoformat(),
            "until": datetime.fromtimestamp(until, timezone.utc).isoformat(),
        })
        posts = result.get("posts", []) if isinstance(result, dict) else []
        if not isinstance(posts, list):
            raise SourceError("Malformed Bluesky response")
        leads = []
        for post in posts[:limit]:
            if not isinstance(post, dict):
                continue
            author = post.get("author") or {}
            record = post.get("record") or {}
            if not isinstance(author, dict) or not isinstance(record, dict):
                continue
            handle = _text(author.get("handle"), 120)
            uri = _text(post.get("uri"), 400)
            rkey = uri.rsplit("/", 1)[-1]
            if (not re.fullmatch(r"[a-zA-Z0-9.-]+", handle) or
                    not re.fullmatch(r"[a-zA-Z0-9]+", rkey)):
                continue
            published = _timestamp(record.get("createdAt"))
            if not since <= published <= until:
                continue
            url = f"https://bsky.app/profile/{handle}/post/{rkey}"
            leads.append(SourceLead("bluesky", url, _text(record.get("text")), published,
                                    _text(author.get("did"), 160)))
        return tuple(leads)


class GDELTSearch:
    ENDPOINT = "https://api.gdeltproject.org/api/v2/doc/doc"

    def __init__(self, transport: JSONTransport):
        self.transport = transport

    def search(self, query: str, since: int, until: int, limit: int = 20) -> tuple[SourceLead, ...]:
        if not 1 <= limit <= 30 or not 2 <= len(query) <= 120 or until <= since:
            raise ValueError("Invalid GDELT search bounds")
        def date(value: int) -> str:
            return datetime.fromtimestamp(value, timezone.utc).strftime("%Y%m%d%H%M%S")
        result = self.transport.get(self.ENDPOINT, {
            "query": query, "mode": "artlist", "format": "json",
            "startdatetime": date(since), "enddatetime": date(until),
            "maxrecords": limit,
        })
        rows = result.get("articles", []) if isinstance(result, dict) else []
        if not isinstance(rows, list):
            raise SourceError("Malformed GDELT response")
        leads = []
        for row in rows[:limit]:
            if not isinstance(row, dict) or not _https_public_url(row.get("url")):
                continue
            published = _timestamp(row.get("seendate"))
            if not since <= published <= until:
                continue
            leads.append(SourceLead("gdelt", row["url"], _text(row.get("title")),
                                    published, _text(row.get("domain"), 150)))
        return tuple(leads)


class CrossrefSearch:
    """Published academic metadata leads; neither peer review nor fact proof."""

    ENDPOINT = "https://api.crossref.org/works"

    def __init__(self, transport: JSONTransport):
        self.transport = transport

    def search(self, query: str, since: int, until: int, limit: int = 10) -> tuple[SourceLead, ...]:
        if not 1 <= limit <= 20 or not 3 <= len(query.strip()) <= 120 or not 0 < since < until:
            raise ValueError("Invalid scholarly search bounds")
        result = self.transport.get(self.ENDPOINT, {
            "query.bibliographic": query, "rows": limit,
            "filter": "from-pub-date:" + datetime.fromtimestamp(since, timezone.utc).strftime("%Y-%m-%d") +
                      ",until-pub-date:" + datetime.fromtimestamp(until, timezone.utc).strftime("%Y-%m-%d"),
        })
        message = result.get("message", {}) if isinstance(result, dict) else {}
        items = message.get("items", []) if isinstance(message, dict) else []
        if not isinstance(items, list):
            raise SourceError("Malformed Crossref response")
        leads = []
        for row in items[:limit]:
            if not isinstance(row, dict):
                continue
            title = row.get("title")
            title = title[0] if isinstance(title, list) and title else ""
            date = row.get("published") or row.get("issued") or {}
            dateparts = date.get("date-parts", [[]]) if isinstance(date, dict) else [[]]
            try:
                parts = dateparts[0]
                y, m, d = int(parts[0]), int(parts[1]) if len(parts) > 1 else 1, \
                    int(parts[2]) if len(parts) > 2 else 1
                published = int(datetime(y, m, d, tzinfo=timezone.utc).timestamp())
            except (TypeError, ValueError, IndexError, OverflowError):
                continue
            url = row.get("URL") or ""
            if not since <= published <= until or not _https_public_url(url) or not title:
                continue
            leads.append(SourceLead("crossref", url, _text(title, 240), published,
                                    _text(row.get("publisher"), 150)))
        return tuple(leads)
