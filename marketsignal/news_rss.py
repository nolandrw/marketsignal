"""Bounded public news RSS discovery for unpublished market-curation briefs.

This is headline metadata, not article body capture or verification. All
requests go to fixed news-index hosts; links returned in the XML are never
fetched and can only be considered unverified publication leads.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener
from xml.etree import ElementTree

from .agent_sources import SourceError, SourceLead, _https_public_url


MAX_RSS_BYTES = 256_000
GOOGLE_URL = "https://news.google.com/rss/search"
BING_URL = "https://www.bing.com/news/search"


class _RejectRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class RSSNewsSearch:
    def __init__(self, *, timeout: float = 7, transport=None):
        if not 1 <= timeout <= 15:
            raise ValueError("Invalid bounded RSS timeout")
        self.timeout = timeout
        self.transport = transport
        self.opener = build_opener(_RejectRedirect)

    def _fetch(self, base: str, params: dict[str, str]) -> bytes:
        if base not in {GOOGLE_URL, BING_URL}:
            raise SourceError("Disallowed RSS provider")
        if self.transport is not None:
            return self.transport.get(base, params)
        req = Request(base + "?" + urlencode(params), headers={
            "User-Agent": "MarketSignalResearch/0.4 (+https://github.com/nolandrw/marketsignal)",
            "Accept": "application/rss+xml,application/xml",
        })
        try:
            with self.opener.open(req, timeout=self.timeout) as response:
                payload = response.read(MAX_RSS_BYTES + 1)
        except HTTPError as exc:
            raise SourceError(f"RSS provider HTTP {int(exc.code)}") from None
        except (URLError, OSError, TimeoutError):
            raise SourceError("RSS network unavailable") from None
        if len(payload) > MAX_RSS_BYTES:
            raise SourceError("RSS response exceeds cap")
        return payload

    def _collect(self, base: str, params: dict[str, str], since: int, until: int,
                 limit: int, provider: str) -> tuple[SourceLead, ...]:
        raw = self._fetch(base, params)
        if not isinstance(raw, bytes) or b"<!DOCTYPE" in raw.upper() or b"<!ENTITY" in raw.upper():
            raise SourceError("Unexpected or unsafe RSS payload")
        try:
            root = ElementTree.fromstring(raw)
        except ElementTree.ParseError:
            raise SourceError("RSS response is not well-formed XML") from None
        if root.tag != "rss":
            raise SourceError("RSS feed is not RSS 2.0")
        found: list[SourceLead] = []
        seen: set[str] = set()
        for item in root.findall("./channel/item")[:80]:
            title = (item.findtext("title") or "").strip()[:240]
            url = (item.findtext("link") or "").strip()
            publisher = (item.findtext("source") or "").strip()[:150]
            date_text = (item.findtext("pubDate") or "").strip()
            try:
                published = parsedate_to_datetime(date_text)
                if published.tzinfo is None:
                    continue
                timestamp = int(published.astimezone(timezone.utc).timestamp())
            except (TypeError, ValueError, OverflowError):
                continue
            if (not _https_public_url(url) or url in seen or
                    not 10 <= len(title) <= 240 or
                    not since <= timestamp <= until):
                continue
            if not publisher:
                # A title suffix is a hint, never an independently validated
                # byline; unknown publisher is not suitable for attribution.
                continue
            seen.add(url)
            found.append(SourceLead(provider, url, title, timestamp, publisher))
            if len(found) >= limit:
                break
        return tuple(found)

    def search(self, query: str, since: int, until: int,
               limit: int = 8) -> tuple[SourceLead, ...]:
        if (not isinstance(query, str) or not 8 <= len(query.strip()) <= 110 or
                not query.isprintable() or
                not 1 <= limit <= 12 or not 0 < since < until or
                until - since > 31 * 86400):
            raise ValueError("Invalid RSS discovery request bounds")

        # Include the UTC observation day so a recent-coverage window can
        # measure same-day chatter. The exact timestamp filter in _collect
        # still excludes posts published after the archived market snapshot.
        after = datetime.fromtimestamp(since, timezone.utc).strftime("%Y-%m-%d")
        before = (datetime.fromtimestamp(until, timezone.utc) +
                  timedelta(days=1)).strftime("%Y-%m-%d")
        google_params = {"q": f"{query} after:{after} before:{before}",
                         "hl": "en-US", "gl": "US", "ceid": "US:en"}
        try:
            leads = self._collect(GOOGLE_URL, google_params, since, until,
                                  limit, "google_news_rss")
            if leads:
                return leads
        except SourceError:
            pass
        # Bing News is an independent, already-probed metadata index. Its
        # results are still screened for publication dates and usable links.
        return self._collect(BING_URL, {"q": query, "format": "rss",
                                        "setlang": "en-US"}, since, until,
                             limit, "bing_news_rss")
