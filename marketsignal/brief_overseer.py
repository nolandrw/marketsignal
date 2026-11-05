"""Read-only process oversight for the private, experimental curation lane.

The overseer observes workflow traces and proposes *testable process repairs*.
It is not a second fact-checker, a model judge, an auto-prompt optimizer or a
release authority. Both this report and its HTML viewer are private artifacts.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
from hashlib import sha256
from html import escape
import json
from pathlib import Path

from .oversight import ProcessFailureEvent, ProcessOverseer


VERSION = "brief-process-overseer-v1"
FUNNEL = (
    ("Candidates", "candidate"),
    ("Coverage discovered", "coverage"),
    ("Editor commissioned", "commissioned"),
    ("Draft produced", "draft"),
    ("Provisional fact-check", "factcheck"),
    ("Unique after release desk", "release"),
)
STATUS_LABELS = {
    "shadow_brief_ready_unpublished": "Provisional draft",
    "held_redundant_brief": "Redundant draft",
    "held_release_editor": "Batch review held",
    "held_brief_review": "Fact-check hold",
    "held_editor": "Editorial hold",
    "held_no_coverage": "Coverage hold",
    "held_search": "Search hold",
    "held_stage_contract": "Stage failure",
}

# An operational gate yield is evidence of process throughput, not a model's
# editorial skill or a human judgment of the writing. Preserve the distinction
# in both the private JSON and its rendered dashboard.
AGENT_STAGES = (
    ("brief_scout", "Narrative scout", "AI agent", "Usable search path"),
    ("coverage_discovery", "Coverage discovery", "Research tool", "Dated coverage found"),
    ("brief_editor", "Commissioning editor", "AI agent", "Assignments commissioned"),
    ("brief_writer", "Brief writer", "AI agent", "Structured drafts accepted"),
    ("brief_factcheck", "Fact-checker", "AI agent", "Provisional passes"),
    ("brief_release_editor", "Release editor", "AI agent", "Unique briefs retained"),
)

# Placeholders, not invented zeros. These are a future analytics schema only;
# the private process report never queries visitor data or the publication.
AUDIENCE_METRICS = (
    ("Discovery & reach", (
        ("unique_readers", "Unique readers"),
        ("sessions", "Sessions"),
        ("organic_search_share", "Organic search share"),
    )),
    ("Reading & engagement", (
        ("article_views", "Article views"),
        ("engaged_time", "Average engaged time"),
        ("article_completion", "Article completion rate"),
    )),
    ("Loyalty & newsletter", (
        ("returning_reader_rate", "Returning reader rate"),
        ("newsletter_subscribers", "Newsletter subscribers"),
        ("newsletter_open_rate", "Newsletter open rate"),
    )),
    ("Growth & monetization", (
        ("article_shares", "Article shares"),
        ("newsletter_signup_rate", "Newsletter signup rate"),
        ("referral_clicks", "Referral or affiliate clicks"),
    )),
)


def _proposal(code: str, n: int, diagnosis: str, experiment: str,
              success: str, *, priority: str = "medium") -> dict:
    return {
        "proposal_id": sha256((VERSION + ":" + code).encode()).hexdigest()[:16],
        "failure_code": code, "priority": priority,
        "affected_cases": n, "root_cause_hypothesis": diagnosis,
        "proposed_experiment": experiment, "success_metric": success,
        "required_tests": ["frozen_replay", "held_out_cases", "human_review"],
        "status": "proposed_unapplied", "owner_approval_required": True,
    }


def _has_stage(brief: dict, name: str, state: str | None = None) -> bool:
    return any(row.get("stage") == name and
               (state is None or row.get("status") == state)
               for row in brief.get("stage_trace", []))


def _case_id(brief: dict, index: int) -> str:
    market_id = brief.get("market", {}).get("market_id")
    # Never use arbitrary free-form IDs as HTML or filenames.
    return str(market_id)[:80] if market_id is not None else f"case-{index:02d}"


def _agent_scorecard(briefs: list[dict], proposals: list[dict]) -> list[dict]:
    """Describe observed throughput; never manufacture editorial quality scores."""
    rows = []
    for stage, name, kind, yield_label in AGENT_STAGES:
        handled = [b for b in briefs if _has_stage(b, stage)]
        if stage == "brief_scout":
            succeeded = sum(_has_stage(b, "coverage_discovery") for b in handled)
        elif stage == "coverage_discovery":
            succeeded = sum(any(t.get("stage") == stage and
                                type(t.get("leads")) is int and t["leads"] > 0
                                for t in b["stage_trace"]) for b in handled)
        elif stage == "brief_editor":
            succeeded = sum(_has_stage(b, "brief_writer") for b in handled)
        elif stage == "brief_writer":
            succeeded = sum(_has_stage(b, "brief_contract", "passed") for b in handled)
        elif stage == "brief_factcheck":
            succeeded = sum(_has_stage(b, "brief_factcheck_gate", "passed_provisionally")
                            for b in handled)
        else:
            succeeded = sum(_has_stage(b, "brief_release_editor", "passed_unique")
                            for b in handled)
        rows.append({
            "stage": stage, "name": name, "kind": kind, "cases_reached": len(handled),
            "observed_yield": succeeded if handled else None,
            "observed_yield_label": yield_label,
            "human_quality_score": None,
            "quality_status": "Not rated — no human evaluation labels",
        })
    rows.append({
        "stage": "process_overseer", "name": "Process overseer", "kind": "Read-only audit",
        "cases_reached": len(briefs), "observed_yield": None,
        "observed_yield_label": f"{len(proposals)} proposed experiments; no auto-changes",
        "human_quality_score": None, "quality_status": "Process diagnosis only",
    })
    return rows


def _marketing_placeholders() -> dict:
    return {"status": "not_instrumented", "data_as_of": None,
            "groups": [{"title": title,
                        "metrics": [{"key": key, "label": label, "value": None}
                                    for key, label in metrics]}
                       for title, metrics in AUDIENCE_METRICS],
            "article_performance": []}


def analyze_brief_run(briefs: list[dict], manifest: dict | None = None,
                      *, run_label: str = "Private pilot") -> dict:
    """Turn existing private run outputs into an evidence-linked process review.

    No network/model access or authoring privileges. A model's `supported`
    verdict is *not* an independently validated truth or quality label.
    """
    if len(briefs) > 100 or not isinstance(manifest or {}, dict):
        raise ValueError("Unbounded or malformed brief diagnostics")
    manifest = manifest or {}
    events: list[ProcessFailureEvent] = []
    cases: list[dict] = []
    status_counts: Counter[str] = Counter()
    gates = Counter()
    known_events: dict[str, list[str]] = defaultdict(list)
    seen_ids: set[str] = set()
    release_seen = False
    for index, brief in enumerate(briefs, 1):
        if not isinstance(brief, dict) or not isinstance(brief.get("stage_trace"), list):
            raise ValueError("Malformed private brief result")
        case_id = _case_id(brief, index)
        if case_id in seen_ids:
            raise ValueError("Duplicate market identity in diagnostic run")
        seen_ids.add(case_id)
        market = brief.get("market") or {}
        status = str(brief.get("status", "unknown"))
        status_counts[status] += 1
        gates["candidate"] += 1
        if any(row.get("stage") == "coverage_discovery" and
               isinstance(row.get("leads"), int) and row["leads"] > 0
               for row in brief["stage_trace"]):
            gates["coverage"] += 1
        if _has_stage(brief, "brief_writer"):
            gates["commissioned"] += 1
        if isinstance(brief.get("article"), dict) and brief["article"].get("paragraphs"):
            gates["draft"] += 1
        if _has_stage(brief, "brief_factcheck_gate", "passed_provisionally"):
            gates["factcheck"] += 1
        if _has_stage(brief, "brief_release_editor"):
            release_seen = True
        if _has_stage(brief, "brief_release_editor", "passed_unique"):
            gates["release"] += 1
        if status == "held_no_coverage":
            events.append(ProcessFailureEvent(case_id, "coverage_discovery", "brief_coverage_empty"))
        if status == "held_editor":
            events.append(ProcessFailureEvent(case_id, "brief_editor", "brief_editor_hold"))
        if status == "held_brief_review":
            events.append(ProcessFailureEvent(case_id, "brief_factcheck", "brief_factcheck_rejection"))
        if status == "held_redundant_brief":
            events.append(ProcessFailureEvent(case_id, "brief_release_editor", "brief_duplicate_story"))
        if status == "held_release_editor":
            events.append(ProcessFailureEvent(case_id, "brief_release_editor", "brief_batch_review_error"))
        for row in brief["stage_trace"]:
            if row.get("stage") == "brief_contract" and row.get("status") == "rejected":
                events.append(ProcessFailureEvent(case_id, "brief_writer", "brief_manuscript_contract"))
            if row.get("stage") == "coverage_discovery" and row.get("source_errors"):
                events.append(ProcessFailureEvent(case_id, "coverage_discovery", "brief_source_error"))
        title = str((brief.get("article") or {}).get("headline", ""))
        if title and any(term in title.casefold() for term in ("market odds", "markets lift odds",
                                                               "betting odds", "polymarket")):
            events.append(ProcessFailureEvent(case_id, "brief_editor", "brief_market_centered_headline"))
        event_id = str(market.get("event_id", ""))
        if event_id and status in {"shadow_brief_ready_unpublished", "held_redundant_brief"}:
            known_events[event_id].append(case_id)
        final_stage = brief["stage_trace"][-1].get("stage", "not_started") if brief["stage_trace"] else "not_started"
        cases.append({
            "case_id": case_id,
            "market_question": str(market.get("question", "Unknown contract"))[:240],
            "trigger": str(market.get("trigger", "price_movement"))[:60],
            "change_pp": market.get("change_pp"),
            "status": status,
            "status_label": STATUS_LABELS.get(status, "Held/other"),
            "model_calls": int(brief.get("model_calls", 0)),
            "last_gate": str(final_stage)[:60],
            "duplicate_of": str(brief.get("duplicate_of", ""))[:80],
            "editor_score": brief.get("editor_score"),
            "human_reviewed": brief.get("human_factcheck_attested") is True,
        })

    # The generic ProcessOverseer learns only from stage events. It never
    # re-evaluates manuscript factual claims or uses AI approval as truth.
    diagnosis = ProcessOverseer().diagnose(events)
    event_count = sum(len(ids) - 1 for ids in known_events.values() if len(ids) > 1)
    if event_count:
        diagnosis["reason_case_counts"]["brief_same_event_overlap"] = event_count

    counts = diagnosis["reason_case_counts"]
    proposals = []
    if counts.get("brief_factcheck_rejection", 0) >= 2:
        proposals.append(_proposal(
            "brief_factcheck_rejection", counts["brief_factcheck_rejection"],
            "Multiple manuscripts fail paragraph-level review, often after revision",
            "Preserve exact fact-check tickets; replay a source-to-writer revision pass",
            "Reduce held fact-check rate without increasing unsupported published claims",
            priority="high"))
    if event_count or counts.get("brief_duplicate_story", 0):
        proposals.append(_proposal(
            "brief_same_event_overlap", max(event_count, counts.get("brief_duplicate_story", 0)),
            "Overlapping contracts or angles create redundant story assignments",
            "Evaluate event-level clustering before drafting while keeping the final batch gate",
            "Lower duplicate draft cost without suppressing distinct stories", priority="high"))
    if counts.get("brief_source_error", 0) >= 2:
        proposals.append(_proposal(
            "brief_source_error", counts["brief_source_error"],
            "Repeated headline index or source transport errors",
            "Replay source queries with bounded failover, timeout and backoff alternatives",
            "Fewer source-error holds with unchanged provenance checks"))
    if counts.get("brief_market_centered_headline", 0) >= 2:
        proposals.append(_proposal(
            "brief_market_centered_headline", counts["brief_market_centered_headline"],
            "Curation headlines overemphasize odds instead of useful real-world developments",
            "Compare editor instructions on a frozen headline dataset with human scoring",
            "Fewer market-centered headlines without increasing causal overstatement"))
    if not release_seen and gates["factcheck"] > 1:
        proposals.append(_proposal(
            "brief_missing_batch_review", gates["factcheck"],
            "This run predates the release editor; its drafts were never batch-compared",
            "Replay the frozen drafts through the cross-article release editor",
            "One unique draft per news peg, with distinct subjects retained"))
    if briefs and not any(b.get("human_factcheck_attested") is True for b in briefs):
        proposals.append(_proposal(
            "brief_human_labels_missing", len(briefs),
            "No attributable human quality labels exist; AI approval is provisional only",
            "Collect reviewer-labeled copy quality, contract relevance and source-support examples",
            "At least 30 labeled cases with measured reviewer agreement"))

    spent = manifest.get("budget") or (briefs[-1].get("model_spending") if briefs else {}) or {}
    # The dashboard explicitly distinguishes observed spending estimates from
    # provider invoices and does not expose arbitrary provider details.
    try:
        spent_usd = round(max(0, float(spent.get("debited_usd", 0))), 6)
    except (ValueError, TypeError):
        spent_usd = 0.0
    attempted_calls = spent.get("attempted_calls")
    if not isinstance(attempted_calls, int) or attempted_calls < 0:
        attempted_calls = sum(c["model_calls"] for c in cases) + (
            1 if release_seen and gates["factcheck"] > 1 else 0)
    return {
        "schema_version": 1, "version": VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "run_label": str(run_label)[:100],
        "summary": {
            "cases": len(briefs), "provisional_drafts": gates["factcheck"],
            "unique_after_release": gates["release"] if release_seen else None,
            "release_editor_executed": release_seen,
            "duplicate_holds": status_counts.get("held_redundant_brief", 0),
            "coverage_attention_triggers": sum(c["trigger"] == "coverage_without_price_movement"
                                               for c in cases),
            "model_calls": attempted_calls,
            "estimated_model_spend_usd": spent_usd,
            "human_reviewed": sum(c["human_reviewed"] for c in cases),
            "process_issue_types": len(counts),
        },
        "dispositions": dict(sorted(status_counts.items())),
        "stage_funnel": [{"label": label, "key": key,
                          "count": (gates[key] if key != "release" or release_seen else None)}
                         for label, key in FUNNEL],
        "issue_counts": counts, "improvement_proposals": proposals,
        "agent_scorecard": _agent_scorecard(briefs, proposals),
        "marketing": _marketing_placeholders(),
        "cases": cases,
        "provenance": {
            "uses_only_existing_private_run_results": True,
            "model_calls_for_oversight": 0,
            "overseer_is_not_article_verifier": True,
            "publication_enabled": False, "automatic_prompt_edits": False,
            "auto_changes_applied": False,
            "ai_factcheck_is_not_human_quality_label": True,
            "model_cost_is_internal_estimate": True,
        },
    }


def load_private_run(directory: str | Path, *, run_label: str = "Private pilot") -> dict:
    """Read bounded local pilot outputs, never fetch remote sources."""
    root = Path(directory)
    if "private" not in root.parts:
        raise ValueError("Overseer input must remain in a private directory")
    files = sorted(root.glob("brief-??.json"))[:100]
    briefs = [json.loads(path.read_text(encoding="utf-8")) for path in files]
    manifest_file = root / "manifest.json"
    manifest = json.loads(manifest_file.read_text(encoding="utf-8")) if manifest_file.exists() else {}
    return analyze_brief_run(briefs, manifest, run_label=run_label)


def _html_rows(rows: list[dict], *, proposals: bool = False) -> str:
    if proposals:
        if not rows:
            return '<p class="empty">No repeated actionable failure found in this sample.</p>'
        return "\n".join(
            f'<article class="ticket"><div class="ticket-top"><span class="badge {"high" if p["priority"] == "high" else "medium"}">{escape(p["priority"])} priority</span>'
            f'<span class="muted">{p["affected_cases"]} cases · owner approval required</span></div>'
            f'<h3>{escape(p["failure_code"].replace("_", " ").title())}</h3>'
            f'<p>{escape(p["root_cause_hypothesis"])}</p>'
            f'<div class="action"><strong>Proposed experiment</strong><div>{escape(p["proposed_experiment"])}</div>'
            f'<div class="muted">Measure: {escape(p["success_metric"])}</div></div></article>'
            for p in rows)
    if not rows:
        return '<tr><td colspan="5" class="empty">No cases in this snapshot.</td></tr>'
    return "\n".join(
        f'<tr><td><strong>{escape(c["market_question"])}</strong><div class="muted">ID {escape(c["case_id"])}</div></td>'
        f'<td>{escape(c["trigger"].replace("_", " "))}</td>'
        f'<td><span class="status">{escape(c["status_label"])}</span></td>'
        f'<td class="number">{c["model_calls"]}</td>'
        f'<td><span class="code">{escape(c["last_gate"])}</span></td></tr>'
        for c in rows)


def _scorecard_rows(rows: list[dict]) -> str:
    if not rows:
        return '<tr><td colspan="4" class="empty">No agent trace available.</td></tr>'
    output = []
    for row in rows:
        reached = int(row["cases_reached"])
        yield_count = row["observed_yield"]
        if yield_count is None:
            result = ('<span class="muted">Not run</span>' if row["stage"] != "process_overseer"
                      else '<span class="muted">Post-run analysis</span>')
            meter = ''
        else:
            passed = int(yield_count)
            result = f'<strong>{passed} / {reached}</strong>'
            meter = (f'<div class="score-track" aria-label="{passed} of {reached} cases met the observed gate">'
                     f'<div class="score-fill" style="width:{round(100 * passed / reached)}%"></div></div>')
        output.append(
            f'<tr><td><strong>{escape(row["name"])}</strong><div class="muted">'
            f'{escape(row["kind"])}</div></td>'
            f'<td class="number">{reached}</td>'
            f'<td><div class="score-result">{result}{meter}</div>'
            f'<div class="muted">{escape(row["observed_yield_label"])}</div></td>'
            f'<td><span class="unrated">—</span><div class="muted">'
            f'{escape(row["quality_status"])}</div></td></tr>')
    return '\n'.join(output)


def _marketing_blocks(marketing: dict) -> str:
    return ''.join(
        '<article class="audience-panel"><h3>' + escape(group["title"]) + '</h3>' +
        ''.join('<div class="audience-item"><span>' + escape(metric["label"]) +
                '</span><strong>' + (escape(str(metric["value"])) if metric["value"] is not None
                                    else '—') + '</strong></div>'
                for metric in group["metrics"]) + '</article>'
        for group in marketing["groups"])


def render_private_dashboard(report: dict, target: str | Path) -> Path:
    """Self-contained HTML review, no JS/CDNs/data fetches or article bodies."""
    dest = Path(target)
    if "private" not in dest.parts:
        raise ValueError("Dashboard must never be written under public site/")
    data = report["summary"]
    maximum = max(1, data["cases"])
    bars = "\n".join(
        f'<div class="funnel-row"><span>{escape(row["label"])}</span>'
        f'<div class="bar-bg"><div class="bar" style="width:{round(100 * (row["count"] or 0) / maximum)}%"></div></div>'
        f'<b>{row["count"] if row["count"] is not None else "—"}</b></div>'
        for row in report["stage_funnel"])
    summary = [
        ("Cases scanned", str(data["cases"]), "Confirmed case records"),
        ("Provisional briefs", str(data["provisional_drafts"]), "Not independently fact-certified"),
        ("Distinct after dedup", str(data["unique_after_release"]) if
         data["unique_after_release"] is not None else "—", "Release desk executed" if
         data["release_editor_executed"] else "No batch editor in this run"),
        ("Internal model cost", f'${data["estimated_model_spend_usd"]:.3f}',
         f'{data["model_calls"]} model calls, not an invoice'),
    ]
    cards = "".join(f'<div class="metric"><div class="label">{escape(k)}</div>'
                    f'<strong>{escape(v)}</strong><small>{escape(note)}</small></div>'
                    for k, v, note in summary)
    outcomes = "".join(f'<span class="result-chip">{escape(STATUS_LABELS.get(k, k))}'
                       f'<b>{int(v)}</b></span>' for k, v in report["dispositions"].items())
    issue_rows = "".join(f'<li><span>{escape(k.replace("_", " "))}</span>'
                         f'<strong>{int(v)}</strong></li>' for k, v in report["issue_counts"].items())
    scorecard = _scorecard_rows(report["agent_scorecard"])
    marketing = report["marketing"]
    audience_panels = _marketing_blocks(marketing)
    html = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light"><title>MarketSignal | Private Process Oversight</title>
<style>
:root{{--ink:#182a31;--muted:#6e7d85;--teal:#0b625c;--line:#dce5e3;--soft:#f4f8f7;--amber:#a15f1c}}
*{{box-sizing:border-box}}body{{margin:0;font:15px/1.55 system-ui,-apple-system,sans-serif;color:var(--ink);background:#fff}}
.wrap{{max-width:1180px;margin:auto;padding:30px 26px 80px}}header{{display:flex;justify-content:space-between;gap:20px;align-items:center;border-bottom:1px solid var(--line);padding-bottom:22px}}
.logo{{font:700 24px Georgia,serif;letter-spacing:-.5px}}.logo span{{color:var(--teal)}}.tag{{font-size:12px;color:var(--teal);background:#e5f5ef;padding:6px 12px;border-radius:18px}}
h1{{font:400 clamp(34px,5vw,52px) Georgia,serif;letter-spacing:-1px;margin:40px 0 8px}}p.lead{{font-size:17px;color:var(--muted);margin:0 0 24px}}h2{{font:400 27px Georgia,serif;margin:0 0 19px}}
.notice{{border-left:3px solid var(--amber);background:#fff8ef;padding:13px 17px;color:#654e33;font-size:13px;margin-bottom:22px}}
.metrics{{display:grid;grid-template-columns:repeat(4,1fr);gap:13px}}.metric{{background:var(--soft);border:1px solid var(--line);border-radius:12px;padding:20px}}
.metric .label{{text-transform:uppercase;font-size:11px;letter-spacing:.6px;color:var(--muted)}}.metric strong{{display:block;font-size:31px;line-height:1.4;font-variant-numeric:tabular-nums}}
.metric small{{display:block;color:var(--muted);font-size:12px}}.split{{display:grid;grid-template-columns:1.4fr 1fr;gap:30px}}section{{margin-top:42px}}
.funnel-row{{display:grid;grid-template-columns:185px 1fr 30px;align-items:center;gap:12px;margin:15px 0;font-size:13px}}
.funnel-row b{{text-align:right;font-variant-numeric:tabular-nums}}.bar-bg{{background:#edf1f0;border-radius:20px;height:13px;overflow:hidden}}.bar{{height:100%;background:var(--teal);border-radius:20px}}
.results{{display:flex;flex-wrap:wrap;gap:9px}}.result-chip{{background:#f1f5f4;border:1px solid var(--line);border-radius:20px;padding:7px 12px;font-size:12px}}.result-chip b{{margin-left:8px}}
.issue-list{{list-style:none;padding:0;margin:0}}.issue-list li{{border-bottom:1px solid var(--line);display:flex;justify-content:space-between;padding:8px 0;font-size:13px}}
.section-note{{color:var(--muted);font-size:13px;margin:-9px 0 17px;max-width:800px}}
.score-table{{min-width:700px}}.score-table td{{vertical-align:middle}}.score-table th:last-child{{min-width:165px}}
.score-result{{display:flex;gap:12px;align-items:center;min-height:22px}}.score-result strong{{font-variant-numeric:tabular-nums;min-width:48px}}
.score-track{{height:6px;flex:1;max-width:150px;background:#e3ece9;border-radius:12px;overflow:hidden}}
.score-fill{{height:100%;background:var(--teal);border-radius:12px}}
.unrated{{font-weight:600;color:#73858a}}.caption-pill{{display:inline-block;margin-left:8px;border-radius:30px;border:1px solid var(--line);padding:2px 9px;font:11px system-ui,sans-serif;color:var(--muted);vertical-align:middle}}
.audience-grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:13px}}.audience-panel{{border:1px solid var(--line);border-radius:12px;padding:20px 22px;background:var(--soft)}}
.audience-panel h3{{font:400 20px Georgia,serif;margin:0 0 10px}}.audience-item{{display:flex;align-items:baseline;justify-content:space-between;gap:18px;border-top:1px solid var(--line);padding:11px 0;font-size:13px}}
.audience-item strong{{font-size:23px;font-weight:400;color:#839397;line-height:1;font-variant-numeric:tabular-nums}}
.ticket-grid{{display:grid;grid-template-columns:repeat(2,1fr);gap:13px}}.ticket{{border:1px solid var(--line);border-radius:10px;padding:19px;background:#fff}}
.ticket h3{{font:400 21px Georgia,serif;margin:8px 0}}.ticket p{{margin:0 0 14px;font-size:13px}}.ticket-top{{display:flex;align-items:center;gap:10px}}
.badge{{border-radius:13px;font-size:11px;padding:3px 9px;text-transform:uppercase;letter-spacing:.2px}}.high{{background:#ffecdc;color:#85450c}}.medium{{background:#e9f2f1;color:#205e57}}
.action{{background:var(--soft);border-radius:7px;padding:12px;font-size:13px}}.action strong{{display:block;margin-bottom:4px}}.action .muted{{margin-top:6px}}
.muted{{color:var(--muted);font-size:12px}}.tablewrap{{overflow:auto}}table{{width:100%;border-collapse:collapse;min-width:720px}}th{{font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.4px;text-align:left;padding:14px 10px}}
td{{border-top:1px solid var(--line);padding:13px 10px;font-size:13px;vertical-align:top}}td strong{{font-weight:600}}.number{{text-align:right;font-variant-numeric:tabular-nums}}.status{{font-size:12px;color:var(--teal)}}.code{{font:11px ui-monospace,monospace;color:#425b61}}
.empty{{color:var(--muted);font-size:13px}}footer{{margin-top:40px;border-top:1px solid var(--line);padding-top:20px;color:var(--muted);font-size:12px;display:flex;justify-content:space-between;gap:20px}}
@media(max-width:850px){{.metrics,.ticket-grid{{grid-template-columns:repeat(2,1fr)}}.split{{grid-template-columns:1fr}}.wrap{{padding:18px}}}}
@media(max-width:650px){{.audience-grid{{grid-template-columns:1fr}}}}
@media(max-width:520px){{.metrics,.ticket-grid{{grid-template-columns:1fr}}.funnel-row{{grid-template-columns:115px 1fr 22px;gap:8px}}}}
</style></head><body><div class="wrap"><header><div class="logo">Market<span>Signal</span><div class="muted">Process integrity · Private oversight</div></div><span class="tag">Read-only snapshot</span></header>
<main><h1>Newsroom process oversight.</h1><p class="lead">{escape(report["run_label"])} · Diagnosing how the pipeline performs, not fact-checking the stories.</p>
<div class="notice"><strong>Private and provisional.</strong> AI fact-check passes are not human verification. Proposed experiments require your approval. No prompt, threshold, article or publication state was changed by the overseer.</div>
<div class="metrics">{cards}</div><div class="split"><section><h2>Stage-gate funnel</h2>{bars}</section>
<section><h2>Outcomes &amp; defects</h2><div class="results">{outcomes}</div><h3>Process signals</h3><ul class="issue-list">{issue_rows}</ul></section></div>
<section><h2>Agent-by-agent scorecard <span class="caption-pill">Operational metrics only</span></h2>
<p class="section-note">Observed yields reflect gate throughput, not writing quality or factual accuracy. An editorial quality score requires labeled human evaluations; holds may be appropriate decisions, not agent mistakes.</p>
<div class="tablewrap"><table class="score-table"><thead><tr><th>Agent / function</th><th class="number">Cases reached</th><th>Observed gate yield</th><th>Human quality grade</th></tr></thead><tbody>{scorecard}</tbody></table></div></section>
<section><h2>Proposed improvement experiments</h2><div class="ticket-grid">{_html_rows(report["improvement_proposals"], proposals=True)}</div></section>
<section><h2>Audience &amp; growth <span class="caption-pill">Future analytics</span></h2>
<p class="section-note">Publication measurement layout only. No analytics integration or readership data is connected; blanks are unknown, not zero. This unpublished pilot cannot be used to infer demand.</p>
<div class="audience-grid">{audience_panels}</div>
<h3>Article performance</h3><div class="tablewrap"><table><thead><tr><th>Published article</th><th>Views</th><th>Headline CTR</th><th>Engaged time</th><th>Shares</th></tr></thead>
<tbody><tr><td colspan="5" class="empty">No article analytics connected. Performance will appear here once publication and measurement are enabled.</td></tr></tbody></table></div></section>
<section><h2>Case-by-case trace</h2><p class="muted">Only status metadata; no article bodies, source URLs or private credentials.</p><div class="tablewrap"><table>
<thead><tr><th>Market question</th><th>Trigger</th><th>Disposition</th><th>Calls</th><th>Last stage</th></tr></thead><tbody>{_html_rows(report["cases"])}</tbody></table></div></section>
</main><footer><span>Process overseer v1 · No automated adjustments · Publication disabled</span><span>Generated {escape(report["generated_at"])}</span></footer></div></body></html>"""
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(html, encoding="utf-8")
    return dest


def render_actions_summary(report: dict) -> str:
    """Safe job summary: aggregate counts only, no article or source metadata."""
    summary = report["summary"]
    lines = ["## MarketSignal · Private Process Overseer", "",
             "> Automated process diagnostics only. No article verified or published.", "",
             "| Metric | Value |", "| --- | ---: |",
             f'| Candidates | {summary["cases"]} |',
             f'| Provisional fact-check passes | {summary["provisional_drafts"]} |',
             f'| Unique after batch release editor | {summary["unique_after_release"] if summary["unique_after_release"] is not None else "Not run"} |',
             f'| Redundant briefs held | {summary["duplicate_holds"]} |',
             f'| Quiet-market attention triggers | {summary["coverage_attention_triggers"]} |',
             f'| Model calls (estimated count) | {summary["model_calls"]} |',
             f'| Internal model cost | ${summary["estimated_model_spend_usd"]:.4f} |',
             f'| Human-reviewed articles | {summary["human_reviewed"]} |',
             "", "### Stage-gate funnel", "",
             "| Gate | Cases |", "| --- | ---: |"]
    lines += [f'| {row["label"]} | {row["count"] if row["count"] is not None else "Not run"} |'
              for row in report["stage_funnel"]]
    lines += ["", "### Owner-review improvement tickets", "",
              f'{len(report["improvement_proposals"])} unapplied proposals in the encrypted artifact.',
              "", "Open `oversight.html` inside the decrypted private artifact for the full report."]
    return "\n".join(lines) + "\n"
