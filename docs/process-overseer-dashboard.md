# MarketSignal — Private Process Overseer and Visibility Dashboard

## Purpose and ownership

The independent overseer owns **process and pipeline improvement**, not
fact-checking an individual paragraph, grading its own output, commissioning a
story or authorizing publication. It operates as a separate, deterministic,
read-only diagnostic pass over recorded stage traces. This is deliberately
distinct from the **Batch Release Editor**, which holds redundant manuscripts.

The first version extends the existing `ProcessOverseer` foundation with
brief-pilot-specific signals and proposals. It does **not** invoke a second
LLM to judge the verifier, train on unvalidated AI grades, edit prompts, adjust
thresholds, spend API tokens, or automatically apply its recommendations.

## Inputs and outputs

Run after the private brief pipeline has completed or partially failed:

```bash
python -m scripts.build_brief_oversight \
  --results-dir data/private/brief-pilot-results \
  --run-label 'Manual unpublished pilot'
```

It reads each `brief-XX.json` plus an optional `manifest.json`, then writes:

| Artifact | Audience | Contains |
| --- | --- | --- |
| `data/private/brief-pilot-results/oversight.json` | Owner/private | Stage counts, case-level metadata, failure signatures, improvement proposals, explicitly qualified model-cost estimate |
| `data/private/brief-pilot-results/oversight.html` | Owner/private | Self-contained read-only browser dashboard with stage funnel, run outcome distribution, issue list, proposal cards and per-case statuses |
| GitHub Actions step summary | Workflow viewer | Aggregate gate counts, model call count and spend only; **no headlines, manuscripts, source URLs, prompts or private credentials** |

Both case-level files enter the existing **encrypted seven-day workflow
artifact**. They are not written to Git history, GitHub Pages, the public
`site/` directory or an external dashboard provider.

The dashboard is a **snapshot**, not a continuously running monitoring service.
No live telemetry, authenticated hosting, historical event store or automated
alerting has been provisioned. Future cross-run comparisons will need a durable
private metric store with owner-approved permissions and retention.

## Measured facts versus provisional judgments

- **Measured:** number of cases and stage transitions, statuses, duplicate
  holds, observed source discovery errors, model calls and internal ledger
  estimate, existence of human review attestations.
- **Diagnostic hypotheses:** a repeated stage failure *may* imply poor queries,
  brittle handoffs, redundant commissioning or prompt overreach. A proposal is
  not a proven root cause.
- **Not measured:** actual factual correctness, reader satisfaction, model
  calibration, causal relevance of headlines, and source independence.
- **Legacy run treatment:** a batch before `brief_release_editor` existed
  displays `—` for unique-after-release, not a falsely reassuring pass count.

## Process experiments and approval

Each ticket includes a stable identifier, observed failure signature, number
of affected cases, hypothesis, bounded proposed experiment, success criterion,
required tests and `owner_approval_required=true`. All tickets remain
`proposed_unapplied`. The pipeline must never weaken source/provenance checks,
silently alter a model instruction, or publish merely because of oversight.

High-priority first-pass diagnostics include:

1. Repeated fact-check holds: retain and replay specific review tickets
   against new writer/research instructions, then measure accuracy and yield.
2. Duplicate events: test early grouping while maintaining the final batch
   release gate; measure both saved draft cost and false suppressions.
3. Repeated market-centered headlines: human-score frozen editor outputs for
   clarity, relevance and causal restraint.
4. Missing human labels: build 30+ reviewed examples before inferring semantic
   article quality from automated checks.

## Safety and test strategy

The GitHub workflow runs offline regression tests before any model spending.
The overseer runs after curation without an API key and before encryption.
Unit tests verify no article body/URL leakage into HTML or Actions summaries,
correct funnel counts, legacy-run handling, owner-approval-only tickets,
duplicate case IDs and private output paths. The existing $2 pilot ledger,
provider-side spending limit and human publication hold remain unchanged.
