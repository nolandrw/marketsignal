"""Offline, source-linked real-topic newsroom field trials.

The input is a *curated* case file, not scraped source material and not a
trained model output. All content is untrusted until external human semantic
review. This utility audits claim/source relationships and produces a clearly
marked shadow article, NEVER a publication payload.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from .story_thesis import (
    audit_story_selection, parse_editorial_selection, parse_story_pitches,
)


ROLES = {
    "new_development", "prior_expectations", "explanation", "stakes",
    "counterpoint", "future_watch", "market_context",
}
KINDS = {"official_record", "original_research", "independent_reporting", "statement"}
SHAKEOUT_RULES = (
    "no_real_market_change_assumed", "valid_source_metadata", "no_future_sources",
    "distinct_source_origins", "source_linked_claims", "uncertainty_and_counterpoint",
    "paragraph_evidence_linkage", "quote_text_provenance", "market_secondary_headline",
    "story_thesis_selection", "human_release_gate_disabled",
)


def _utc(value: str) -> int:
    if not isinstance(value, str):
        raise ValueError("Expected ISO UTC date")
    date = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if date.tzinfo is None or date.utcoffset().total_seconds() != 0:
        raise ValueError("Date must include UTC zone")
    return int(date.timestamp())


def _web_url(value: str) -> bool:
    if not isinstance(value, str) or len(value) > 1200 or any(c.isspace() for c in value):
        return False
    try:
        p = urlsplit(value)
        return (p.scheme == "https" and bool(p.hostname) and
                p.username is None and p.password is None and
                p.port is None and not p.fragment)
    except ValueError:
        return False


def load_case(path: str | Path) -> dict:
    target = Path(path)
    if target.stat().st_size > 200_000:
        raise ValueError("Case file exceeds review budget")
    value = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema_version") != 1:
        raise ValueError("Unexpected case schema")
    return value


def audit_case(case: dict) -> dict:
    """Structural rubric: independently inspectable controls, scaled to 100.

    A 100/100 means ONLY this technical fixture passed its structural contract;
    accuracy, unbiased framing and newsworthiness remain unmeasured.
    """
    checks = dict.fromkeys(SHAKEOUT_RULES, False)
    try:
        as_of = _utc(case["as_of_utc"])
        sources = case["sources"]
        claims = case["claims"]
        article = case["article"]
        market = case["market_reference"]
        source_map = {row["source_id"]: row for row in sources}
        claim_map = {row["claim_id"]: row for row in claims}
        if (not isinstance(sources, list) or not isinstance(claims, list) or
                not isinstance(article["paragraphs"], list)):
            raise ValueError("Missing content arrays")
        checks["no_real_market_change_assumed"] = (
            market.get("signal_detected") is False and
            market.get("movement_claimed") is False and
            isinstance(market.get("observed_at"), int) and
            market["observed_at"] <= as_of)
        checks["valid_source_metadata"] = (
            3 <= len(sources) <= 15 and len(source_map) == len(sources) and
            all(re.fullmatch(r"[a-z][a-z0-9_-]{2,48}", s["source_id"]) and
                _web_url(s["url"]) and s["kind"] in KINDS and
                bool(s["publisher"].strip()) and bool(s["independent_origin"].strip()) and
                30 <= len(s["captured_excerpt"]) <= 400
                for s in sources))
        checks["no_future_sources"] = (
            all(0 < _utc(s["published_at"]) <= as_of for s in sources))
        checks["distinct_source_origins"] = (
            len({s["independent_origin"] for s in sources}) >= 3 and
            any(s["kind"] in {"official_record", "original_research"} for s in sources) and
            any(s["kind"] == "independent_reporting" for s in sources))
        checks["source_linked_claims"] = (
            len(claims) >= 6 and len(claim_map) == len(claims) and
            all(re.fullmatch(r"[a-z][a-z0-9_-]{2,48}", c["claim_id"]) and
                bool(c["statement"].strip()) and
                1 <= len(c["source_ids"]) <= 4 and
                set(c["source_ids"]) <= set(source_map) and
                c["role"] in ROLES and
                20 <= len(c["supporting_excerpt"]) <= 300 and
                any(c["supporting_excerpt"] in source_map[s]["captured_excerpt"]
                    for s in c["source_ids"]) and
                c["certainty"] in {"reported", "attributed_hypothesis"}
                for c in claims))
        roles = {c["role"] for c in claims}
        checks["uncertainty_and_counterpoint"] = (
            {"new_development", "prior_expectations", "explanation", "stakes", "counterpoint", "future_watch"} <= roles and
            len(case.get("unresolved_questions", [])) >= 2 and
            all(c["certainty"] == "attributed_hypothesis"
                for c in claims if c["role"] == "explanation"))
        checks["paragraph_evidence_linkage"] = (
            5 <= len(article["paragraphs"]) <= 25 and
            all(bool(p["text"].strip()) and
                set(p["claim_ids"]) <= set(claim_map) and bool(p["claim_ids"]) and
                set(p["source_ids"]) <= set(source_map) and bool(p["source_ids"]) and
                set(source_id for claim_id in p["claim_ids"]
                    for source_id in claim_map[claim_id]["source_ids"]) <= set(p["source_ids"])
                for p in article["paragraphs"]))
        # Only supplied exact direct quotes from short captured excerpts may
        # appear as curly quotes. No snippets or source bodies are fetched.
        rendered = " ".join(p["text"] for p in article["paragraphs"])
        quotes = re.findall(r"“([^”]+)”", rendered)
        checks["quote_text_provenance"] = (
            all(any(q in s["captured_excerpt"] for s in sources) for q in quotes) and
            all(len(q.split()) <= 24 for q in quotes))
        checks["market_secondary_headline"] = (
            20 <= len(article["headline"].strip()) <= 120 and
            not re.search(r"polymarket|odds|market price|%|percentage points",
                          article["headline"], re.I) and
            len(rendered.split()) >= 200 and
            "market_context" not in {c["role"] for c in claims[:2]})
        pitches = parse_story_pitches(case.get("story_pitches"))
        selection = parse_editorial_selection(case.get("editorial_selection"))
        pitch_issues = audit_story_selection(
            pitches, selection, {c["claim_id"]: c["role"] for c in claims},
            article_headline=article["headline"],
        )
        first_claims = {claim_map[c]["role"] for c in article["paragraphs"][0]["claim_ids"]}
        checks["story_thesis_selection"] = (
            not pitch_issues and "market_context" not in first_claims and
            bool(first_claims.intersection({"new_development", "prior_expectations"}))
        )
        checks["human_release_gate_disabled"] = (
            article.get("publication_enabled") is False and
            article.get("human_semantic_factcheck") is False and
            article.get("status") == "SHADOW_ONLY")
    except (KeyError, TypeError, ValueError, AttributeError, OverflowError):
        # Invalid content never throws a raw source body into operational logs.
        pass
    return {
        "evaluation_type": "offline_structural_field_trial",
        "checks": checks,
        "score": round(100 * sum(checks.values()) / len(checks)),
        "story_selection_issues": locals().get("pitch_issues", ["story_selection_not_evaluated"]),
        "publication_enabled": False,
        "semantic_accuracy_certified": False,
        "human_editorial_quality_measured": False,
    }


def render_shadow(case: dict) -> str:
    report = audit_case(case)
    if report["score"] != 100:
        raise ValueError("Shadow article failed structural audit")
    article = case["article"]
    sources = {s["source_id"]: s for s in case["sources"]}
    result = [f"# {article['headline']}", "", f"*{article['deck']}*", "",
              "> **SHADOW REPORT — NOT PUBLISHED OR INDEPENDENTLY FACT-CHECKED.**",
              "> Market snapshot is a discovery reference only. No qualifying movement was observed.", ""]
    seen: list[str] = []
    for paragraph in article["paragraphs"]:
        refs = []
        for source_id in paragraph["source_ids"]:
            if source_id not in seen:
                seen.append(source_id)
            refs.append(f"[{source_id}]")
        result.extend([paragraph["text"].strip() + " " + " ".join(refs), ""])
    result.extend(["## Sources and outstanding checks", ""])
    for source_id in seen:
        source = sources[source_id]
        result.append(f"- [{source_id}]: [{source['publisher']}]({source['url']}) ({source['published_at']}; {source['kind']}).")
    result.extend(["", "### Questions the reporter must still resolve", ""])
    result.extend(f"- {q}" for q in case["unresolved_questions"])
    result.extend(["", "**Editorial status:** HELD — an independent semantic fact-check and owner approval are required.", ""])
    selection = parse_editorial_selection(case["editorial_selection"])
    pitches = {p.pitch_id: p for p in parse_story_pitches(case["story_pitches"])}
    result.extend(["## Editorial story spine (internal shadow review)", "",
                   f"- **Chosen angle:** {pitches[selection.selected_pitch_id].thesis}",
                   f"- **Why this angle:** {selection.rationale}",
                   "- **Competing angles assessed:** " + "; ".join(
                       p.working_headline for p in pitches.values()
                       if p.pitch_id != selection.selected_pitch_id),
                   "- **Quality caveat:** structural checks passed; narrative merit, originality "
                   "and semantic accuracy are not independently scored or certified.", ""])
    return "\n".join(result)
