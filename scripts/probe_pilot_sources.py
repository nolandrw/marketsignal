"""Read-only, zero-model-cost diagnostics for four-case official source leads.

This intentionally DOES NOT save source content or use search snippets as
evidence. It probes the same multi-format transport and format/date extraction
as the capture gateway, and reports sanitized holds only.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from urllib.parse import urlsplit

from marketsignal.document_ingestion import ExtractionHold, extract_document, parse_date
from marketsignal.source_capture import (
    CaptureError, HostPermission, PublicHTMLTransport, SourceCaptureGateway,
    _ArticleParser,
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
        document = gateway.transport.fetch_document(
            url, max_bytes=gateway.permissions[host].max_capture_bytes)
        if document.mime_type in {"text/html", "application/xhtml+xml"}:
            parser = _ArticleParser(require_article=False)
            parser.feed(document.content.decode("utf-8"))
            text_blocks = [p for p in parser.paragraphs if len(p) >= 45]
            published_at = parse_date(parser.publisher_date)
            extractable = len(text_blocks) >= 2 and sum(map(len, parser.paragraphs)) >= 220
            excerpts = len(text_blocks)
        else:
            extracted = extract_document(document.content, document.mime_type)
            published_at = extracted.published_at
            extractable = bool(extracted.excerpts)
            excerpts = len(extracted.excerpts)
        dated = published_at is not None and published_at <= int(datetime.now(timezone.utc).timestamp())
        ready_shape = dated and extractable
        return {"lead": lead_name, "host": host,
                "status": ("potentially_capturable" if ready_shape else
                           "date_metadata_hold" if not dated else "parser_hold"),
                "mime_type": document.mime_type,
                "publisher_date_present_and_valid": dated,
                "short_excerpt_candidates": excerpts,
                "full_source_capture_performed": False}
    except (CaptureError, ExtractionHold, UnicodeError, ValueError) as exc:
        return {"lead": lead_name, "host": host,
                "status": ("retrieval_hold" if isinstance(exc, CaptureError)
                           else "parser_hold"),
                "reason": (str(exc) if isinstance(exc, CaptureError) else type(exc).__name__),
                "full_source_capture_performed": False}


def main() -> int:
    permissions = tuple(HostPermission(host, "official_record", "official_public_record",
                                       max_capture_bytes=16_000_000 if host == "www.sec.gov"
                                       else 2_000_000)
                        for host in sorted({urlsplit(url).hostname for url in OFFICIAL_LEADS.values()}))
    gateway = SourceCaptureGateway(permissions, PublicHTMLTransport(timeout=4))
    findings = [inspect(name, url, gateway) for name, url in OFFICIAL_LEADS.items()]
    print(json.dumps({"phase": "read_only_multiformat_source_shape_probe", "paid_calls": 0,
                      "publication_enabled": False, "sources": findings}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
