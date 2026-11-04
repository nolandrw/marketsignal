"""Realistic, no-network and adversarial format-to-evidence regression tests."""

import csv
import hashlib
import io
import json
import time
import unittest
from unittest.mock import Mock

from marketsignal.context_discovery import ContextLead
from marketsignal.document_ingestion import ExtractionHold, extract_document, parse_date
from marketsignal.source_capture import (
    CaptureError, FetchedDocument, HostPermission, PublicHTMLTransport, SourceCaptureGateway,
    _official_header_date,
)


NOW = int(time.time())
URL = "https://official.example.org/data"


class MemoryDocumentTransport:
    def __init__(self, raw, mime, *, robots="User-agent: *\nAllow: /"):
        self.raw, self.mime, self.robots = raw, mime, robots
        self.urls = []

    def get(self, url, *, max_bytes, media):
        self.urls.append(url)
        return self.robots

    def fetch_document(self, url, *, max_bytes):
        self.urls.append(url)
        if len(self.raw) > max_bytes:
            raise CaptureError("Publisher content exceeded budget")
        return FetchedDocument(self.raw, self.mime)


def capture(raw, mime, *, first_party=True, kind="official_record", max_bytes=2_000_000):
    transport = MemoryDocumentTransport(raw, mime)
    gateway = SourceCaptureGateway((HostPermission("official.example.org", kind,
                                                  "official_public_record" if kind == "official_record"
                                                  else "permissioned_short_excerpt", max_bytes),),
                                   transport)
    lead = ContextLead("record", "contemporaneous_reporting", URL, "Official record",
                       "official.example.org", NOW - 60,
                       publication_date_basis=("first_party_official_feed" if first_party else "discovery_only"))
    return gateway.capture(lead, observed_at=NOW), transport


class DocumentIngestionTests(unittest.TestCase):
    def test_original_json_fields_have_source_locations_digest_and_date(self):
        data = {"published_at": "2026-11-01T08:00:00Z", "measurements": [
            {"station": "Harbor-7", "reading": "A measured reference value for official harbor traffic activity"},
            {"station": "Harbor-8", "reading": "A second official reading with a different measurement"}]}
        raw = json.dumps(data).encode()
        result, transport = capture(raw, "application/json", first_party=False)
        self.assertEqual(result.document_sha256, hashlib.sha256(raw).hexdigest())
        self.assertEqual(result.publication_date_basis, "embedded_json_metadata")
        self.assertEqual(result.mime_type, "application/json")
        self.assertIn("$", result.excerpt_locations[0])
        self.assertFalse(result.permission_to_republish)
        self.assertFalse(result.verified_truth)
        self.assertEqual(len(transport.urls), 2)
        self.assertEqual(result.source_rows()[0]["content_location"], result.excerpt_locations[0])

    def test_csv_requires_trusted_first_party_date(self):
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["city", "observations", "unit"])
        writer.writerow(["Coastal Harbor", "123456 commercial vessel entries recorded", "trips"])
        writer.writerow(["Northern Harbor", "98765 commercial vessel entries recorded", "trips"])
        raw = output.getvalue().encode()
        result, _ = capture(raw, "text/csv")
        self.assertEqual(result.publication_date_basis, "first_party_official_feed")
        self.assertEqual(result.excerpt_locations[0], "csv:row:2")
        with self.assertRaises(CaptureError):
            capture(raw, "text/csv", first_party=False)

    def test_xml_embedded_date_and_dtd_rejection(self):
        raw = (b"<feed><published>2026-10-29T10:00:00Z</published>"
               b"<item><description>Official monitoring results for the first period exceeded "
               b"the historical comparison threshold.</description></item>"
               b"<item><description>Second independent observation in a similar publication "
               b"window.</description></item></feed>")
        result, _ = capture(raw, "application/xml", first_party=False)
        self.assertEqual(result.publication_date_basis, "embedded_xml_metadata")
        with self.assertRaises(ExtractionHold):
            extract_document(b'<!DOCTYPE foo [<!ENTITY x "fake">]><foo>&x;</foo>', "application/xml")

    def test_plain_text_official_feed_and_untrusted_date_hold(self):
        raw = (b"Official first paragraph reports a documented change in the monitored values.\n"
               b"Second paragraph describes its implications for the measurement methodology.\n")
        result, _ = capture(raw, "text/plain")
        self.assertEqual(result.extraction_method, "plain_text")
        with self.assertRaises(CaptureError):
            capture(raw, "text/plain", first_party=False)

    def test_curated_undated_lead_cannot_launder_a_date(self):
        transport = MemoryDocumentTransport(
            b'<html><meta name="date" content="2026-10-28"><main>' +
            b'<p>A complete, publisher-dated original public document explaining a decision and implications.</p>' * 4 +
            b'</main></html>', "text/html")
        gateway = SourceCaptureGateway((HostPermission("official.example.org", "official_record",
                                                      "official_public_record"),), transport)
        lead = ContextLead("record", "contemporaneous_reporting", URL,
                           "Original government release", "official.example.org", 0,
                           publication_date_basis="date_unknown")
        result = gateway.capture(lead, observed_at=NOW)
        self.assertEqual(result.publication_date_basis, "publisher_page_metadata")
        with self.assertRaises(CaptureError):
            gateway.capture(ContextLead("record", "contemporaneous_reporting", URL,
                                        "Release", "official.example.org", 0), observed_at=NOW)
        transport.raw = transport.raw.replace(b'<meta name="date" content="2026-10-28">', b'')
        with self.assertRaises(CaptureError):
            gateway.capture(lead, observed_at=NOW)

    def test_first_party_government_release_headers_and_preformatted_text(self):
        for host, header in (
            ("www.eia.gov", "Release Date: August 12, 2026"),
            ("www.bls.gov", "Transmission of material in this release is embargoed until "
                            "8:30 a.m. (ET) Wednesday, October 14, 2026"),
            ("www.sec.gov", "As filed with the Securities and Exchange Commission on "
                            "November 2, 2026"),
        ):
            with self.subTest(host=host):
                original = ("<html><body><pre>" + header + "\n" +
                            "This original official release provides complete factual information about the event.\n" * 4 +
                            "</pre></body></html>").encode()
                self.assertIsNotNone(_official_header_date(original.decode(), host))
                transport = MemoryDocumentTransport(original, "text/html")
                gateway = SourceCaptureGateway((HostPermission(host, "official_record",
                                                              "official_public_record"),), transport)
                lead = ContextLead("curated", "contemporaneous_reporting",
                                   f"https://{host}/original", "Official release", host, 0,
                                   publication_date_basis="date_unknown")
                result = gateway.capture(lead, observed_at=NOW)
                self.assertEqual(result.publication_date_basis, "publisher_document_header")
                self.assertEqual(len(result.excerpts), 3)
        self.assertIsNone(_official_header_date(
            "<p>An article mentions that a release date was August 12, 2026.</p>",
            "www.eia.gov"))
        self.assertIsNone(_official_header_date(
            "<p>As filed with the Securities and Exchange Commission on November 2, 2026</p>",
            "news.example.com"))

    def test_general_official_html_fallback_without_article_container(self):
        raw = (b'<html><head><meta property="article:published_time" '
               b'content="2026-10-28T10:00:00Z"></head><body><table>'
               b'<tr><td>Official statement with a full explanatory narrative about the decision and its scope.</td></tr>'
               b'<tr><td>Additional official context regarding implementation actions and next steps for affected entities.</td></tr>'
               b'<tr><td>Third row provides further details on the implementation deadline and obligations.</td></tr>'
               b'</table></body></html>')
        result, _ = capture(raw, "text/html", first_party=False)
        self.assertEqual(result.extraction_method, "html_official_record_blocks")
        self.assertEqual(len(result.excerpts), 3)

    def test_pdf_text_with_page_provenance_and_encryption_hold(self):
        try:
            from reportlab.pdfgen import canvas
        except ImportError:
            self.skipTest("PDF sample generator unavailable")
        buf = io.BytesIO()
        drawing = canvas.Canvas(buf)
        drawing.drawString(40, 720, "Original agency PDF: official measurements were independently documented for a full period.")
        drawing.showPage()
        drawing.drawString(40, 720, "Second page documents the exact methodology and the numerical comparison used in the report.")
        drawing.save()
        result, _ = capture(buf.getvalue(), "application/pdf")
        self.assertEqual(result.mime_type, "application/pdf")
        self.assertEqual(result.excerpt_locations[0], "pdf:page:1")
        self.assertIn("pdf:page:2", result.excerpt_locations)
        with self.assertRaises(ExtractionHold):
            extract_document(b"definitely not a PDF", "application/pdf")

    def test_missing_pdf_date_and_untrusted_search_date_cannot_authorize_capture(self):
        try:
            from reportlab.pdfgen import canvas
        except ImportError:
            self.skipTest("PDF sample generator unavailable")
        buf = io.BytesIO()
        drawing = canvas.Canvas(buf)
        drawing.drawString(40, 720, "A dated original government report cannot be inferred from discovery metadata alone.")
        drawing.save()
        with self.assertRaises(CaptureError):
            capture(buf.getvalue(), "application/pdf", first_party=False)

    def test_format_limits_and_date_only_are_conservative(self):
        self.assertIsNone(parse_date("just a random timestamp"))
        self.assertEqual(parse_date("2026-11-01") % 86400, 86399)
        with self.assertRaises(ExtractionHold):
            extract_document(b"hello", "application/x-msdownload")
        with self.assertRaises(ValueError):
            HostPermission("official.example.org", "independent_reporting",
                           "permissioned_short_excerpt", 16_000_000)

    def test_json_variants_tsv_and_structured_dates(self):
        raw = json.dumps({"filingDate": "2026-11-01", "data":
                          "Original structured-data evidence reports a documented market development."}).encode()
        for media in ("application/geo+json", "application/ld+json", "application/vnd.api+json"):
            with self.subTest(media=media):
                result, _ = capture(raw, media, first_party=False)
                self.assertEqual(result.publication_date_basis, "embedded_json_metadata")
        tabbed = (b"agency\tmeasurement\n"
                  b"Official Ministry\tThe original monitoring report recorded a material change\n")
        result, _ = capture(tabbed, "text/tab-separated-values")
        self.assertEqual(result.extraction_method, "csv_rows")
        bulk = {"published_at": "2026-11-01T08:00:00Z", "rows": [
            "A complete observation for an independently measured data point." for _ in range(260)]}
        result, _ = capture(json.dumps(bulk).encode(), "application/json", first_party=False)
        self.assertTrue(result.partial_extraction)
        with self.assertRaises(ExtractionHold):
            extract_document(b'{"value":NaN}', "application/json")

    def test_transport_enforces_document_type_size_and_pdf_magic(self):
        class Response:
            def __init__(self, raw, mime, declared=None):
                self.raw = raw
                self.headers = {"Content-Type": mime,
                                "Content-Length": str(len(raw) if declared is None else declared)}
            def __enter__(self): return self
            def __exit__(self, *_): return None
            def read(self, count): return self.raw[:count]

        transport = PublicHTMLTransport()
        document = Response(b"%PDF-1.5\nminimal", "application/octet-stream")
        transport._opener = Mock(open=Mock(return_value=document))
        fetched = transport.fetch_document("https://official.example.org/report.pdf", max_bytes=128)
        self.assertEqual(fetched.mime_type, "application/pdf")
        with self.assertRaises(CaptureError):
            transport.fetch_document("https://official.example.org/report.json", max_bytes=128)
        transport._opener.open.return_value = Response(b"not a PDF", "application/octet-stream")
        with self.assertRaises(CaptureError):
            transport.fetch_document("https://official.example.org/report.pdf", max_bytes=128)
        transport._opener.open.return_value = Response(b"x" * 129, "text/plain")
        with self.assertRaises(CaptureError):
            transport.fetch_document("https://official.example.org/record.txt", max_bytes=128)
        transport._opener.open.return_value = Response(b"hello", "text/plain", declared=500)
        with self.assertRaises(CaptureError):
            transport.fetch_document("https://official.example.org/record.txt", max_bytes=128)


if __name__ == "__main__":
    unittest.main()
