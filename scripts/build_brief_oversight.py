"""Read-only post-run process diagnostics, private HTML, and safe Actions summary.

This command never needs credentials, model calls or publication access.
The case-level dashboard remains inside the encrypted pilot artifact.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from marketsignal.brief_overseer import (
    load_private_run, render_actions_summary, render_private_dashboard,
)


def run(results_dir: Path, *, run_label: str) -> dict:
    report = load_private_run(results_dir, run_label=run_label)
    results_dir.mkdir(parents=True, exist_ok=True)
    (results_dir / "oversight.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    render_private_dashboard(report, results_dir / "oversight.html")
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        # This summary contains *only aggregate telemetry* and fixed phrases.
        with open(summary_path, "a", encoding="utf-8") as handle:
            handle.write(render_actions_summary(report))
    print(json.dumps({"overseer": "complete", "cases": report["summary"]["cases"],
                      "proposal_count": len(report["improvement_proposals"]),
                      "private_dashboard": "included_in_encrypted_artifact",
                      "automatic_changes": False, "publication_enabled": False}))
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Private MarketSignal process oversight")
    parser.add_argument("--results-dir", type=Path,
                        default=Path("data/private/brief-pilot-results"))
    parser.add_argument("--run-label", default="MarketSignal manual brief pilot")
    args = parser.parse_args()
    try:
        run(args.results_dir, run_label=args.run_label)
    except (OSError, ValueError, KeyError, TypeError, RuntimeError):
        print(json.dumps({"overseer": "held", "reason": "diagnostic_input_error",
                          "publication_enabled": False}))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
