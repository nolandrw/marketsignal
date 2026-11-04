"""Read-only preparation of four-case original-source research *seeds*.

Never calls an LLM, promotes a web snippet, publishes, or claims coverage
review. Missing diversity stays visible for later investigation. Private
output is gitignored and must pass pilot preflight before any paid run.
"""

from __future__ import annotations

import json
import time
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from marketsignal.context_discovery import ContextLead
from marketsignal.gamma import _json_list
from marketsignal.models import Market
from marketsignal.quantitative import create_pitch
from marketsignal.source_capture import CaptureError, HostPermission, SourceCaptureGateway
from marketsignal.topic_lead import TopicLeadContext, TopicSourceLead
from scripts.run_research_pilot import EXPECTED_IDS


PRIVATE = Path("data/private")
ARCHIVE = Path("data/archive/2026-11-03.json")
SOURCES = {
    "hormuz": (
        "https://www.maritime.dot.gov/msci/2026-011-persian-gulf-strait-hormuz-and-gulf-oman-iranian-attacks-commercial-vessels",
        "https://www.eia.gov/outlooks/steo/report/energysecurity/article.php",
    ),
    "ipo": (
        "https://www.sec.gov/Archives/edgar/data/2130357/000162828026068676/0001628280-26-068676-index.html",
        "https://www.sec.gov/Archives/edgar/data/2130357/000162828026068676/anthropicpbc-sx1ax1.htm",
        "https://www.sec.gov/Archives/edgar/data/1181412/000162828026036936/spaceexplorationtechnologi.htm",
    ),
    "fed": (
        "https://www.federalreserve.gov/newsevents/pressreleases/monetary20261028a.htm",
        "https://www.bls.gov/news.release/archives/cpi_10142026.htm",
        "https://www.federalreserve.gov/Releases/H15/Update/",
    ),
    "uap": (
        "https://science.nasa.gov/uap/faqs/",
        "https://science.nasa.gov/uap/",
        "https://www.aaro.mil/Congressional-Press-Products/",
    ),
}
PURPOSE = {
    "hormuz": "Test whether an independent investigation can distinguish vessel counts from oil flows at Hormuz.",
    "ipo": "Test whether original IPO filings establish comparable valuations rather than market speculation.",
    "fed": "Test original rate series and the available evidence for borrower and depositor pass-through.",
    "uap": "Test whether authenticated government records support or refute a claimed official alien finding.",
}


def _live_market(market_id: str, previous: Market) -> tuple[Market, int, str]:
    """Fetch a real current Gamma quote and preserve its exact observation clock."""
    endpoint = f"https://gamma-api.polymarket.com/markets/{market_id}"
    request = Request(endpoint, headers={"Accept": "application/json",
                                         "User-Agent": "MarketSignal/0.1 (unpublished research)"})
    with urlopen(request, timeout=12) as response:
        if response.headers.get("Content-Type", "").split(";", 1)[0] != "application/json":
            raise ValueError("Market endpoint did not return JSON")
        raw = response.read(250_001)
        if len(raw) > 250_000:
            raise ValueError("Oversized live market response")
    observed_at = int(time.time())
    data = json.loads(raw)
    outcomes, prices = _json_list(data.get("outcomes")), _json_list(data.get("outcomePrices"))
    tokens = _json_list(data.get("clobTokenIds"))
    if (str(data.get("id")) != market_id or data.get("question") != previous.question or
            not data.get("active") or data.get("closed") or
            len(outcomes) != 2 or {str(o).lower() for o in outcomes} != {"yes", "no"} or
            len(prices) != 2 or len(tokens) != 2):
        raise ValueError("Original market identity or active status changed")
    yes = next(i for i, label in enumerate(outcomes) if label.lower() == "yes")
    if str(tokens[yes]) != previous.yes_token_id:
        raise ValueError("Live outcome token differs from frozen subject")
    price = float(prices[yes])
    volume = float(data["volume24hr"])
    liquidity = float(data.get("liquidityNum") or data["liquidity"])
    if not (0 < price < 1 and 0 <= volume < 1e14 and 0 <= liquidity < 1e14):
        raise ValueError("Invalid live quote")
    return replace(previous, yes_price=price, volume_24h=volume,
                   liquidity=liquidity), observed_at, str(data.get("description") or "")[:2000]


def prepare() -> dict:
    if not ARCHIVE.is_file():
        raise ValueError("Frozen November 3 case identity archive is missing")
    old = json.loads(ARCHIVE.read_text(encoding="utf-8"))
    frozen = {row["market_id"]: Market(**row) for row in old["markets"]
              if row.get("market_id") in EXPECTED_IDS.values()}
    if set(frozen) != set(EXPECTED_IDS.values()):
        raise ValueError("Missing frozen subject identity")
    # Official/public-record only. Other sources require their own documented
    # rights grant; this script never invents independent-reporting permission.
    hosts = {urlsplit(url).hostname for urls in SOURCES.values() for url in urls}
    policy_publishers = [{"host": host, "kind": "official_record",
                          "copyright_basis": "official_public_record",
                          "max_capture_bytes": 16_000_000 if host == "www.sec.gov" else 2_000_000}
                         for host in sorted(hosts)]
    gateway = SourceCaptureGateway(tuple(HostPermission(**row) for row in policy_publishers))
    PRIVATE.mkdir(parents=True, exist_ok=True)
    summary = {"phase": "partial_original_evidence_preparation", "model_calls": 0,
               "publication_enabled": False, "cases": {}}
    manifest = {"schema_version": 1, "cases": []}
    for name, market_id in EXPECTED_IDS.items():
        market, as_of, resolution_terms = _live_market(market_id, frozen[market_id])
        all_rows, source_status = [], []
        for url in SOURCES[name]:
            lead = ContextLead("curated", "contemporaneous_reporting", url,
                               "Original primary record", urlsplit(url).hostname or "", 0,
                               publication_date_basis="date_unknown")
            try:
                captured = gateway.capture(lead, observed_at=as_of)
                source_status.append({"url": url, "state": "captured",
                                      "format": captured.mime_type,
                                      "dated_by": captured.publication_date_basis,
                                      "excerpt_count": len(captured.excerpts),
                                      "digest": captured.document_sha256})
                all_rows.extend(captured.source_rows())
            except CaptureError as exc:
                source_status.append({"url": url, "state": "held", "reason": str(exc)})
        all_rows = all_rows[:15]
        basename = f"data/private/{name}"
        sources = tuple(TopicSourceLead(source_id=row["source_id"],
                         publisher=row["publisher"], url=row["url"],
                         origin_key=row["independent_origin"],
                         published_at=int(datetime.fromisoformat(
                             row["published_at"].replace("Z", "+00:00")).timestamp()),
                         source_type="primary_record", captured_excerpt=row["captured_excerpt"])
                        for row in all_rows)
        context = TopicLeadContext(
            story_id=f"pilot-{name}-{as_of}", as_of=as_of,
            market_question=market.question,
            resolution_terms=resolution_terms,
            quantitative_pitch=create_pitch(market, as_of, ()),
            sources=sources, coverage_checked=False,
        )
        inputs = {
            "context_file": basename + "-context.json",
            "captures_file": basename + "-captures.json",
            "policy_file": basename + "-policy.json",
            "test_fixture_file": basename + "-fixture.json",
        }
        payloads = {
            "context_file": {"schema_version": 1, **context.to_dict()},
            "captures_file": {"source_rows": all_rows, "publication_enabled": False,
                              "claims_semantically_verified": False},
            "policy_file": {"publishers": policy_publishers,
                            "enable_bluesky": False, "enable_crossref": False},
            "test_fixture_file": {"case_id": context.story_id, "market_id": market_id,
                                  "as_of": as_of, "purpose": PURPOSE[name],
                                  "mode": "test_only_manual_subject", "publication_enabled": False},
        }
        for field, path in inputs.items():
            Path(path).write_text(json.dumps(payloads[field], indent=2), encoding="utf-8")
        manifest["cases"].append({"name": name, **inputs, "angle_id": "auto:first"})
        origins = {row["independent_origin"] for row in all_rows}
        summary["cases"][name] = {
            "market_id": market_id, "as_of": as_of,
            "yes_quote": market.yes_price, "quote_source": "direct_gamma_api",
            "historical_baseline_available": False,
            "source_origins": len(origins), "excerpt_rows": len(all_rows),
            "rights_reviewed_for_independent_reporting": False,
            "coverage_checked": False,
            "seed_evidence_ready": bool(all_rows),
            "publication_ready": False,
            "pilot_ready": bool(all_rows),
            "original_source_attempts": source_status,
        }
    (PRIVATE / "pilot-manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (PRIVATE / "pilot-readiness.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


if __name__ == "__main__":
    try:
        result = prepare()
        print(json.dumps(result, indent=2))
    except (OSError, ValueError, KeyError, TypeError, TimeoutError) as exc:
        print(json.dumps({"phase": "held", "reason": type(exc).__name__,
                          "publication_enabled": False, "model_calls": 0}))
        raise SystemExit(1)
