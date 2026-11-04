"""Bounded, source-grounded *shadow* reporting loop with explicit agent handoffs.

Each agent can run through ResponsesJSONModel or a conspicuously replayed
curated case. Neither path can publish. Structural checks prove provenance
and bounded handoffs; model semantic reviews are NOT independent certification.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from typing import Protocol

from .field_trial import _utc, _web_url
from .model_gateway import ModelUnavailable, STAGE_INSTRUCTIONS
from .story_thesis import (RUBRIC_WEIGHTS, StoryPitch,
                           headline_issues, parse_story_pitches)


class StageModel(Protocol):
    def complete(self, stage: str, payload: dict) -> dict: ...


@dataclass(frozen=True)
class LoopPolicy:
    max_investigation_rounds: int = 2
    max_writer_rounds: int = 2
    max_model_calls: int = 14
    commission_threshold: int = 75
    editorial_quality_threshold: int = 90

    def __post_init__(self):
        if not (1 <= self.max_investigation_rounds <= 3 and
                1 <= self.max_writer_rounds <= 3 and
                5 <= self.max_model_calls <= 24 and
                65 <= self.commission_threshold <= 95 and
                80 <= self.editorial_quality_threshold <= 100):
            raise ValueError("Unbounded or invalid editorial policy")


@dataclass
class ShadowRun:
    status: str = "research_hold"
    disposition_reason: str = "not_started"
    selected: dict | None = None
    pitches: list[dict] = field(default_factory=list)
    article: dict | None = None
    reviews: list[dict] = field(default_factory=list)
    model_calls: int = 0
    model_call_budget: int = 14
    trace: list[dict] = field(default_factory=list)
    source_issues: list[str] = field(default_factory=list)
    quality_score: int | None = None
    final_editorial_score: int | None = None
    process_rubric: dict = field(default_factory=dict)
    agent_diagnostics: dict = field(default_factory=dict)
    publication_enabled: bool = False
    semantic_accuracy_certified: bool = False
    independently_human_graded: bool = False

    def to_dict(self) -> dict:
        result = asdict(self)
        result["process_rubric"] = process_scorecard(self)
        result["agent_diagnostics"] = agent_diagnostics(self)
        return result


def process_scorecard(run: ShadowRun) -> dict:
    """Mechanical workflow completeness only; NOT independently graded journalism."""
    stages = [entry["stage"] for entry in run.trace]
    reviews = [entry["stage"] for entry in run.reviews]
    checks = {
        "source_integrity": not run.source_issues,
        "bounded_supported_pitches": 1 <= len(run.pitches) <= 3,
        "bounded_calls": run.model_calls <= run.model_call_budget,
        "pitch_verifier_handoff": "pitch_verifier" in stages,
        "editor_owned_selection": bool(run.selected and run.selected.get("headline")),
        "documented_editorial_rubric": run.final_editorial_score is not None,
        "writer_output_and_provenance": bool(run.article and "deterministic_draft_gate" not in reviews),
        "article_fact_verifier_handoff": "fact_verifier" in stages,
        "quality_critique_recorded": "quality_reviewer" in stages,
        "release_safety": not run.publication_enabled and not run.semantic_accuracy_certified,
    }
    # The score reports how much of the workflow was actually exercised in
    # this run. Holding due to poor quality can still be a process success.
    return {"type": "deterministic_process_coverage", "score": 10 * sum(checks.values()),
            "threshold": 90, "checks": checks, "not_a_journalistic_quality_score": True}


def agent_diagnostics(run: ShadowRun) -> dict:
    """Stage-specific operational outcomes, not letter grades masquerading as truth."""
    names = ("investigator", "pitch_verifier", "chief_editor", "writer",
             "fact_verifier", "quality_reviewer")
    diagnostics = {}
    for name in names:
        attempts = sum(entry["stage"] == name for entry in run.trace)
        diagnostics[name] = {"attempts": attempts,
                             "execution": "completed" if attempts else "not_reached",
                             "evidence_of_semantic_accuracy": False}
    diagnostics["quality_reviewer"]["provisional_article_score"] = run.quality_score
    return diagnostics


def _hash(item: object) -> str:
    return hashlib.sha256(json.dumps(item, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


def evidence_issues(case: dict) -> tuple[str, ...]:
    """Local source/claim gate; no model can waive these constraints."""
    issues: list[str] = []
    try:
        as_of = _utc(case["as_of_utc"])
        sources = case["sources"]
        claims = case["claims"]
        if not isinstance(sources, list) or not isinstance(claims, list):
            return ("invalid_source_inventory",)
        source_map = {s["source_id"]: s for s in sources}
        claim_map = {c["claim_id"]: c for c in claims}
        if not 3 <= len(sources) <= 25 or len(source_map) != len(sources):
            issues.append("source_count_or_identity_invalid")
        if (len({s["independent_origin"] for s in sources}) < 3 or
                not any(s["kind"] in ("official_record", "original_research") for s in sources) or
                not any(s["kind"] == "independent_reporting" for s in sources)):
            issues.append("insufficient_origin_diversity")
        for source in sources:
            if (not re.fullmatch(r"[a-z][a-z0-9_-]{2,48}", source["source_id"]) or
                    not _web_url(source["url"]) or
                    not 0 < _utc(source["published_at"]) <= as_of or
                    source["kind"] not in {"official_record", "original_research", "independent_reporting", "statement"} or
                    not source["publisher"].strip() or not source["independent_origin"].strip() or
                    not 30 <= len(source["captured_excerpt"]) <= 400):
                issues.append("invalid_source_metadata_or_date")
        if len(claims) < 6 or len(claim_map) != len(claims):
            issues.append("insufficient_claim_inventory")
        roles = {c["role"] for c in claims}
        if not {"new_development", "prior_expectations", "stakes", "counterpoint"} <= roles:
            issues.append("missing_required_context_roles")
        for claim in claims:
            if (not re.fullmatch(r"[a-z][a-z0-9_-]{2,48}", claim["claim_id"]) or
                    not 20 <= len(claim["supporting_excerpt"]) <= 300 or
                    not claim["statement"].strip() or
                    not 1 <= len(claim["source_ids"]) <= 4 or
                    not set(claim["source_ids"]) <= source_map.keys() or
                    not any(claim["supporting_excerpt"] in source_map[s]["captured_excerpt"]
                            for s in claim["source_ids"]) or
                    claim["role"] not in {"new_development", "prior_expectations", "explanation", "stakes",
                                           "counterpoint", "future_watch", "market_context"} or
                    claim["certainty"] not in {"reported", "attributed_hypothesis"} or
                    (claim["role"] == "explanation" and claim["certainty"] != "attributed_hypothesis")):
                issues.append("claim_capture_mismatch")
        market = case["market_reference"]
        if (not isinstance(market.get("signal_detected"), bool) or
                not isinstance(market.get("movement_claimed"), bool) or
                market.get("movement_claimed") and not market["signal_detected"]):
            issues.append("unsubstantiated_market_movement")
        if not case.get("unresolved_questions"):
            issues.append("missing_reporting_questions")
    except (KeyError, TypeError, ValueError, AttributeError, OverflowError):
        issues.append("malformed_evidence_packet")
    return tuple(sorted(set(issues)))


def pitch_issues(pitch: StoryPitch, case: dict) -> tuple[str, ...]:
    """Validate one angle independently of an editorial selection."""
    issues: list[str] = list(headline_issues(pitch.working_headline))
    claim_map = {c["claim_id"]: c for c in case["claims"]}
    source_map = {s["source_id"]: s for s in case["sources"]}
    if not re.fullmatch(r"[a-z][a-z0-9_-]{2,60}", pitch.pitch_id):
        issues.append("invalid_pitch_id")
    if any(not 22 <= len(getattr(pitch, key).strip()) <= 700 for key in (
            "thesis", "conflict", "surprise", "why_now", "stakes", "original_value")):
        issues.append("incomplete_narrative")
    ids = set(pitch.supporting_claim_ids) | set(pitch.contrary_claim_ids)
    if not ids <= claim_map.keys() or not pitch.contrary_claim_ids:
        issues.append("unsupported_or_missing_counterevidence")
    supported = {claim_map[c]["role"] for c in pitch.supporting_claim_ids if c in claim_map}
    contrary = {claim_map[c]["role"] for c in pitch.contrary_claim_ids if c in claim_map}
    if (len(set(pitch.supporting_claim_ids)) < 3 or
            not {"new_development", "prior_expectations", "stakes"} <= supported or
            "counterpoint" not in contrary):
        issues.append("missing_story_spine")
    origins = {source_map[s]["independent_origin"] for cid in ids if cid in claim_map
               for s in claim_map[cid]["source_ids"] if s in source_map}
    if len(origins) < 2:
        issues.append("pitch_lacks_independent_sources")
    return tuple(sorted(set(issues)))


def bounded_score(scores: object) -> int:
    if not isinstance(scores, dict) or set(scores) != set(RUBRIC_WEIGHTS):
        raise ValueError("Missing rubric dimensions")
    for dimension, maximum in RUBRIC_WEIGHTS.items():
        value = scores[dimension]
        if type(value) is not int or not 0 <= value <= maximum:
            raise ValueError("Out-of-range editorial rubric score")
    return sum(scores.values())


def draft_issues(article: dict, case: dict, headline: str) -> tuple[str, ...]:
    issues: list[str] = list(headline_issues(article.get("headline", "")))
    try:
        paragraphs = article["paragraphs"]
        claim_map = {c["claim_id"]: c for c in case["claims"]}
        source_map = {s["source_id"]: s for s in case["sources"]}
        if article["headline"] != headline:
            issues.append("unapproved_headline_change")
        if not 4 <= len(paragraphs) <= 25:
            issues.append("invalid_paragraph_count")
        if not 30 <= len(article["deck"].strip()) <= 320:
            issues.append("invalid_deck")
        text = " ".join(p["text"] for p in paragraphs)
        if not 170 <= len(text.split()) <= 1300:
            issues.append("invalid_article_length")
        for index, paragraph in enumerate(paragraphs):
            citations = set(paragraph["source_ids"])
            claims = set(paragraph["claim_ids"])
            if (not 25 <= len(paragraph["text"].strip()) <= 2600 or
                    not citations or not claims or not claims <= claim_map.keys() or
                    not citations <= source_map.keys() or
                    not {s for c in claims for s in claim_map[c]["source_ids"]} <= citations):
                issues.append("unlinked_or_empty_paragraph:" + str(index))
        if paragraphs[0]["claim_ids"] and all(
                claim_map.get(c, {}).get("role") == "market_context"
                for c in paragraphs[0]["claim_ids"]):
            issues.append("market_centered_lede")
        for quoted in re.findall(r"“([^”]+)”", text):
            if (len(quoted.split()) > 24 or not any(quoted in s["captured_excerpt"]
                                                   for s in case["sources"])):
                issues.append("unverifiable_printed_quote")
        if case["market_reference"]["signal_detected"] is False and re.search(
                r"(?i)(?:odds|market|contract|polymarket).{0,60}(?:surged|jumped|plunged|spiked|fell|rose)", text):
            issues.append("fabricated_market_movement")
        if article.get("publication_enabled") is True:
            issues.append("publication_rights_escalation")
    except (ValueError, KeyError, TypeError, AttributeError):
        issues.append("malformed_draft")
    return tuple(sorted(set(issues)))


class CaseReplayModel:
    """Recorded human-curated material, NOT simulated independent model inference.

    Useful for regression-testing the real handoffs against real-topic source
    captures without using credentials or implying autonomous reporting.
    """

    def __init__(self, case: dict):
        self.case = case

    def complete(self, stage: str, payload: dict) -> dict:
        if stage == "investigator":
            return {"pitches": self.case["story_pitches"],
                    "research_requests": self.case.get("unresolved_questions", [])}
        if stage == "pitch_verifier":
            return {"reviews": [
                {"pitch_id": pitch["pitch_id"], "verdict": "accept",
                 "issues": [], "research_requests": []}
                for pitch in payload["pitches"]]}
        if stage == "chief_editor":
            return {"decision": "commission", **self.case["editorial_selection"],
                    "scores": {"central_conflict": 18, "public_significance": 18,
                               "surprise_or_reversal": 13, "specificity": 13,
                               "evidence_strength": 12, "original_value": 4,
                               "narrative_depth": 4}, "requested_work": []}
        if stage == "writer":
            return {"headline": self.case["article"]["headline"],
                    "deck": self.case["article"]["deck"],
                    "paragraphs": self.case["article"]["paragraphs"]}
        if stage == "fact_verifier":
            return {"reviews": [{"paragraph_index": i, "verdict": "supported", "issues": []}
                                for i in range(len(payload["article"]["paragraphs"]))],
                    "article_issues": []}
        if stage == "quality_reviewer":
            # Recorded baseline estimates, not an actual synthetic audience or
            # independent assessment. The derivative story is held for value.
            return {"verdict": "revise",
                    "scores": {"central_conflict": 17, "public_significance": 17,
                               "surprise_or_reversal": 12, "specificity": 12,
                               "evidence_strength": 10, "original_value": 3,
                               "narrative_depth": 4},
                    "issues": ["No independently reported insight beyond existing coverage",
                               "Short excerpts cannot substantiate every nuance of the causal framing"],
                    "strengths": ["Concrete political conflict and historical stakes"]}
        raise ValueError("Unknown replay stage")


class EditorialShadowLoop:
    """Retryable newsroom choreography; the release state is always HELD."""

    def __init__(self, model: StageModel, policy: LoopPolicy | None = None):
        self.model = model
        self.policy = policy or LoopPolicy()

    def run(self, case: dict) -> ShadowRun:
        result = ShadowRun(model_call_budget=self.policy.max_model_calls)
        result.source_issues = list(evidence_issues(case))
        if result.source_issues:
            result.disposition_reason = "invalid_source_evidence"
            return result
        claims = case["claims"]
        sources = case["sources"]
        context = {
            "case_id": case["case_id"], "as_of_utc": case["as_of_utc"],
            "topic": case["market_reference"]["question"],
            "source_captures": [{k: s[k] for k in ("source_id", "publisher", "published_at",
                                                     "kind", "independent_origin", "url", "captured_excerpt")}
                                for s in sources],
            "claim_inventory": claims,
            "research_questions": case["unresolved_questions"],
            "market_reference": case["market_reference"],
            "source_evidence_is_untrusted": True,
            "publication_enabled": False,
        }

        def call(stage: str, payload: dict) -> dict:
            if result.model_calls >= self.policy.max_model_calls:
                raise ModelUnavailable("Total model-call budget exceeded")
            result.model_calls += 1
            response = self.model.complete(stage, payload)
            if not isinstance(response, dict):
                raise ValueError("Malformed stage response")
            result.trace.append({"step": len(result.trace) + 1,
                                 "stage": stage, "input_sha256": _hash(payload),
                                 "output_sha256": _hash(response),
                                 "agent_prompt_sha256": hashlib.sha256(
                                     STAGE_INSTRUCTIONS[stage].encode("utf-8")).hexdigest(),
                                 "model_id": getattr(self.model, "model", "scripted_replay"),
                                 "output_bytes": len(json.dumps(response)),
                                 "status": "completed"})
            return response

        def hold(reason: str) -> ShadowRun:
            result.disposition_reason = reason
            result.status = "shadow_review_hold" if result.article else "research_hold"
            return result

        try:
            feedback: list[str] = []
            accepted: list[dict] = []
            for _ in range(self.policy.max_investigation_rounds):
                generated = call("investigator", {**context, "verifier_feedback": feedback})
                pitches = parse_story_pitches(generated.get("pitches"))
                result.pitches = [asdict(p) for p in pitches]
                if not 1 <= len(pitches) <= 3 or len({p.pitch_id for p in pitches}) != len(pitches):
                    feedback = ["Provide one to three distinct, sourced pitches; do not invent alternatives"]
                    continue
                local = {p.pitch_id: list(pitch_issues(p, case)) for p in pitches}
                reviews = call("pitch_verifier", {**context, "pitches": result.pitches,
                                                 "local_provenance_findings": local})
                if (not isinstance(reviews.get("reviews"), list) or
                        any(not isinstance(item, dict) or "pitch_id" not in item
                            for item in reviews["reviews"])):
                    return hold("malformed_pitch_verifier_review")
                by_id = {item["pitch_id"]: item for item in reviews["reviews"]}
                if (len(reviews["reviews"]) != len(pitches) or
                        len(by_id) != len(pitches) or set(by_id) != set(local)):
                    return hold("incomplete_pitch_verifier_review")
                accepted = []
                feedback = []
                for pitch in pitches:
                    review = by_id[pitch.pitch_id]
                    if (review["verdict"] not in ("accept", "revise", "reject") or
                            not isinstance(review["issues"], list)):
                        return hold("invalid_pitch_verifier_verdict")
                    # 'accept' with unresolved issues/research requests is not an acceptance.
                    verifier_notes = review["issues"] + review.get("research_requests", [])
                    if local[pitch.pitch_id] or review["verdict"] != "accept" or verifier_notes:
                        feedback.extend([pitch.pitch_id + ": " + item
                                         for item in local[pitch.pitch_id] + review["issues"]])
                        feedback.extend(review.get("research_requests", []))
                    else:
                        accepted.append(asdict(pitch))
                result.reviews.append({"stage": "pitch_verifier", "accepted_pitch_ids":
                                       [p["pitch_id"] for p in accepted],
                                       "feedback": feedback, "status": "provisional"})
                if accepted:
                    break
            if not accepted:
                return hold("no_provisionally_supported_story_pitch")

            editorial = call("chief_editor", {**context, "verified_pitches": accepted,
                                             "rejected_pitch_feedback": feedback,
                                             "rubric_maxima": RUBRIC_WEIGHTS})
            result.final_editorial_score = bounded_score(editorial["scores"])
            choice_id = editorial["selected_pitch_id"]
            if (editorial["decision"] != "commission" or
                    choice_id not in {p["pitch_id"] for p in accepted} or
                    headline_issues(editorial["headline"]) or
                    len(editorial["rationale"].strip()) < 45 or
                    result.final_editorial_score < self.policy.commission_threshold):
                return hold("chief_editor_declined_or_unsubstantiated_angle")
            # An unresolved desk request is a research HOLD, never an authorization
            # to proceed based on a numerical score alone.
            outstanding = editorial["requested_work"]
            if not isinstance(outstanding, list) or any(
                    not isinstance(item, str) or not item.strip() for item in outstanding):
                return hold("invalid_editor_research_request")
            if outstanding:
                result.reviews.append({"stage": "chief_editor", "status": "research_required",
                                       "requested_work": outstanding[:8]})
                return hold("chief_editor_requested_additional_reporting")
            result.selected = {"selected_pitch_id": choice_id,
                               "headline": editorial["headline"],
                               "rationale": editorial["rationale"],
                               "rubric": editorial["scores"],
                               "score": result.final_editorial_score,
                               "status": "provisional_model_or_replay_judgment"}
            selected_pitch = next(p for p in accepted if p["pitch_id"] == choice_id)
            revision_feedback: list[str] = []
            for _ in range(self.policy.max_writer_rounds):
                article = call("writer", {**context, "approved_pitch": selected_pitch,
                                          "editorial_selection": result.selected,
                                          "rubric_maxima": RUBRIC_WEIGHTS,
                                          "reviewer_feedback": revision_feedback,
                                          "length_policy": "Prefer 250–600 words; write less if thin, never pad"})
                issues = list(draft_issues(article, case, result.selected["headline"]))
                # Do not let an LLM or replay assert publication permission.
                if article.get("publication_enabled") is True:
                    issues.append("publication_rights_escalation")
                result.article = {"headline": article.get("headline", ""),
                                  "deck": article.get("deck", ""),
                                  "paragraphs": article.get("paragraphs", []),
                                  "status": "SHADOW_ONLY", "publication_enabled": False}
                if issues:
                    result.reviews.append({"stage": "deterministic_draft_gate", "issues": issues,
                                           "status": "rejected"})
                    revision_feedback = issues
                    continue
                fact = call("fact_verifier", {**context, "approved_pitch": selected_pitch,
                                             "article": result.article})
                reviewed = fact["reviews"]
                indices = [v["paragraph_index"] for v in reviewed]
                if sorted(indices) != list(range(len(result.article["paragraphs"]))):
                    return hold("incomplete_article_fact_verification")
                violations = ["paragraph_" + str(v["paragraph_index"]) + ": " + ", ".join(v["issues"])
                              for v in reviewed if v["verdict"] != "supported" or v["issues"]]
                violations.extend(fact["article_issues"])
                result.reviews.append({"stage": "fact_verifier", "issues": violations,
                                       "status": "provisional_model_or_replay_only"})
                if violations:
                    revision_feedback = violations
                    continue
                quality = call("quality_reviewer", {
                    "case_id": case["case_id"], "selected_pitch": selected_pitch,
                    "editorial_selection": result.selected,
                    "article": result.article,
                    "claims": claims, "source_provenance": context["source_captures"],
                    "rubric_maxima": RUBRIC_WEIGHTS,
                    "independent_reporting_not_available": True,
                })
                result.quality_score = bounded_score(quality["scores"])
                result.reviews.append({"stage": "quality_reviewer", "score": result.quality_score,
                                       "scores": quality["scores"], "issues": quality["issues"],
                                       "strengths": quality["strengths"],
                                       "status": "provisional_model_or_replay_only"})
                if (result.quality_score >= self.policy.editorial_quality_threshold and
                        quality["verdict"] == "pass" and not quality["issues"]):
                    result.status = "shadow_draft_meets_provisional_rubric"
                    result.disposition_reason = "human_factcheck_and_editor_signoff_still_required"
                    return result
                revision_feedback = quality["issues"] or [
                    f"Editorial value below {self.policy.editorial_quality_threshold}/100; improve supported story"]
            return hold("reviewer_requested_revisions_or_evidence_insufficient")
        except (ModelUnavailable, KeyError, TypeError, ValueError, AttributeError,
                OverflowError) as exc:
            # No source text, model outputs or provider errors in public logs.
            result.trace.append({"step": len(result.trace) + 1,
                                 "stage": "fail_closed", "error_class": type(exc).__name__})
            return hold("model_or_contract_failure")


def render_loop_report(case: dict, run: ShadowRun) -> str:
    """Private Markdown report, explicitly distinct from an article release."""
    lines = ["# MarketSignal investigative shadow run", "",
             f"**Case:** {case.get('case_id', 'unknown')}",
             f"**Status:** {run.status} — {run.disposition_reason}",
             "**Publication:** DISABLED; no independent semantic or audience certification.",
             "**Provenance:** curated real-topic excerpts and recorded editorial work "
             "when mode=replay; not fresh autonomous research.", "",
             "## Investigator's competing pitches", ""]
    for pitch in run.pitches:
        lines.extend([f"### {pitch['working_headline']}", "",
                      f"{pitch['thesis']}", "",
                      f"- Why now: {pitch['why_now']}",
                      f"- Opposition/counterevidence: {', '.join(pitch['contrary_claim_ids'])}", ""])
    if run.selected:
        lines.extend(["## Chief editor decision", "",
                      f"**Selected headline:** {run.selected['headline']}", "",
                      run.selected["rationale"], "",
                      f"**Provisional editor score:** {run.final_editorial_score}/100", ""])
    if run.article:
        source_lookup = {s["source_id"]: s for s in case["sources"]}
        lines.extend(["## Shadow newspaper draft", "",
                      f"# {run.article['headline']}", "", f"*{run.article['deck']}*", "",
                      "> **UNPUBLISHED — source-linked draft for critical review only.**", ""])
        for paragraph in run.article["paragraphs"]:
            seen_urls = set()
            citations = []
            for source_id in paragraph["source_ids"]:
                source = source_lookup.get(source_id)
                if source and source["url"] not in seen_urls:
                    seen_urls.add(source["url"])
                    citations.append(f"[{source['publisher']}]({source['url']})")
            links = " ".join(citations)
            lines.extend([paragraph["text"] + " " + links, ""])
    lines.extend(["## Evaluation (do not mistake for human scoring)", "",
                  f"- Deterministic process coverage: {process_scorecard(run)['score']}/100",
                  f"- Provisional blind-model/replay quality score: {run.quality_score if run.quality_score is not None else 'NOT MEASURED'}/100",
                  f"- Model/recorded stage calls: {run.model_calls}",
                  f"- Source integrity issues: {', '.join(run.source_issues) or 'none detected'}",
                  "- Independent article quality: NOT MEASURED",
                  "- Independent semantic fact-check: NOT PERFORMED",
                  "- Owner release approval: NOT GIVEN", ""])
    for item in run.reviews:
        lines.extend([f"- {item['stage']}: {json.dumps(item, ensure_ascii=False)}"])
    lines.extend(["", "## Audit trace", "",
                  "Each output is hashed; full source inventories are excluded from logs.", ""])
    for entry in run.trace:
        lines.append(f"- Step {entry['step']}: {entry['stage']} — {entry.get('status', entry.get('error_class', 'unknown'))}; "
                     f"output SHA-256 {entry.get('output_sha256', 'none')[:12]}")
    lines.extend(["", "## Missing evidence and next reporting", ""])
    lines.extend("- " + question for question in case.get("unresolved_questions", []))
    lines.append("")
    return "\n".join(lines)
