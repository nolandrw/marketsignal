# MarketSignal — Autonomous Market Intelligence

**Status: $0 daily GitHub Actions / Pages site is deployed; a bounded public-source
Narrative Scout, Evidence Investigator, editorial workflow and measured
synthetic shadow evaluation are implemented. AI-authored news and paid cloud
hosting are NOT activated.**

MarketSignal is a portfolio-oriented, auditable pipeline for detecting meaningful
changes in prediction-market contracts. It is designed to become a bounded
multi-stage newsroom, with documented quality gates, a public track record,
and minimal ongoing maintenance.

The collector deliberately makes **no AI calls** and **no publication decisions**.
It uses the public read-only Polymarket Gamma API, SQLite for local tests or
optional PostgreSQL for durable data, deterministic thresholds, and an
inspectable local HTML report.

## Quick start (Python 3.11+, no third-party packages)

From this directory:

```bash
python -m unittest discover -s tests -v
python -m marketsignal demo
python -m marketsignal collect --max-markets 150 --max-pages 8
python -m marketsignal report
python -m marketsignal daily --archive-dir data/archive --out site/index.html
python -m marketsignal editorial-demo
python -m marketsignal evaluate-agents --cases 120
python -m marketsignal source-smoke --archive-dir data/archive
python -m marketsignal investigate-archive --archive-file data/archive/2026-11-03.json
```

The `daily` command collects one real snapshot per UTC date, writes an
immutable JSON archive and renders a static report. The first day normally
has no movement signals because it establishes the baseline. It needs no
database service, model API key, paid account or Python dependency.

PostgreSQL support is optional (`python -m pip install '.[postgres]'`). Set
`DATABASE_URL` to use it; production additionally sets
`REQUIRE_PERSISTENT_DB=1`. The `init-db` schema migration is a separate
privileged step, not part of routine collection.

Open `demo/index.html` to see synthetic, clearly labeled signal scenarios.
Open `reports/index.html` for your real stored market observations.

The first live run saves observations but ordinarily produces **no signals**:
the engine requires a past 1-hour or 24-hour baseline. Repeat `collect` after
at least an hour and then at regular intervals to accumulate market history.

Collection is append-only per 15-minute bucket and safe to retry. Existing
observations never change on a retry. A failure is recorded in the `runs`
table and returns a nonzero exit status. Signals have a 6-hour duplicate
suppression window per market.

## What's implemented

- Current Gamma `/events/keyset` discovery with stable cursor pagination.
- Active binary Yes/No market normalization, category and data-quality filters.
- Initial watchlist ranked by 24-hour trading volume, bounded by API pages.
- Immutable, timestamped local market snapshots and run audit records.
- Deterministic 1-hour and 24-hour price-delta detection.
- Liquidity and volume gates, simple transparent prioritization score.
- Duplicate suppression, unit tests, CI, and a static read-only dashboard.
- A synthetic demo to verify movements without implying they happened.
- An idempotent daily pipeline with Git-tracked JSON snapshots, replayable
  movement detection, a static website payload and a scheduled GitHub workflow.
- Typed editorial-agent stages with independent numeric/citation verification,
  conservative HOLD decisions, an offline synthetic replay and no publication access.
- Read-only, bounded Polymarket history / Bluesky / GDELT discovery adapters,
  conservative narrative handoffs, an Evidence Investigator that refuses to
  certify discovery-only rumors, and automatic shadow metrics that never
  appear on the public site.
- Optional PostgreSQL storage with one-time schema setup, 30-day retention
  (preserving signal evidence), stale-run recovery and a CLI health probe.
- Non-root container image, explicit Secret Manager integration and opt-in
  Google Cloud deployment/scheduler scripts (not executed or provisioned).

## What's NOT implemented

- A provisioned hosted database or paging alerts.
- Backfilled history, orderbook spread validation, or statistical calibration.
- Actual model-powered research/writing, independent full-text verification,
  human-rated real-world editorial evaluation and article publication. Source
  **discovery** exists, but discovery is not fact-checking.
- Cross-market clustering, professional licensing review, or fully unattended operation.

The first CI live-source probe confirmed Polymarket history was accessible,
but unauthenticated Bluesky search returned **HTTP 403** and GDELT discovery
returned no usable response. Those adapters are best-effort and currently
**degraded**; successful fake-source tests are not evidence of live coverage.
The system will hold unsupported story claims rather than scrape around a
provider's denied access or invent a catalyst.

These omissions are intentional. The next milestone requires a **real seven-day
scheduled-collector trial**, historical price backfill, an evaluation dataset,
and model-powered, independently verified shadow research/writing. No public
auto-publishing until quality gates have been demonstrated.

## Data and editorial integrity

The stored quote `yes_price` is the Gamma API's `outcomePrices` entry for the
contract's **Yes** outcome. It is **not** asserted to be a perfect probability,
and it is not a bid/ask midpoint. Change is expressed in **percentage points**.
These trading prices do not prove an event happened or explain a causal reason.

Current thresholds (hypotheses, not calibrated statistical significance):

| Gate | Setting |
| --- | --- |
| Market volume in past 24h | >= $50,000 |
| Liquidity | >= $25,000 |
| 1-hour move | >= 8 percentage points |
| 24-hour move | >= 15 percentage points |
| Duplicate market signal cooldown | 6 hours |

The watchlist is a bounded sample of high-activity events, not all Polymarket
markets. Sports, crypto, entertainment, and weather are omitted from the
general-interest scope when the feed provides identifying metadata. This is
not a fully exhaustive category classifier.

## Architecture

```text
Gamma API -> normalized Yes/No markets -> immutable SQLite/PostgreSQL snapshots
          -> deterministic 1h/24h detector -> auditable signals
          -> read-only HTML operations report
```

The implemented **shadow newsroom** connects downstream of archived signals:

```text
archived signal -> quantitative triage -> narrative scout (optional public leads)
  -> evidence investigator (discovery ≠ verification)
  -> permissioned movement-only writer -> verifier -> editor (hold/shadow)
  -> sanitized private CI artifact
```

The public publisher is deliberately disconnected; only the independently
scheduled data-only dashboard is deployed. The next research phase needs
authorized reliable source access, real-content fact checking and real-world
human-rated evaluations before an autonomous narrative publisher is safe.

See [agent instructions](docs/agent-instructions-v1.md),
[agent evaluation](docs/agent-evaluation.md),
[agent workflow](docs/agents.md), [architecture](docs/architecture.md),
[quality gates](docs/quality-gates.md),
[security boundaries](SECURITY.md), the [free daily runbook](docs/free-poc.md)
and [paid-cloud deployment runbook](docs/deployment.md).

## Low-cost operational strategy

1. **Free daily pilot:** GitHub Actions runs once each morning, saving dated
   public JSON archives to the repo and producing a GitHub Pages-ready report.
   Hosting is optional until configured in repo settings.
2. **Scheduled shadow service:** once the pilot justifies it, initialize hosted
   Postgres, run the collector every 15 minutes, and add a freshness alert.
3. **Bounded agents:** investigate only qualified signals; enforce token and
   search budgets; record provenance and reject unsupported claims.
4. **Unattended website:** only permit low-risk, fully checked pieces to
   publish after repeatable replay tests and a shadow evaluation period.

SQLite remains local/in-memory only in the free daily workflow. Its **JSON
archive is committed to Git**, preserving the observed history between
ephemeral GitHub Actions runners. Never rely on runner-local SQLite files as
durable storage. The CI workflow runs tests and the separate `Daily
MarketSignal` workflow handles scheduled data collection.

### Deployment remains opt-in

The checked-in `Dockerfile` and `scripts/deploy_gcp.sh` create no resources
until explicitly run with an approval environment variable. The deployment
script intentionally does **not** activate Cloud Scheduler; that is a second,
explicitly approved step using `scripts/enable_schedule_gcp.sh`. See the
[runbook](docs/deployment.md) for the database bootstrap, worker role and
permissions, secrets, cost controls and operational verification.

## API and license considerations

- [Polymarket event keyset API](https://docs.polymarket.com/api-reference/events/list-events-keyset-pagination)
- [Polymarket historical prices](https://docs.polymarket.com/api-reference/markets/get-prices-history)
- [Polymarket data terms](https://polymarket.com/tos)

Public API access does not automatically grant unrestricted commercial data
redistribution. Review terms before any revenue-generating or institutional
data offering.

## Portfolio story

Show the evolution from deterministic ingestion to statistical detection,
then a source-grounded multi-agent publishing workflow. Publish tests,
operational reliability, model-evaluation methodology, accuracy/correction
metrics, and measured cost per accepted article. Never display illustrative
dashboard metrics as actual operating performance.
