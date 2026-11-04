"""Bounded, format-aware extraction of citable *source material*, not truth.

Formats are selected by the server Content-Type, not by a filename extension.
Original bytes are fingerprinted elsewhere; locations point back into the
source document. Unknown types and untrusted/undated documents remain holds.
"""

from __future__ import annotations

import csv
import io
import json
import re
from dataclasses import dataclass
from datetime import datetime, time, timezone
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree


SUPPORTED_MIME = frozenset({
    "text/html", "application/xhtml+xml", "application/pdf", "application/json",
    "text/json", "application/geo+json", "application/ld+json",
    "application/vnd.api+json", "text/csv", "application/csv",
    "text/tab-separated-values", "text/plain",
    "application/xml", "text/xml", "application/rss+xml", "application/atom+xml",
})
MAX_DOCUMENT_BYTES = 16_000_000
MAX_TEXT_CHARS = 90_000


class ExtractionHold(ValueError):
    """Parser could not safely extract eligible, attributable evidence."""


@dataclass(frozen=True)
class ExtractedDocument:
    mime_type: str
    excerpts: tuple[str, ...]
    locations: tuple[str, ...]
    published_at: int | None
    date_basis: str | None
    extraction_method: str
    partial_extraction: bool = False


def parse_date(value: object) -> int | None:
    """Use end-of-day for a date-only publication label (avoid lookahead)."""
    if not isinstance(value, str) or not 6 <= len(value.strip()) <= 100:
        return None
    value = value.strip()
    try:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            d = datetime.strptime(value, "%Y-%m-%d").date()
            dt = datetime.combine(d, time(23, 59, 59), timezone.utc)
        elif "," in value:
            dt = parsedate_to_datetime(value)
        else:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            return None
        return int(dt.timestamp()) if dt.timestamp() > 0 else None
    except (ValueError, OverflowError, TypeError):
        return None


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("\x00", " ")).strip()


def _snippets(rows: list[tuple[str, str]], *, minimum: int = 40) -> tuple[tuple[str, ...], tuple[str, ...]]:
    excerpts: list[str] = []
    locations: list[str] = []
    for location, original in rows:
        line = _clean(original)
        if len(line) < minimum:
            continue
        # A long block is quoted as a contiguous bounded prefix. No fabricated
        # ellipsis or extrapolation is inserted into evidence text.
        excerpts.append(line[:370])
        locations.append(location)
        if len(excerpts) >= 3:
            break
    if not excerpts:
        raise ExtractionHold("No bounded source excerpts")
    return tuple(excerpts), tuple(locations)


def _structured_date(value) -> int | None:
    if not isinstance(value, dict):
        return None
    for key in ("datePublished", "published_at", "published", "releaseDate", "release_date",
                "filingDate", "filing_date"):
        date = parse_date(value.get(key))
        if date is not None:
            return date
    return None


def _flatten_json(value, *, path: str = "$", depth: int = 0, limit: int = 250,
                  truncated: list[bool] | None = None):
    """Preserve JSON-pointer-like locations and reject vast/deep structures."""
    if depth > 12:
        raise ExtractionHold("JSON exceeds safe nesting")
    if isinstance(value, dict):
        if truncated is not None and len(value) > limit:
            truncated[0] = True
        for key, child in list(value.items())[:limit]:
            if isinstance(key, str) and len(key) <= 100:
                yield from _flatten_json(child, path=path + "/" + key.replace("~", "~0").replace("/", "~1"),
                                         depth=depth + 1, limit=limit, truncated=truncated)
    elif isinstance(value, list):
        if truncated is not None and len(value) > limit:
            truncated[0] = True
        for index, child in enumerate(value[:limit]):
            yield from _flatten_json(child, path=f"{path}/{index}", depth=depth + 1,
                                     limit=limit, truncated=truncated)
    elif isinstance(value, (str, int, float, bool)) and value is not None:
        yield path, str(value)[:1200]


def extract_document(raw: bytes, mime_type: str, *,
                     trusted_feed_date: int | None = None) -> ExtractedDocument:
    """Bounded extraction; feed dates must be supplied only from first-party RSS/Atom.

    A discovery/search timestamp alone must never be passed as a trusted date.
    The result is useful evidence only after host/robots/rights checks outside
    this parser and after verification of the underlying source meaning.
    """
    if (not isinstance(raw, bytes) or not 1 <= len(raw) <= MAX_DOCUMENT_BYTES or
            mime_type not in SUPPORTED_MIME):
        raise ExtractionHold("Unsupported or oversized document format")
    if trusted_feed_date is not None and (type(trusted_feed_date) is not int or trusted_feed_date <= 0):
        raise ExtractionHold("Invalid first-party feed publication date")
    published = None
    basis = None
    partial = False
    if mime_type == "application/pdf":
        if not raw.startswith(b"%PDF-"):
            raise ExtractionHold("Invalid PDF signature")
        try:
            from pypdf import PdfReader
        except ImportError:
            raise ExtractionHold("PDF parser unavailable; install research extra") from None
        try:
            reader = PdfReader(io.BytesIO(raw), strict=True)
            if reader.is_encrypted or len(reader.pages) > 1200:
                raise ExtractionHold("Encrypted or unbounded PDF")
            rows = []
            for index in range(min(len(reader.pages), 50)):
                text = (reader.pages[index].extract_text() or "")[:MAX_TEXT_CHARS]
                rows.extend((f"pdf:page:{index + 1}", p) for p in text.splitlines())
                if sum(len(t) for _, t in rows) > MAX_TEXT_CHARS:
                    partial = True
                    break
            partial = partial or len(reader.pages) > 50
        except ExtractionHold:
            raise
        except Exception:
            raise ExtractionHold("PDF extraction failed") from None
        method = "pdf_text_extraction"
    elif mime_type in {"application/json", "text/json", "application/geo+json",
                       "application/ld+json", "application/vnd.api+json"}:
        try:
            data = json.loads(raw.decode("utf-8"),
                              parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
        except (ValueError, UnicodeError):
            raise ExtractionHold("Invalid JSON document") from None
        published = _structured_date(data)
        basis = "embedded_json_metadata" if published is not None else None
        truncated = [False]
        rows = [(place, f"{place}: {value}") for place, value in
                _flatten_json(data, truncated=truncated)]
        partial = truncated[0]
        method = "json_fields"
    elif mime_type in {"text/csv", "application/csv", "text/tab-separated-values"}:
        try:
            reader = csv.reader(io.StringIO(raw.decode("utf-8-sig")), strict=True,
                                delimiter="\t" if mime_type == "text/tab-separated-values" else ",")
            headers = next(reader)
            if not 1 <= len(headers) <= 100:
                raise ExtractionHold("Invalid CSV header width")
            rows = []
            for row_number, values in enumerate(reader, start=2):
                if row_number > 501:
                    partial = True
                    break
                if len(values) != len(headers):
                    raise ExtractionHold("Inconsistent CSV row width")
                line = "; ".join(f"{h[:50]}={v[:180]}" for h, v in zip(headers, values))
                rows.append((f"csv:row:{row_number}", line))
        except (csv.Error, UnicodeError, StopIteration):
            raise ExtractionHold("Invalid CSV data") from None
        method = "csv_rows"
    elif mime_type in {"application/xml", "text/xml", "application/rss+xml", "application/atom+xml"}:
        if b"<!DOCTYPE" in raw.upper() or b"<!ENTITY" in raw.upper():
            raise ExtractionHold("XML entities or DTD are not permitted")
        try:
            root = ElementTree.fromstring(raw)
        except ElementTree.ParseError:
            raise ExtractionHold("Invalid XML document") from None
        rows = []
        for index, elem in enumerate(root.iter()):
            if index > 2000:
                partial = True
                break
            if elem.text and elem.text.strip():
                rows.append((f"xml:{index}:{elem.tag[-50:]}", f"{elem.tag[-50:]}: {elem.text}"))
            if elem.tag.rsplit("}", 1)[-1].lower() in ("published", "pubdate", "updated"):
                published = published or parse_date(elem.text)
        basis = "embedded_xml_metadata" if published is not None else None
        method = "xml_elements"
    elif mime_type == "text/plain":
        try:
            text = raw.decode("utf-8")
        except UnicodeError:
            raise ExtractionHold("Invalid plain-text encoding") from None
        rows = [(f"text:line:{i}", line) for i, line in enumerate(text.splitlines()[:1000], 1)]
        method = "plain_text"
    else:
        # HTML is handled by the safer page-specific parser in source_capture,
        # which also looks for first-party publication date metadata.
        raise ExtractionHold("HTML requires the publisher page parser")
    if published is None and trusted_feed_date is not None:
        published, basis = trusted_feed_date, "first_party_official_feed"
    excerpts, locations = _snippets(rows, minimum=30)
    return ExtractedDocument(mime_type, excerpts, locations, published, basis,
                             method, partial)
