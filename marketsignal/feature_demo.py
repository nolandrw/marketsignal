"""Fictional full-context newspaper-feature test fixture (not real news)."""

from __future__ import annotations

import json
from dataclasses import asdict

from .editorial import Candidate
from .feature_story import (
    ContextClaim, DirectQuote, FeatureNewsroom, ReportingDossier, SourceDocument,
)
from .models import Market, Signal


def fictional_feature_fixture() -> tuple[Candidate, ReportingDossier]:
    """Self-contained documentary evidence for a deliberately fictional city."""
    observed = 1_800_000_000
    market = Market(
        market_id="fictional-crescent-barrier", event_id="fictional-crescent",
        event_title="Crescent Bay coastal barrier", event_slug="crescent-barrier-demo",
        question="Will the Crescent Bay flood barrier win final approval this year?",
        yes_token_id="12345678901234567890", yes_price=.63,
        volume_24h=900_000, liquidity=320_000, end_date="",
    )
    signal = Signal(market.market_id, observed, observed - 86400, 24,
                    .42, .63, 21.0, 84, market.volume_24h, market.liquidity)
    candidate = Candidate(market, signal, risk="low")

    source_material = [
        (
            "plan-2026", "Crescent Bay City Planning Office",
            "https://example.org/fictional/planning-memo", "primary_record",
            "city-planning", 1799800000,
            "For months, city officials had expected a final vote on the proposed flood barrier "
            "before the winter storms. The timetable rested on an engineering review that "
            "officials said was nearly complete. The plan had been sold as a way to protect "
            "the waterfront without closing the working harbor during construction. "
            "A preliminary estimate put the construction period at four years.",
        ),
        (
            "notice-2026", "Crescent Bay Engineering Department",
            "https://example.org/fictional/review-notice", "primary_record",
            "city-engineering", 1799910000,
            "The city postponed the final flood barrier vote after ordering a new review "
            "of the project foundations. The review was ordered after engineers identified "
            "unresolved questions in the subsurface survey. Director Maya Chen said: "
            "We need to understand what is beneath the harbor before we commit to building above it. "
            "The department said it would release a revised timeline after the review is complete.",
        ),
        (
            "impact-2026", "Crescent Bay Civic Data Institute",
            "https://example.org/fictional/harbor-impact", "independent_reporting",
            "civic-institute", 1799840000,
            "The proposed barrier would border neighborhoods where 12,000 people live, "
            "including two low-lying districts with limited evacuation routes. "
            "Local fishing businesses fear that prolonged construction could restrict "
            "harbor access in peak season. A longer delay could also leave residents "
            "without the promised protection through another storm season.",
        ),
        (
            "review-2026", "Independent Coastal Engineering Panel",
            "https://example.org/fictional/engineering-assessment", "independent_reporting",
            "engineering-panel", 1799920000,
            "The newly requested review does not establish that the barrier design is unsafe. "
            "Panel chair Luis Ortega said: A delay is frustrating, but it is not evidence that "
            "the design will fail. The panel advised keeping alternative flood defenses "
            "under consideration until the foundation results are published.",
        ),
        (
            "contractors-2026", "Crescent Bay Contractors Association",
            "https://example.org/fictional/contractors-statement", "public_statement",
            "contractor-group", 1799925000,
            "The local contractors association speculated that higher material costs "
            "could complicate the revised schedule, but presented no documents linking "
            "those costs to the engineering department's decision. It urged the city "
            "to publish a detailed estimate before reopening bids.",
        ),
    ]
    documents = tuple(SourceDocument.capture(
        id_, publisher, url, published, observed, kind, content, origin
    ) for id_, publisher, url, kind, origin, published, content in source_material)
    lookup = {source.source_id: source for source in documents}

    def claim(identifier: str, role: str, statement: str, source_id: str,
              excerpt: str, *, theory: bool = False) -> ContextClaim:
        if excerpt not in lookup[source_id].content:
            raise AssertionError("Synthetic fixture has a broken excerpt")
        return ContextClaim(identifier, role, statement, source_id, excerpt,
                            "attributed_theory" if theory else "reported")

    claims = (
        claim("development", "development",
              "Crescent Bay's plan for a flood barrier has hit a pause: city engineers ordered "
              "another foundation review, and the final approval vote has been postponed.",
              "notice-2026", "The city postponed the final flood barrier vote after ordering a new review"),
        claim("prior-view", "prior_view",
              "Until recently, city officials expected the proposal to reach a decision "
              "before winter storms returned.",
              "plan-2026", "For months, city officials had expected a final vote on the proposed flood barrier"),
        claim("prior-reason", "prior_reason",
              "Their optimism depended in part on an engineering review described as nearly complete.",
              "plan-2026", "The timetable rested on an engineering review that officials said was nearly complete"),
        claim("background", "background",
              "The project was intended to protect the waterfront while allowing a working harbor "
              "to stay open during construction.",
              "plan-2026", "The plan had been sold as a way to protect the waterfront without closing the working harbor"),
        claim("stakes-people", "stakes",
              "Some 12,000 residents live along the proposed route, including people in two "
              "low-lying districts with few evacuation options.",
              "impact-2026", "The proposed barrier would border neighborhoods where 12,000 people live"),
        claim("stakes-business", "stakes",
              "Fishing businesses are worried that construction could limit harbor access "
              "during their most important season.",
              "impact-2026", "Local fishing businesses fear that prolonged construction could restrict harbor access"),
        claim("hypothesis-cost", "hypothesis",
              "A contractors group has floated higher material costs as another possible "
              "complication, although it supplied no evidence that cost concerns caused the delay.",
              "contractors-2026", "speculated that higher material costs could complicate the revised schedule", theory=True),
        claim("counterpoint", "counterpoint",
              "An independent engineering panel cautioned that ordering another review "
              "does not itself mean that the barrier is unsafe.",
              "review-2026", "The newly requested review does not establish that the barrier design is unsafe"),
        claim("next-step", "next_step",
              "The city says a revised timetable will follow once the additional review is finished.",
              "notice-2026", "The department said it would release a revised timeline after the review is complete"),
    )
    quotes = (
        DirectQuote("chen-quote", "Maya Chen",
                    "We need to understand what is beneath the harbor before we commit to building above it.",
                    "notice-2026"),
        DirectQuote("ortega-quote", "Luis Ortega",
                    "A delay is frustrating, but it is not evidence that the design will fail.",
                    "review-2026"),
    )
    dossier = ReportingDossier(
        1, candidate.candidate_id, "Crescent Bay coastal barrier",
        "A Coastal City's Flood Defense Plan Hits an Unexpected Pause",
        documents, claims, quotes,
        ("What exactly changed in the engineering review?",
         "Can costs be separated from the documented foundation concerns?",
         "What temporary protections exist for affected residents?"),
    )
    return candidate, dossier


def demo_feature() -> dict:
    candidate, dossier = fictional_feature_fixture()
    result = FeatureNewsroom().run(candidate, dossier)
    if result.article is None:
        return {"synthetic": True, "publication_enabled": False,
                "research_assignment": asdict(result.assignment),
                "plan": asdict(result.plan) if result.plan else None,
                "article": None, "status": result.status,
                "review": {"structural_provenance_issues": list(result.issue_codes)}}
    return {"synthetic": True, "publication_enabled": False,
            "research_assignment": asdict(result.assignment),
            "plan": asdict(result.plan), "article": result.article.to_dict(),
            "status": result.status, "handoffs": list(result.handoffs),
            "review": {"structural_provenance_issues": list(result.issue_codes),
                       "source_contents_are_fictional": True,
                       "semantic_accuracy_independently_certified": False,
                       "model_written": False,
                       "publication_approved": False}}


def main() -> int:
    result = demo_feature()
    print(json.dumps(result, indent=2))
    return 0 if result.get("article") and not result["review"]["structural_provenance_issues"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
