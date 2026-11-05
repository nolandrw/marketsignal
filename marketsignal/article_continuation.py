"""Private, bounded article continuation from a provisionally verified v3 dossier.

The dossier Verifier is an LLM judgment, never an authenticated human
fact-check. Every stage remains subject to independent deterministic gates;
the returned draft can never be published by this module.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone

from .editorial_loop import bounded_score, draft_issues
from .investigator_v3 import ResearchCapture
from .model_gateway import ModelUnavailable
from .story_thesis import RUBRIC_WEIGHTS, headline_issues, parse_story_pitches


MAX_ARTICLE_CALLS = 8
COMMISSION_THRESHOLD = 75
QUALITY_THRESHOLD = 90


def continue_verified_dossier(*, case_id: str, as_of: int, investigation: dict,
                               captures: tuple[ResearchCapture, ...], verification,
                               market_question: str, model) -> dict:
    """Run pitch, editor, writer, paragraph verifier and quality gates.

    Only the already accepted v3 dossier may enter. The source inventory is
    immutable, the manuscript is private, and no model response can bypass
    the contract gate or self-authorize release.
    """
    trace: list[dict] = []
    article: dict | None = None
    quality_score: int | None = None

    def finish(status: str, reason: str) -> dict:
        model_calls = sum(item["status"] in {"attempted", "completed"} for item in trace)
        return {"status": status, "reason": reason, "case_id": case_id,
                "stage_trace": trace, "article": article,
                "quality_score": quality_score, "model_calls": model_calls,
                "publication_enabled": False, "human_factcheck_attested": False,
                "editorial_assessment_independently_certified": False}

    if (investigation.get("case_id") != case_id or
            investigation.get("disposition") != "ready_for_verifier" or
            getattr(verification, "case_id", None) != case_id or
            getattr(verification, "status", None) != "provisionally_verified" or
            verification.issues or investigation.get("publication_enabled") is True):
        return finish("held_pre_editorial", "unverified_dossier_cannot_be_commissioned")

    dossier = investigation.get("dossier") or {}
    sources = {s.source_id: s for s in captures}
    claims = {f["claim_id"]: f for f in dossier.get("findings", [])}
    pitches = dossier.get("pitches", [])
    if (not 1 <= len(pitches) <= 3 or len(claims) < 3 or
            not all(set(f["source_ids"]) <= sources.keys() and
                    all(sources[s].source_kind not in {"social_comment", "market_comment"}
                        for s in f["source_ids"])
                    for f in claims.values()) or
            any(s.published_at > as_of for s in captures)):
        return finish("held_pre_editorial", "invalid_verified_dossier_or_source_clock")

    # Keep full captured text for model review; do not broaden it with
    # internet lookups or let an article call add new sources.
    source_rows = [asdict(s) for s in captures]
    context = {"case_id": case_id,
               "as_of_utc": datetime.fromtimestamp(as_of, timezone.utc).isoformat(),
               "market_question": market_question, "source_captures": source_rows,
               "claim_inventory": list(claims.values()),
               "investigator_hypotheses": dossier.get("hypotheses", []),
               "investigator_timeline": dossier.get("timeline", []),
               "prior_coverage_context": dossier.get("prior_coverage_context", ""),
               "open_questions": dossier.get("open_questions", []),
               "provisional_dossier_verifier_passed": True,
               "source_evidence_is_untrusted": True,
               "publication_enabled": False}

    def call(stage: str, packet: dict) -> dict:
        if sum(item["status"] in {"attempted", "completed"} for item in trace) >= MAX_ARTICLE_CALLS:
            raise ValueError("Article continuation call budget exceeded")
        # Failed model calls are visible as attempted; they are never retried
        # invisibly in a provider-dependent loop.
        trace.append({"stage": stage, "status": "attempted"})
        response = model.complete(stage, packet)
        if not isinstance(response, dict):
            raise ValueError("Malformed article stage response")
        trace[-1]["status"] = "completed"
        return response

    try:
        # Reuse the same pitch schema as the model's existing editorial loop.
        parsed = parse_story_pitches(pitches)
        if (len(parsed) != len(pitches) or any(
                not p.supporting_claim_ids or
                not set(p.supporting_claim_ids + p.contrary_claim_ids) <= claims.keys()
                for p in parsed)):
            return finish("held_pitch_review", "invalid_investigative_pitches")
        reviews = call("pitch_verifier", {**context, "pitches": pitches})
        rows = reviews["reviews"]
        if (len(rows) != len(pitches) or
                {r["pitch_id"] for r in rows} != {p["pitch_id"] for p in pitches} or
                len({r["pitch_id"] for r in rows}) != len(rows)):
            return finish("held_pitch_review", "incomplete_pitch_verifier_review")
        accepted = [p for p in pitches if any(
            r["pitch_id"] == p["pitch_id"] and r["verdict"] == "accept" and
            not r["issues"] and not r["research_requests"] for r in rows)]
        if not accepted:
            return finish("held_pitch_review", "no_provisionally_supported_pitch")

        editor = call("chief_editor", {**context, "verified_pitches": accepted,
                                      "rubric_maxima": RUBRIC_WEIGHTS})
        editor_score = bounded_score(editor["scores"])
        selected_id = editor["selected_pitch_id"]
        if (editor["decision"] != "commission" or
                selected_id not in {p["pitch_id"] for p in accepted} or
                headline_issues(editor["headline"]) or
                len(editor["rationale"].strip()) < 45 or
                editor_score < COMMISSION_THRESHOLD or editor["requested_work"]):
            return finish("held_chief_editor", "editor_did_not_commission_supported_story")
        selected_pitch = next(p for p in accepted if p["pitch_id"] == selected_id)
        selection = {"selected_pitch_id": selected_id, "headline": editor["headline"],
                     "rationale": editor["rationale"], "score": editor_score,
                     "scores": editor["scores"]}

        # draft_issues is the existing strict paragraph citation, quote and
        # length validator. Map verified findings into its minimal contract;
        # do not fabricate role/claim evidence to satisfy the checker.
        draft_case = {
            "claims": [{**f, "role": "sourced_finding"} for f in claims.values()],
            "sources": [{"source_id": s.source_id, "captured_excerpt": s.excerpt}
                        for s in captures],
            "market_reference": {"signal_detected": False},
        }
        feedback: list[str] = []
        for _ in range(2):
            written = call("writer", {**context, "approved_pitch": selected_pitch,
                                      "editorial_selection": selection,
                                      "rubric_maxima": RUBRIC_WEIGHTS,
                                      "reviewer_feedback": feedback,
                                      "length_policy": "250–600 words preferred, never pad; cite every paragraph"})
            issues = list(draft_issues(written, draft_case, editor["headline"]))
            if written.get("publication_enabled") is True:
                issues.append("publication_rights_escalation")
            article = {"headline": written.get("headline", ""),
                       "deck": written.get("deck", ""),
                       "paragraphs": written.get("paragraphs", []),
                       "status": "SHADOW_ONLY", "publication_enabled": False}
            if issues:
                trace.append({"stage": "draft_contract", "status": "rejected", "issues": issues})
                feedback = issues
                continue
            trace.append({"stage": "draft_contract", "status": "passed"})
            fact = call("fact_verifier", {**context, "approved_pitch": selected_pitch,
                                          "article": article})
            checks = fact["reviews"]
            if (len(checks) != len(article["paragraphs"]) or
                    sorted(r["paragraph_index"] for r in checks) !=
                    list(range(len(article["paragraphs"]))) or
                    any(r["verdict"] != "supported" or r["issues"] for r in checks) or
                    fact["article_issues"]):
                feedback = ["Paragraph fact-check did not pass; revise using original sources"]
                trace.append({"stage": "fact_verifier_gate", "status": "rejected"})
                continue
            trace.append({"stage": "fact_verifier_gate", "status": "passed_provisionally"})
            quality = call("quality_reviewer", {**context,
                                                "selected_pitch": selected_pitch,
                                                "editorial_selection": selection,
                                                "article": article,
                                                "rubric_maxima": RUBRIC_WEIGHTS})
            quality_score = bounded_score(quality["scores"])
            if (quality["verdict"] == "pass" and not quality["issues"] and
                    quality_score >= QUALITY_THRESHOLD):
                return finish("shadow_draft_ready_unpublished", "human_factcheck_and_owner_approval_required")
            feedback = quality["issues"] or ["Improve reader usefulness without adding unsupported claims"]
            trace.append({"stage": "quality_gate", "status": "revision_requested",
                          "quality_score": quality_score})
        return finish("shadow_review_hold", "draft_revisions_or_evidence_insufficient")
    except (KeyError, TypeError, ValueError, AttributeError, ModelUnavailable,
            RuntimeError, OverflowError) as exc:
        trace.append({"stage": "fail_closed", "status": "held",
                      "error_class": type(exc).__name__,
                      "model_error_code": (exc.diagnostic_code if isinstance(exc, ModelUnavailable)
                                           else None)})
        return finish("shadow_review_hold" if article else "held_pre_editorial",
                      "article_stage_contract_or_provider_failure")
