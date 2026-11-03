"""Command-line entrypoints for collection, replayable demo, and inspection."""

from __future__ import annotations

import argparse
import json
import sys
import time
import os
from dataclasses import replace
from pathlib import Path

from .dashboard import render_dashboard
from .daily import run_daily
from .detection import detect_signals
from .agent_evals import evaluate_shadow
from .agent_sources import BlueskySearch, GDELTSearch, PolymarketHistory, PublicJSONTransport
from .editorial import Candidate, EditorialPipeline
from .feature_demo import demo_feature
from .field_trial import audit_case, load_case, render_shadow
from .feature_demo import fictional_feature_fixture
from .feature_story import FeatureNewsroom, assign_reporting_from_archive
from .context_discovery import discover_archive as discover_context_archive
from .gamma import GammaError, discover_markets
from .investigation import NarrativeScout
from .models import Market, Signal
from .newsroom import replay_archive, safe_report
from .postgres import PostgresStorage, open_storage
from .source_smoke import probe_sources
from .storage import Storage
from .quantitative import pitches_from_archive
from .historical import backfill_prices
from .kalshi import KalshiDiscovery
from .agent_sources import PolymarketComments
from .learning import load_human_labels, train_challenger
from .newsroom_control import (
    StoryLedger, StoryState, TopicRubric, WorkflowController,
    accept_structural_dossier, story_id,
)
from .oversight import OversightAgent, SyntheticAudiencePanel, grade_agents


def collect(db_file: str, max_markets: int, max_pages: int,
            retention_days: int = 30) -> int:
    started_at = int(time.time())
    with open_storage(db_file) as store:
        recovered = store.recover_stale_runs(started_at)
        run_id = store.start_run(started_at)
        try:
            markets, events_scanned = discover_markets(max_markets=max_markets, max_pages=max_pages)
            if not markets:
                raise GammaError("No markets matched the watchlist; keeping previous observations unchanged")
            inserted = store.save_snapshots(markets, started_at)
            new_signals = detect_signals(store, markets, started_at)
            # Perform retention cleanup at most once per UTC day. Signal-linked
            # before/after quotes are retained as an audit trail.
            day = str(started_at // 86400)
            expired = 0
            if store.get_metadata("last_retention_day") != day:
                expired = store.prune_snapshots(started_at - retention_days * 86400)
                store.set_metadata("last_retention_day", day)
            store.set_metadata("dataset", "live")
            store.finish_run(run_id, int(time.time()), status="ok", events=events_scanned,
                             markets=inserted, signals=len(new_signals))
            print(json.dumps({"status": "ok", "events_scanned": events_scanned,
                              "eligible_markets": len(markets), "new_snapshots": inserted,
                              "new_signals": len(new_signals), "expired_snapshots": expired,
                              "recovered_runs": recovered,
                              "backend": "postgres" if os.environ.get("DATABASE_URL") else "sqlite"}, indent=2))
            return 0
        except Exception as exc:
            # Untrusted network/database exceptions can echo secrets or URLs.
            # Store the error class, not an arbitrary third-party message.
            summary = type(exc).__name__
            store.finish_run(run_id, int(time.time()), status="error", error=summary)
            print(f"Collection failed safely ({summary})", file=sys.stderr)
            return 1


def demo(db_file: str, report_file: str) -> int:
    """Create a synthetic replay for layout and detector verification only."""
    current = Storage.bucket(int(time.time()))
    basis = [
        ("demo-1", "Federal Reserve cuts rates at the next meeting?", 0.42, 0.57, 1_200_000, 320_000),
        ("demo-2", "Major AI regulation passes before year-end?", 0.33, 0.21, 750_000, 185_000),
        ("demo-3", "New international climate agreement signed?", 0.52, 0.54, 185_000, 95_000),
        ("demo-4", "National infrastructure bill passes?", 0.14, 0.31, 600_000, 280_000),
    ]
    with Storage(db_file) as store:
        run_id = store.start_run(current, source="synthetic-demo")
        past: list[Market] = []
        present: list[Market] = []
        for market_id, question, before, after, volume, liquidity in basis:
            market = Market(market_id, market_id, "Synthetic demonstration event", "demo-only",
                            question, "123456789", before, volume, liquidity, "")
            past.append(market)
            present.append(replace(market, yes_price=after))
        store.save_snapshots(past, current - 86400)
        store.save_snapshots(past, current - 3600)
        inserted = store.save_snapshots(present, current)
        signals = detect_signals(store, present, current)
        store.set_metadata("dataset", "demo")
        store.finish_run(run_id, current, status="ok", events=4, markets=inserted, signals=len(signals))
        total_signals = store.dashboard_data()["stats"]["signals"]
        rendered = render_dashboard(store, report_file)
    print(json.dumps({"status": "demo", "synthetic_signals_visible": total_signals,
                      "new_signals": len(signals),
                      "database": db_file, "dashboard": str(rendered)}, indent=2))
    return 0


def editorial_demo() -> int:
    """Run a synthetic end-to-end editorial shadow pass without APIs or writes."""
    now = Storage.bucket(int(time.time()))
    market = Market(
        market_id="synthetic-editorial-1", event_id="synthetic-event-1",
        event_title="Fictional launch demonstration", event_slug="synthetic-example",
        question="Will the fictional Atlas rocket launch by year-end?",
        yes_token_id="synthetic-token", yes_price=0.54,
        volume_24h=640_000, liquidity=210_000, end_date="",
    )
    signal = Signal(
        market_id=market.market_id, observed_at=now, baseline_at=now - 86400,
        window_hours=24, previous_price=0.35, current_price=0.54,
        change_pp=19.0, score=83, volume_24h=640_000, liquidity=210_000,
    )
    # Risk classification is supplied only to illustrate a low-risk example;
    # real markets default to unknown and require editorial review.
    packet = EditorialPipeline().run(Candidate(market, signal, risk="low"))
    print(json.dumps({"synthetic": True, "publication_enabled": False,
                      "editorial_result": packet.to_dict()}, indent=2))
    return 0 if packet.status == "shadow_ready" else 1


def newsroom_v3_demo() -> dict:
    """Exercise every handoff with fictional evidence; stop at release gate."""
    candidate, dossier = fictional_feature_fixture()
    story = StoryState(story_id(candidate.market.market_id, candidate.signal.observed_at),
                       candidate.market.market_id, candidate.signal.observed_at,
                       quantitative_score=candidate.signal.score)
    rubric = TopicRubric(5, 4, 4, 4, 4, 3,
                         source_ids=tuple(doc.source_id for doc in dossier.documents))
    story.topic_score = rubric.score
    with StoryLedger(":memory:") as ledger:
        def move(target: str, reason: str, agent: str) -> None:
            WorkflowController.advance(story, target, reason=reason)
            ledger.record(story, agent, reason)

        ledger.record(story, "quantitative_triage", "synthetic_candidate")
        for stage in ("triaged", "topic_review", "investigating", "verifying"):
            move(stage, "fictional_workflow_test", "workflow_controller")
        structural_issues = accept_structural_dossier(story, candidate, dossier)
        if structural_issues:
            raise AssertionError("Fictional dossier no longer satisfies structural gate")
        move("chief_editor", "structural_checks_passed", "verifier")
        story.editorial_assignment_ready = True
        move("drafting", "length_and_angle_assigned", "chief_editor")
        generated = FeatureNewsroom().run(candidate, dossier)
        if generated.status != "shadow_draft_ready" or not generated.article:
            raise AssertionError("Fictional writer or verifier regression")
        move("editorial_review", "fictional_draft_ready", "writer")
        story.editorial_review_passed = not generated.issue_codes
        move("copy_editing", "structural_editor_acceptance", "chief_editor")
        story.copy_review_passed = bool(generated.article.source_urls and
                                        generated.article.headline == dossier.proposed_headline)
        move("audience_review", "fictional_citation_layout", "copy_editor")
        # The panel is explicitly a readability/provenance heuristic, not
        # simulated people with meaningful taste or newsroom judgment.
        draft = generated.article
        audience = SyntheticAudiencePanel().examine(
            draft.headline, " ".join(p.text for p in draft.paragraphs),
            sum(bool(p.source_ids) or p.role == "market_context" for p in draft.paragraphs),
            len(draft.paragraphs))
        story.audience_review_recorded = True
        move("release_review", "audience_diagnostic_recorded", "audience_panel")
        # Structural provenance is not independent semantic fact checking;
        # real release cannot advance to owner approval on this evidence.
        move("held", "semantic_factcheck_not_available", "release_editor")
        result = {"synthetic": True, "state": story.to_dict(),
                  "topic_score": rubric.score, "owner_approval_required": True,
                  "publication_enabled": False, "audit_chain_valid": ledger.verify_chain(story.story_id),
                  "audit_handoffs": [entry["state"] for entry in ledger.events(story.story_id)],
                  "fictional_article": {"headline": draft.headline,
                                        "word_count": draft.approximate_word_count,
                                        "paragraph_count": len(draft.paragraphs),
                                        "source_count": len(dossier.documents),
                                        "semantic_factcheck_passed": False},
                  "audience_panel": audience,
                  "oversight": [p.to_dict() for p in OversightAgent().assess(ledger.metrics())]}
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Auditable Polymarket movement monitoring")
    commands = parser.add_subparsers(dest="command", required=True)
    ingest = commands.add_parser("collect", help="Fetch current markets and append observations")
    ingest.add_argument("--db", default="data/marketsignal.db")
    ingest.add_argument("--max-markets", type=int, default=150)
    ingest.add_argument("--max-pages", type=int, default=8)
    ingest.add_argument("--retention-days", type=int, default=30)
    dashboard = commands.add_parser("report", help="Generate a read-only HTML operations dashboard")
    dashboard.add_argument("--db", default="data/marketsignal.db")
    dashboard.add_argument("--out", default="reports/index.html")
    health = commands.add_parser("health", help="Fail if the collector is stale or unsuccessful")
    health.add_argument("--db", default="data/marketsignal.db")
    health.add_argument("--max-age-minutes", type=int, default=35)
    daily = commands.add_parser("daily", help="One daily snapshot and static briefing, no paid services")
    daily.add_argument("--archive-dir", default="data/archive")
    daily.add_argument("--out", default="site/index.html")
    daily.add_argument("--max-markets", type=int, default=150)
    daily.add_argument("--max-pages", type=int, default=8)
    commands.add_parser("init-db", help="Initialize PostgreSQL schema with a privileged migration account")
    simulate = commands.add_parser("demo", help="Generate a clearly labeled synthetic detector demo")
    simulate.add_argument("--db", default="demo/demo.db")
    simulate.add_argument("--out", default="demo/index.html")
    commands.add_parser("editorial-demo", help="Replay a synthetic agent workflow without API calls")
    commands.add_parser("feature-demo", help="Evidence-backed fictional newspaper article shadow test")
    investigate = commands.add_parser(
        "investigate-archive", help="Shadow-only bounded source research for archived signals"
    )
    investigate.add_argument("--archive-file", required=True)
    investigate.add_argument("--max-candidates", type=int, default=3)
    assignments = commands.add_parser(
        "assign-context", help="Generate structured newspaper reporting briefs from archived signals"
    )
    assignments.add_argument("--archive-file", required=True)
    assignments.add_argument("--max-candidates", type=int, default=3)
    context = commands.add_parser(
        "discover-context", help="Read-only background and prior reporting discovery (shadow only)"
    )
    context.add_argument("--archive-file", required=True)
    context.add_argument("--max-candidates", type=int, default=2)
    evaluate = commands.add_parser(
        "evaluate-agents", help="Run deterministic synthetic agent process/result rubrics"
    )
    evaluate.add_argument("--cases", type=int, default=120)
    smoke = commands.add_parser(
        "source-smoke", help="Public-source connectivity, sanitized counts only"
    )
    smoke.add_argument("--archive-dir", default="data/archive")
    pitches = commands.add_parser("quantitative-report", help="Read-only 1h/1d/7d/30d story pitches")
    pitches.add_argument("--archive-file", required=True)
    pitches.add_argument("--top", type=int, default=20)
    historical = commands.add_parser("backfill-history", help="Bounded public Polymarket history (manual)")
    historical.add_argument("--archive-file", required=True)
    historical.add_argument("--out-dir", default="data/history")
    historical.add_argument("--max-markets", type=int, default=3)
    historical.add_argument("--days", type=int, default=30)
    kalshi = commands.add_parser("kalshi-sample", help="Read-only Kalshi adapter smoke probe")
    kalshi.add_argument("--max-pages", type=int, default=1)
    comments = commands.add_parser("comment-pulse", help="Unverified Polymarket comment activity only")
    comments.add_argument("--archive-file", required=True)
    comments.add_argument("--max-events", type=int, default=2)
    commands.add_parser("newsroom-v3-demo", help="Synthetic bounded workflow; no release")
    field = commands.add_parser("field-trial", help="Audit a real-topic curated evidence case and render a held shadow article")
    field.add_argument("--case", required=True)
    field.add_argument("--out", default="reports/field-trial.md")
    train = commands.add_parser("train-ranker", help="Train inactive ML challenger on verified human labels")
    train.add_argument("--labels", required=True)
    train.add_argument("--model-out", default="data/private/news-ranker-challenger.json")
    ledger = commands.add_parser("newsroom-audit", help="Summarize private quality ledger")
    ledger.add_argument("--db", default="data/private/story-ledger.db")
    arguments = parser.parse_args(argv)
    if arguments.command == "quantitative-report":
        if not 1 <= arguments.top <= 100:
            parser.error("--top must be 1..100")
        selected = pitches_from_archive(arguments.archive_file)[:arguments.top]
        print(json.dumps({"shadow_only": True, "pitches": [p.to_dict() for p in selected]}, indent=2))
        return 0
    if arguments.command == "backfill-history":
        print(json.dumps(backfill_prices(arguments.archive_file, arguments.out_dir,
                                         max_markets=arguments.max_markets,
                                         lookback_days=arguments.days), indent=2))
        return 0
    if arguments.command == "kalshi-sample":
        samples = KalshiDiscovery(PublicJSONTransport()).sample(max_pages=arguments.max_pages)
        print(json.dumps({"venue": "kalshi", "status": "experimental_discovery_only",
                          "quote_count": len(samples), "market_volume_unit": "contracts",
                          "merged_into_daily_scoring": False}, indent=2))
        return 0
    if arguments.command == "comment-pulse":
        if not 1 <= arguments.max_events <= 3:
            parser.error("--max-events must be 1..3")
        record = json.loads(Path(arguments.archive_file).read_text(encoding="utf-8"))
        seen = set()
        client = PolymarketComments(PublicJSONTransport())
        pulses = []
        for raw in record.get("markets", []):
            market = Market(**raw)
            if market.event_id in seen or market.venue != "polymarket":
                continue
            seen.add(market.event_id)
            pulse = client.pulse(market.event_id, market.event_slug, int(record["observed_at"]))
            pulses.append({"event_id": pulse.event_id, "recent_comments_24h": pulse.recent_comments_24h,
                           "unique_commenters": pulse.distinct_recent_accounts,
                           "unverified_leads": len(pulse.theory_leads),
                           "evidence_grade": pulse.evidence_grade})
            if len(pulses) >= arguments.max_events:
                break
        print(json.dumps({"shadow_only": True, "pulses": pulses}, indent=2))
        return 0
    if arguments.command == "newsroom-v3-demo":
        print(json.dumps(newsroom_v3_demo(), indent=2))
        return 0
    if arguments.command == "field-trial":
        case = load_case(arguments.case)
        audit = audit_case(case)
        if audit["score"] != 100:
            print(json.dumps({"status": "structural_hold", "audit": audit}, indent=2))
            return 1
        output = Path(arguments.out)
        if output.suffix.lower() != ".md" or any(
                component in {"site", "archive", "docs"} for component in output.parts):
            parser.error("Shadow article output must be a private Markdown preview, not site/archive/docs")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(render_shadow(case), encoding="utf-8")
        print(json.dumps({"status": "shadow_hold", "path": str(output),
                          "structural_audit": audit, "independent_factcheck": False,
                          "publication_enabled": False}, indent=2))
        return 0
    if arguments.command == "train-ranker":
        model = train_challenger(load_human_labels(arguments.labels))
        if "site" in Path(arguments.model_out).parts or "archive" in Path(arguments.model_out).parts:
            parser.error("Do not publish training artifacts in the website or market archive")
        model.save(arguments.model_out)
        print(json.dumps({"status": "challenger_only", "metrics": model.holdout_metrics,
                          "training_examples": model.training_examples,
                          "model_file": arguments.model_out}, indent=2))
        return 0
    if arguments.command == "newsroom-audit":
        if not Path(arguments.db).exists():
            print(json.dumps({"status": "no_private_ledger_yet", "grades": {}}, indent=2))
            return 0
        with StoryLedger(arguments.db) as audit:
            metrics = audit.metrics()
            print(json.dumps({"metrics": metrics, "grades": grade_agents(metrics),
                              "oversight": [p.to_dict() for p in OversightAgent().assess(metrics)]}, indent=2))
        return 0
    if arguments.command == "collect":
        if not 1 <= arguments.max_markets <= 1000 or not 1 <= arguments.max_pages <= 100:
            parser.error("--max-markets must be 1..1000 and --max-pages 1..100")
        if not 1 <= arguments.retention_days <= 365:
            parser.error("--retention-days must be 1..365")
        return collect(arguments.db, arguments.max_markets, arguments.max_pages,
                       arguments.retention_days)
    if arguments.command == "demo":
        return demo(arguments.db, arguments.out)
    if arguments.command == "editorial-demo":
        return editorial_demo()
    if arguments.command == "feature-demo":
        output = demo_feature()
        print(json.dumps(output, indent=2))
        return 0 if output.get("article") and not output["review"]["structural_provenance_issues"] else 1
    if arguments.command == "evaluate-agents":
        result = evaluate_shadow(arguments.cases)
        print(json.dumps(result, indent=2))
        return 0 if result["passes_offline_thresholds"] else 1
    if arguments.command == "source-smoke":
        print(json.dumps(probe_sources(arguments.archive_dir), indent=2))
        return 0
    if arguments.command == "investigate-archive":
        transport = PublicJSONTransport(timeout=8, retries=1)
        slow_news_transport = PublicJSONTransport(timeout=20, retries=0)
        scout = NarrativeScout(PolymarketHistory(transport),
                               BlueskySearch(transport), GDELTSearch(slow_news_transport))
        results = replay_archive(arguments.archive_file, scout,
                                 max_candidates=arguments.max_candidates)
        print(json.dumps(safe_report(results), indent=2))
        return 0
    if arguments.command == "assign-context":
        print(json.dumps(assign_reporting_from_archive(
            arguments.archive_file, max_candidates=arguments.max_candidates
        ), indent=2))
        return 0
    if arguments.command == "discover-context":
        news = GDELTSearch(PublicJSONTransport(timeout=20, retries=0))
        print(json.dumps(discover_context_archive(
            arguments.archive_file, news, max_candidates=arguments.max_candidates
        ), indent=2))
        return 0
    if arguments.command == "daily":
        if not 1 <= arguments.max_markets <= 1000 or not 1 <= arguments.max_pages <= 100:
            parser.error("--max-markets must be 1..1000 and --max-pages 1..100")
        result = run_daily(arguments.archive_dir, arguments.out,
                           max_markets=arguments.max_markets, max_pages=arguments.max_pages)
        print(json.dumps(result, indent=2))
        return 0
    if arguments.command == "init-db":
        url = os.environ.get("DATABASE_URL")
        if not url:
            parser.error("init-db requires DATABASE_URL (privileged migration credential)")
        with PostgresStorage(url, initialize=True):
            pass
        print("PostgreSQL schema initialized (run with restricted role for collection)")
        return 0
    if arguments.command == "health":
        with open_storage(arguments.db) as store:
            runs = store.dashboard_data()["runs"]
        last = runs[0] if runs else None
        age = (int(time.time()) - last["started_at"]) if last else None
        healthy = last is not None and last["status"] == "ok" and age is not None and age <= arguments.max_age_minutes * 60
        print(json.dumps({"healthy": healthy, "last_run_status": last["status"] if last else None,
                          "age_seconds": age}))
        return 0 if healthy else 1
    with open_storage(arguments.db) as store:
        output = render_dashboard(store, arguments.out)
    print(f"Dashboard generated: {output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
