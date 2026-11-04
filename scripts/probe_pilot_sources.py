"""Read-only, zero-model-cost diagnostics for four-case official source leads.

This intentionally DOES NOT save a source capture or use search snippets as
evidence. It tests the existing official-page retrieval shape, robots rules,
first-party date metadata and bounded extraction with sanitized output.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from urllib.parse import urlsplit

from marketsignal.source_capture import (
    CaptureError, HostPermission, PublicHTMLTransport, SourceCaptureGateway,
    MAX_HTML_BYTES, _ArticleParser,
)


OFFICIAL_LEADS = {
    "hormuz_marad": "https://www.maritime.dot.gov/msci/2026-011-persian-gulf-strait-hormuz-and-gulf-oman-iranian-attacks-commercial-vessels",
    "ipo_sec_index": "https://www.sec.gov/Archives/edgar/data/2130357/000162828026068676/0001628280-26-068676-index.html",
    "fed_fomc": "https://www.federalreserve.gov/newsevents/pressreleases/monetary20261028a.htm",
    "uap_aaro_index": "https://www.aaro.mil/Congressional-Press-Products/",
    "uap_nasa_faq": "https://science.nasa.gov/uap/faqs/",
}


def inspect(lead_name: str, url: str, gateway: SourceCaptureGateway) -> dict:
    host = urlsplit(url).hostname or ""
    try:
        gateway._permission(host, url)
        raw = gateway.transport.get(url, max_bytes=MAX_HTML_BYTES, media="text/html")
        parser = _ArticleParser()
        parser.feed(raw)
        short = [p for p in parser.paragraphs if 45 <= len(p) <= 370]
        date = parser.publisher_date or ""
        try:
            published = datetime.fromisoformat(date.replace("Z", "+00:00"))
            dated = published.tzinfo is not None and 0 < published.timestamp() <= datetime.now(timezone.utc).timestamp()
        except (ValueError, OverflowError):
            dated = False
        ready_shape = dated and len(short) >= 2 and sum(map(len, parser.paragraphs)) >= 220
        return {"lead": lead_name, "host": host,
                "status": "potentially_capturable" if ready_shape else "parser_or_date_hold",
                "publisher_date_present_and_valid": dated,
                "short_excerpt_candidates": len(short),
                "full_source_capture_performed": False}
    except CaptureError as exc:
        return {"lead": lead_name, "host": host, "status": "retrieval_hold",
                "reason": str(exc), "full_source_capture_performed": False}


def main() -> int:
    permissions = tuple(HostPermission(host, "official_record", "official_public_record")
                        for host in sorted({urlsplit(url).hostname for url in OFFICIAL_LEADS.values()}))
    gateway = SourceCaptureGateway(permissions, PublicHTMLTransport(timeout=4))
    findings = [inspect(name, url, gateway) for name, url in OFFICIAL_LEADS.items()]
    print(json.dumps({"phase": "read_only_source_shape_probe", "paid_calls": 0,
                      "publication_enabled": False, "sources": findings}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
