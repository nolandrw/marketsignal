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
MAX_ATTENTION_PROBES = 8
MAX_ATTENTION_STORIES = 3
ATTENTION_WINDOW_SECONDS = 2 * 86400
MIN_ATTENTION_HEADLINES = 6
MIN_ATTENTION_PUBLISHERS = 4


@dataclass(frozen=True)
class Movement:
    market: Market
    baseline_at: int
    observed_at: int
    previous_price: float
    delta_pp: float
    trigger: str = "price_movement"
    coverage_attention: dict | None = None

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
                "trigger": self.trigger,
                "coverage_attention": self.coverage_attention,
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


def select_quiet_candidates(previous_file: str | Path, latest_file: str | Path,
                            *, excluded_events: set[tuple[str, str]] | None = None,
                            maximum: int = MAX_ATTENTION_PROBES,
                            threshold_pp: float = MIN_MOVEMENT_PP) -> tuple[Movement, ...]:
    """Select liquid, nearly unchanged events for a bounded *news* attention probe.

    The absence of a movement is observed, not interpreted as a probability
    judgment. One representative contract per event avoids redundant searches.
    """
    if not 1 <= maximum <= MAX_ATTENTION_PROBES or not 1 <= threshold_pp <= 25:
        raise ValueError("Invalid quiet-market probe bounds")
    old = json.loads(Path(previous_file).read_text(encoding="utf-8"))
    new = json.loads(Path(latest_file).read_text(encoding="utf-8"))
    if (old.get("schema_version") != 1 or new.get("schema_version") != 1 or
            not isinstance(old.get("markets"), list) or
            not isinstance(new.get("markets"), list) or
            not isinstance(old.get("observed_at"), int) or
            not isinstance(new.get("observed_at"), int) or
            not 0 < new["observed_at"] - old["observed_at"] <= 48 * 3600):
        raise ValueError("Attention probe needs consecutive dated real archives")
    older = {m.market_id: m for m in (Market(**row) for row in old["markets"])}
    if len(older) != len(old["markets"]):
        raise ValueError("Duplicate historical market identity")
    excluded = excluded_events or set()
    candidates: dict[tuple[str, str], Movement] = {}
    seen: set[str] = set()
    for row in new["markets"]:
        market = Market(**row)
        if market.market_id in seen:
            raise ValueError("Duplicate latest market identity")
        seen.add(market.market_id)
        prior = older.get(market.market_id)
        event = (market.venue, market.event_id)
        if (prior is None or event in excluded or
                (prior.venue, prior.yes_token_id, prior.question) !=
                (market.venue, market.yes_token_id, market.question) or
                market.volume_24h < MIN_VOLUME_USD or
                market.liquidity < MIN_LIQUIDITY_USD or
                not all(math.isfinite(p) and 0 <= p <= 1 for p in
                        (market.yes_price, prior.yes_price))):
            continue
        delta = round((market.yes_price - prior.yes_price) * 100, 3)
        if abs(delta) >= threshold_pp:
            continue
        movement = Movement(market, old["observed_at"], new["observed_at"],
                            prior.yes_price, delta)
        if event not in candidates or market.volume_24h > candidates[event].market.volume_24h:
            candidates[event] = movement
    ranked = sorted(candidates.values(), key=lambda m: (m.market.volume_24h,
                                                         m.market.liquidity), reverse=True)
    return tuple(ranked[:maximum])


def _attention_query(market: Market) -> str:
    """A deterministic, bounded subject query; no speculative LLM pre-scout."""
    subject = market.event_title.replace("...", " ").replace("___", " ")
    subject = re.sub(r"[?!.]+", " ", subject)
    subject = re.sub(r"\s+", " ", subject).strip()
    return _short_query(subject)


def probe_quiet_attention(candidates: tuple[Movement, ...], search: CoverageSearch,
                          *, maximum: int = MAX_ATTENTION_STORIES) -> tuple[Movement, ...]:
    """Look for broad *sampled* coverage around unchanged markets.

    The news index returns ranked, capped headline samples, not a full article
    count. Compare adjacent 48h windows and require publisher diversity; never
    characterize these counts as exhaustive media volume.
    """
    if not 0 <= maximum <= MAX_ATTENTION_STORIES:
        raise ValueError("Invalid attention story cap")
    selected = []
    for candidate in candidates[:MAX_ATTENTION_PROBES]:
        if len(selected) >= maximum:
            break
        query = _attention_query(candidate.market)
        if not query:
            continue
        end = candidate.observed_at
        try:
            recent = search.search(query, end - ATTENTION_WINDOW_SECONDS, end, limit=12)
            previous = search.search(query, end - 2 * ATTENTION_WINDOW_SECONDS,
                                     end - ATTENTION_WINDOW_SECONDS, limit=12)
        except (OSError, RuntimeError, ValueError, TypeError, AttributeError):
            continue  # A failed probe is not evidence of quiet coverage.
        recent_valid = {lead.url: lead for lead in recent
                        if _valid_lead(lead, end) and
                        end - ATTENTION_WINDOW_SECONDS <= lead.posted_at <= end}
        previous_valid = {lead.url: lead for lead in previous
                          if _valid_lead(lead, end) and
                          end - 2 * ATTENTION_WINDOW_SECONDS <= lead.posted_at <
                          end - ATTENTION_WINDOW_SECONDS}
        publishers = {lead.author_key.casefold().strip() for lead in recent_valid.values()}
        # Multiple RSS links to an identical syndicated title should not
        # manufacture an impression of independent editorial attention.
        titles = {re.sub(r"[^a-z0-9]+", " ", lead.title.rsplit(" - ", 1)[0].casefold()).strip()
                  for lead in recent_valid.values()}
        if (len(recent_valid) < MIN_ATTENTION_HEADLINES or
                len(publishers) < MIN_ATTENTION_PUBLISHERS or len(titles) < 4 or
                not (len(recent_valid) >= len(previous_valid) + 3 or
                     len(recent_valid) >= 9)):
            continue
        metrics = {"sampled_recent_headlines": len(recent_valid),
                   "sampled_prior_headlines": len(previous_valid),
                   "distinct_recent_publishers": len(publishers),
                   "distinct_recent_titles": len(titles),
                   "window_hours": 48,
                   "sampled_not_total_media_volume": True,
                   "query": query}
        selected.append(Movement(candidate.market, candidate.baseline_at,
                                 candidate.observed_at, candidate.previous_price,
                                 candidate.delta_pp, "coverage_without_price_movement", metrics))
    return tuple(selected)


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
    if movement.trigger == "coverage_without_price_movement":
        trace.append({"stage": "quantitative_attention_gate", "status": "passed",
                      "sampled_recent_headlines": movement.coverage_attention[
                          "sampled_recent_headlines"],
                      "distinct_recent_publishers": movement.coverage_attention[
                          "distinct_recent_publishers"]})
    article = None
    calls = 0
    context = movement.to_dict()
    context["source_caution"] = (
        "Coverage leads are published HEADLINE METADATA, not captured full articles. "
        "Attribute them to named publishers; do not assume or assert an event is verified. "
        "Market movements are observed prices, not proof of a real-world cause.")
    if movement.trigger == "coverage_without_price_movement":
        context["source_caution"] += (
            " This case was triggered by high or increasing publisher diversity in "
            "a CAPPED NEWS-INDEX SAMPLE, NOT an observed market move. The contract "
            "price changed less than one percentage point; do not describe a surge "
            "in betting interest, a statistically proven news spike, or trader "
            "indifference. A worthwhile contrast may be public coverage versus "
            "stable quoted pricing, if the news headlines really bear on the contract.")

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


def review_release_redundancy(results: list[dict], model) -> list[dict]:
    """Batch-stage editorial check after writing, *before* human-release queue.

    The editor sees the real article angles, not just contract names. A
    deterministic event-ID check guarantees that opposite contracts within
    one event cannot both reach the human-ready queue, even if the model errs.
    This never publishes anything and never discards the duplicate manuscript.
    """
    ready = [row for row in results if row["status"] == "shadow_brief_ready_unpublished"]
    if not ready:
        return results
    if len(ready) == 1:
        ready[0]["stage_trace"].append({"stage": "brief_release_editor", "status": "passed_unique"})
        return results

    candidates = [{"market_id": row["market"]["market_id"],
                   "event_id": row["market"]["event_id"],
                   "event_title": row["market"]["event_title"],
                   "question": row["market"]["question"],
                   "trigger": row["market"].get("trigger", "price_movement"),
                   "headline": row["article"]["headline"],
                   "deck": row["article"]["deck"],
                   "paragraphs": [p["text"] for p in row["article"]["paragraphs"]],
                   "editor_score": row.get("editor_score", 0)}
                  for row in ready]
    by_id = {row["market"]["market_id"]: row for row in ready}
    try:
        decision = model.complete("brief_release_editor", {"drafts": candidates,
                                                             "publication_enabled": False})
        reviews = decision["reviews"]
        if (not isinstance(reviews, list) or len(reviews) != len(ready) or
                len({r["market_id"] for r in reviews}) != len(ready) or
                set(r["market_id"] for r in reviews) != set(by_id)):
            raise ValueError("Incomplete batch editorial disposition")
        duplicate_of: dict[str, str] = {}
        reasons: dict[str, str] = {}
        for review in reviews:
            market_id, canonical = review["market_id"], review["duplicate_of"]
            if (not isinstance(canonical, str) or
                    (canonical and (canonical == market_id or canonical not in by_id)) or
                    not isinstance(review["reason"], str) or
                    not review["reason"].strip()):
                raise ValueError("Invalid editorial reference")
            duplicate_of[market_id] = canonical
            reasons[market_id] = review["reason"][:300]
        # No chains or cycles. Each duplicate points to a real surviving brief.
        if any(duplicate_of.get(canonical) for canonical in duplicate_of.values() if canonical):
            raise ValueError("Ambiguous canonical brief")
    except (KeyError, TypeError, ValueError, RuntimeError, AttributeError):
        for row in ready:
            row["status"] = "held_release_editor"
            row["reason"] = "batch_duplicate_review_unavailable"
            row["stage_trace"].append({"stage": "brief_release_editor",
                                       "status": "held_for_manual_comparison"})
        return results

    # Even an editorial model calling two contracts distinct must not approve
    # a duplicate story about the same underlying event.
    events: dict[tuple[str, str], list[dict]] = {}
    for row in ready:
        events.setdefault((row["market"].get("venue", "polymarket"),
                           row["market"]["event_id"]), []).append(row)
    for event_rows in events.values():
        if len(event_rows) < 2:
            continue
        survivor = max(event_rows, key=lambda row: (row.get("editor_score", 0),
                                                    len(row.get("external_leads", [])),
                                                    row["market"].get("volume_24h_usd", 0)))
        winner_id = survivor["market"]["market_id"]
        # Prefer the mandated same-event canonical story, including if the
        # model had grouped that candidate with an unrelated event.
        duplicate_of[winner_id] = ""
        for row in event_rows:
            mid = row["market"]["market_id"]
            if mid != winner_id:
                duplicate_of[mid] = winner_id
                reasons[mid] = "Same underlying event; complementary contract or overlapping story"

    # If the deterministic override changed a canonical, re-point its former
    # dependents to the surviving canonical rather than leaving a chain.
    for mid, canonical in list(duplicate_of.items()):
        if canonical and duplicate_of.get(canonical):
            target = duplicate_of[canonical]
            duplicate_of[mid] = target if target != mid else ""

    for row in ready:
        mid = row["market"]["market_id"]
        canonical = duplicate_of[mid]
        if canonical:
            row["status"] = "held_redundant_brief"
            row["reason"] = "duplicate_of_other_pilot_story"
            row["duplicate_of"] = canonical
            row["duplicate_rationale"] = reasons[mid]
            row["stage_trace"].append({"stage": "brief_release_editor",
                                       "status": "held_duplicate", "duplicate_of": canonical})
        else:
            row["stage_trace"].append({"stage": "brief_release_editor", "status": "passed_unique"})
    return results
