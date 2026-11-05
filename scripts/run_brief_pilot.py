"""Manually approved, unpublished, bounded market-curation brief experiment.

This uses actual successive Gamma archive observations and RSS headline
metadata. Unlike the four-case investigator pilot, it makes no claim to have
captured original reporting, resolved why odds changed, or certified facts.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

from marketsignal.brief_pilot import (
    MAX_CASES, MAX_ATTENTION_STORIES, run_brief, select_movers,
    select_quiet_candidates, probe_quiet_attention, review_release_redundancy,
)
from marketsignal.model_budget import ModelBudget
from marketsignal.model_gateway import ResponsesJSONModel
from marketsignal.news_rss import RSSNewsSearch


LIMIT_USD = "2.00"
ARCHIVE_DIR = Path("data/archive")
RESULTS = Path("data/private/brief-pilot-results")
LEDGER = Path("data/private/brief-pilot-budget.sqlite")


def latest_pair() -> tuple[Path, Path]:
    records = sorted(ARCHIVE_DIR.glob("????-??-??.json"))
    if len(records) < 2:
        raise ValueError("Two real archived observations are required")
    earlier, latest = records[-2:]
    payload = json.loads(latest.read_text(encoding="utf-8"))
    observed = payload["observed_at"]
    if not isinstance(observed, int) or not 0 <= time.time() - observed <= 72 * 3600:
        raise ValueError("Latest comparison is too stale for a live brief")
    return earlier, latest


def run(*, maximum: int, min_delta_pp: float) -> dict:
    earlier, latest = latest_pair()
    movements = select_movers(earlier, latest, maximum=maximum,
                              threshold_pp=min_delta_pp)
    if not os.environ.get("OPENAI_API_KEY"):
        raise ValueError("A dedicated API key is required")
    budget = ModelBudget(LEDGER, LIMIT_USD)
    model = ResponsesJSONModel("gpt-5-mini", budget=budget)
    # CI showed GDELT HTTP 429 from GitHub Actions, while Google and Bing RSS
    # responded with parseable feeds. RSS is metadata-only, never body text.
    search = RSSNewsSearch(timeout=7)
    # A quiet market with unusually broad public attention can also be worth a
    # short brief. These probes are bounded and *do not* consume model tokens.
    attention_cap = min(MAX_ATTENTION_STORIES, maximum // 4)
    quiet = select_quiet_candidates(
        earlier, latest,
        excluded_events={(m.market.venue, m.market.event_id) for m in movements},
        threshold_pp=min_delta_pp)
    attention = probe_quiet_attention(quiet, search, maximum=attention_cap)
    # Reserve slots only for probes that actually qualify. Existing movement
    # selection still fills all remaining capacity.
    candidates = list(movements[:maximum - len(attention)]) + list(attention)
    if not candidates:
        raise ValueError("No genuine movement or qualified coverage-attention contrast")
    RESULTS.mkdir(parents=True, exist_ok=True)
    counts: dict[str, int] = {}
    inventory = []
    results = [run_brief(movement, model, search) for movement in candidates]
    review_release_redundancy(results, model)
    for index, (movement, result) in enumerate(zip(candidates, results), start=1):
        result["model_spending"] = budget.summary()
        target = RESULTS / f"brief-{index:02d}.json"
        target.write_text(json.dumps(result, indent=2), encoding="utf-8")
        counts[result["status"]] = counts.get(result["status"], 0) + 1
        # Logs contain only IDs, gates, counts and provider expense. No article
        # text, publisher lead URLs, API keys, prompts, or source material.
        safe = {"market_id": movement.market.market_id,
                "change_pp": movement.delta_pp,
                "trigger": movement.trigger,
                "status": result["status"],
                "model_calls": result["model_calls"],
                "stage_trace": [{"stage": row["stage"], "status": row["status"],
                                 "leads": row.get("leads"),
                                 "issues": row.get("issues", [])}
                                for row in result["stage_trace"]],
                "model_spend_usd": budget.summary()["debited_usd"]}
        print(json.dumps(safe))
        inventory.append({"market_id": movement.market.market_id,
                          "result_file": str(target), "status": result["status"]})
    report = {"status": "unpublished_market_curation_pilot",
              "cases": len(candidates), "dispositions": counts,
              "movement_triggers": len(candidates) - len(attention),
              "coverage_attention_triggers": len(attention),
              "attention_probe_candidates": len(quiet),
              "source_depth": "market_quote_plus_discovery_headlines_only",
              "publication_enabled": False,
              "human_factcheck_attested": False,
              "budget": budget.summary(), "inventory": inventory}
    (RESULTS / "manifest.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "inventory"}))
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Private lightweight market-curation pilot")
    parser.add_argument("--max-cases", type=int, default=MAX_CASES)
    parser.add_argument("--min-delta-pp", type=float, default=1.0)
    args = parser.parse_args()
    try:
        run(maximum=args.max_cases, min_delta_pp=args.min_delta_pp)
        return 0
    except (OSError, ValueError, RuntimeError, TypeError, KeyError) as exc:
        print(json.dumps({"pilot": "held", "reason": type(exc).__name__,
                          "publication_enabled": False}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
