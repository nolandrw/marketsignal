"""Low-friction, unpublished market-movement briefs built from dated coverage leads.

This is a *curation* lane, not an investigative dossier or a fact-certified news
article. A headline in a discovery index proves only that a publisher used that
headline; it does not independently verify the underlying event. The resulting
copy must attribute that distinction, cite every claim, and remain private.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from urllib.parse import urlsplit

from .models import Market


MAX_CASES = 12
MIN_MOVEMENT_PP = 1.0
MIN_VOLUME_USD = 50_000
MIN_LIQUIDITY_USD = 25_000
MAX_MODEL_CALLS_PER_CASE = 6
MIN_EDITOR_SCORE = 50
SOURCE_MARKET = "market_snapshot"


@dataclass(frozen=True)
class Movement:
    market: Market
    baseline_at: int
    observed_at: int
    previous_price: float
    delta_pp: float

    def to_dict(self) -> dict:
        return {"market_id": self.market.market_id,
                "event_id": self.market.event_id,
                "event_title": self.market.event_title,
                "question": self.market.question,
                "category": self.market.category,
                "market_url": self.market.source_url,
                "baseline_at": self.baseline_at,
                "observed_at": self.observed_at,
                "prior_yes_price": self.previous_price,
                "current_yes_price": self.market.yes_price,
                "change_pp": self.delta_pp,
                "volume_24h_usd": self.market.volume_24h,
                "liquidity_usd": self.market.liquidity,
                "market_prices_are_not_event_probabilities": True,
                "market_movement_does_not_establish_causality": True}


def select_movers(previous_file: str | Path, latest_file: str | Path,
                  *, maximum: int = MAX_CASES,
                  threshold_pp: float = MIN_MOVEMENT_PP) -> tuple[Movement, ...]:
    """Use observed, same-contract price changes; never fabricate a baseline."""
    if not 1 <= maximum <= MAX_CASES or not 1 <= threshold_pp <= 25:
        raise ValueError("Invalid bounded brief selection")
    old = json.loads(Path(previous_file).read_text(encoding="utf-8"))
    new = json.loads(Path(latest_file).read_text(encoding="utf-8"))
    if (old.get("schema_version") != 1 or new.get("schema_version") != 1 or
            not isinstance(old.get("markets"), list) or not isinstance(new.get("markets"), list) or
            not isinstance(old.get("observed_at"), int) or
            not isinstance(new.get("observed_at"), int) or
            not 0 < new["observed_at"] - old["observed_at"] <= 48 * 3600):
        raise ValueError("Brief archive comparison must be consecutive and dated")
    old_markets = {m.market_id: m for m in (Market(**row) for row in old["markets"])}
    if len(old_markets) != len(old["markets"]):
        raise ValueError("Duplicate historical market identity")
    candidates = []
    seen = set()
    for row in new["markets"]:
        market = Market(**row)
        prior = old_markets.get(market.market_id)
        if market.market_id in seen:
            raise ValueError("Duplicate latest market identity")
        seen.add(market.market_id)
        if prior is None or (prior.venue, prior.yes_token_id, prior.question) != (
                market.venue, market.yes_token_id, market.question):
            continue
        if market.volume_24h < MIN_VOLUME_USD or market.liquidity < MIN_LIQUIDITY_USD:
            continue
        if not (math.isfinite(market.yes_price) and math.isfinite(prior.yes_price)
                and 0 <= market.yes_price <= 1 and 0 <= prior.yes_price <= 1):
            continue
        delta = round((market.yes_price - prior.yes_price) * 100, 3)
        if abs(delta) < threshold_pp:
            continue
        candidates.append(Movement(market, old["observed_at"], new["observed_at"],
                                   prior.yes_price, delta))
    candidates.sort(key=lambda x: (abs(x.delta_pp), x.market.volume_24h), reverse=True)
    return tuple(candidates[:maximum])


class CoverageSearch(Protocol):
    def search(self, query: str, since: int, until: int, limit: int = 8): ...


def _short_query(value: str) -> str:
    """Normalize a model-generated search lead without treating it as evidence."""
    if not isinstance(value, str):
        return ""
    query = " ".join(value.split())
    if len(query) > 110:
        query = query[:110].rsplit(" ", 1)[0]
    return query if 8 <= len(query) <= 110 else ""


def _valid_lead(lead, observed_at: int) -> bool:
    try:
        url = urlsplit(lead.url)
        return (url.scheme == "https" and bool(url.hostname) and
                not (url.username or url.password) and
                0 < lead.posted_at <= observed_at and
                observed_at - lead.posted_at <= 30 * 86400 and
                10 <= len(lead.title.strip()) <= 240)
    except (ValueError, AttributeError, TypeError):
        return False


def _manuscript_issues(raw: dict, headline: str, available: set[str]) -> list[str]:
    issues = []
    if (not isinstance(raw, dict) or raw.get("headline") != headline or
            not isinstance(raw.get("deck"), str) or len(raw["deck"].strip()) < 20 or
            not isinstance(raw.get("paragraphs"), list) or
            not 3 <= len(raw["paragraphs"]) <= 6):
        return ["malformed_or_uncommissioned_manuscript"]
    total_words = 0
    used = set()
    for index, p in enumerate(raw["paragraphs"]):
        if (not isinstance(p, dict) or not isinstance(p.get("text"), str) or
                not 35 <= len(p["text"].strip()) <= 1200 or
                p.get("claim_type") not in {"market_observation", "attributed_coverage", "interpretation"} or
                not isinstance(p.get("source_ids"), list) or not p["source_ids"] or
                not set(p["source_ids"]) <= available or
                len(set(p["source_ids"])) != len(p["source_ids"])):
            issues.append(f"invalid_paragraph_{index}")
            continue
        if p["claim_type"] == "market_observation" and SOURCE_MARKET not in p["source_ids"]:
            issues.append(f"market_stat_without_market_source_{index}")
        if p["claim_type"] == "attributed_coverage" and not (set(p["source_ids"]) - {SOURCE_MARKET}):
            issues.append(f"attribution_without_coverage_{index}")
        total_words += len(p["text"].split())
        used.update(p["source_ids"])
    if not 120 <= total_words <= 450:
        issues.append("brief_length_out_of_bounds")
    if SOURCE_MARKET not in used or not (used - {SOURCE_MARKET}):
        issues.append("missing_market_or_external_coverage_link")
    if any(word in headline.lower() for word in ("polymarket", "kalshi", "betting odds")):
        issues.append("platform_centered_headline")
    return issues


def run_brief(movement: Movement, model, search: CoverageSearch) -> dict:
    """Bounded scout -> discovery -> editor -> writer -> verifier, always private."""
    trace: list[dict] = []
    article = None
    calls = 0
    context = movement.to_dict()
    context["source_caution"] = (
        "Coverage leads are published HEADLINE METADATA, not captured full articles. "
        "Attribute them to named publishers; do not assume or assert an event is verified. "
        "Market movements are observed prices, not proof of a real-world cause.")

    def result(status: str, reason: str, **more) -> dict:
        return {"status": status, "reason": reason, "market": movement.to_dict(),
                "stage_trace": trace, "model_calls": calls,
                "article": article, "publication_enabled": False,
                "human_factcheck_attested": False,
                "source_depth": "market_data_and_unverified_headline_metadata",
                **more}

    def call(stage: str, packet: dict) -> dict:
        nonlocal calls
        if calls >= MAX_MODEL_CALLS_PER_CASE:
            raise ValueError("Per-brief model call ceiling")
        calls += 1
        trace.append({"stage": stage, "status": "attempted"})
        response = model.complete(stage, packet)
        if not isinstance(response, dict):
            raise ValueError("Non-object model stage response")
        trace[-1]["status"] = "completed"
        return response

    try:
        scout = call("brief_scout", context)
        queries = []
        for candidate in scout["search_queries"][:2]:
            query = _short_query(candidate)
            if query and query not in queries:
                queries.append(query)
        if not queries:
            return result("held_search", "no_usable_research_query")
        leads = {}
        errors = []
        for query in queries:
            try:
                candidates = search.search(query, max(1, movement.observed_at - 30 * 86400),
                                           movement.observed_at, limit=8)
                for row in candidates[:8]:
                    if _valid_lead(row, movement.observed_at):
                        leads[row.url] = row
            except (OSError, RuntimeError, ValueError, TypeError, AttributeError) as exc:
                errors.append(type(exc).__name__)
        # Cap article context to eight distinct dated links, all discovery-only.
        source_rows = [{"source_id": f"coverage_{n+1}", "publisher": row.author_key,
                        "headline": row.title, "url": row.url, "published_at": row.posted_at,
                        "evidence_level": "discovery_title_only"}
                       for n, row in enumerate(list(leads.values())[:8])]
        trace.append({"stage": "coverage_discovery", "status": "completed",
                      "queries": len(queries), "leads": len(source_rows),
                      "source_errors": errors})
        if not source_rows:
            return result("held_no_coverage", "no_dated_external_coverage_leads")
        editor = call("brief_editor", {**context, "coverage_leads": source_rows,
                                      "reader_question": scout["reader_question"],
                                      "possible_connection": scout["possible_connection"]})
        source_ids = {s["source_id"] for s in source_rows}
        if (editor.get("decision") != "go" or
                type(editor.get("reader_value_score")) is not int or
                editor["reader_value_score"] < MIN_EDITOR_SCORE or
                not isinstance(editor.get("headline"), str) or
                not 20 <= len(editor["headline"].strip()) <= 130 or
                not isinstance(editor.get("selected_source_ids"), list) or
                set(editor.get("selected_source_ids", [])) - source_ids or
                not editor.get("selected_source_ids") or
                not editor.get("reader_value", "").strip()):
            return result("held_editor", "brief_not_worth_sourcing_or_insufficient_coverage",
                          editor_score=editor.get("reader_value_score"))
        selected = [s for s in source_rows if s["source_id"] in editor["selected_source_ids"]]
        feedback = []
        for _ in range(2):
            written = call("brief_writer", {**context, "selected_coverage": selected,
                                           "editorial_assignment": editor,
                                           "review_feedback": feedback})
            issue_list = _manuscript_issues(written, editor["headline"],
                                            {SOURCE_MARKET} | {s["source_id"] for s in selected})
            article = {"headline": written.get("headline", ""),
                       "deck": written.get("deck", ""),
                       "paragraphs": written.get("paragraphs", []),
                       "status": "UNPUBLISHED_CURATION_BRIEF",
                       "publication_enabled": False}
            trace.append({"stage": "brief_contract", "status": "passed" if not issue_list else "rejected",
                          "issues": issue_list})
            if issue_list:
                feedback = issue_list
                continue
            verification = call("brief_factcheck", {**context, "selected_coverage": selected,
                                                   "article": article})
            checks = verification["reviews"]
            if (len(checks) == len(article["paragraphs"]) and
                    sorted(c["paragraph_index"] for c in checks) == list(range(len(checks))) and
                    all(c["verdict"] == "supported" and not c["issues"] for c in checks) and
                    not verification["article_issues"]):
                trace.append({"stage": "brief_factcheck_gate", "status": "passed_provisionally"})
                trace.append({"stage": "release", "status": "held_for_human_review"})
                return result("shadow_brief_ready_unpublished", "owner_and_human_review_required",
                              external_leads=selected, editor_score=editor["reader_value_score"])
            trace.append({"stage": "brief_factcheck_gate", "status": "rejected"})
            feedback = ["Fact checker found unsupported or overstated headline-derived claims"]
        return result("held_brief_review", "brief_revisions_or_evidence_insufficient")
    except (KeyError, TypeError, ValueError, AttributeError, RuntimeError, OverflowError) as exc:
        # Stable diagnostics only; never expose source URLs or model bodies in public logs.
        trace.append({"stage": "fail_closed", "status": "held",
                      "error_class": type(exc).__name__,
                      "model_error_code": getattr(exc, "diagnostic_code", None)})
        return result("held_stage_contract", "brief_provider_or_contract_failure")
