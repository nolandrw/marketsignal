# MarketSignal — Autonomous Market Intelligence

**Status: $0 daily GitHub Actions / Pages site is deployed; a bounded public-source
Narrative Scout, Evidence Investigator, editorial workflow and measured
synthetic shadow evaluation are implemented. AI-authored news and paid cloud
hosting are NOT activated.**

**Editorial product direction:** MarketSignal aims to be a general-interest
newspaper informed by prediction-market leads, **not** a site of odds-movement
headlines. Its offline `feature-demo` now illustrates a wider reporting
assignment, a cited evidence dossier, a context-first article and an
editor-chosen word budget. See the [v2 newspaper standard](docs/editorial-standard-v2.md).

**Newsroom v3 foundations:** multi-horizon quantitative pitches, optional
bounded historical backfill, an experimental isolated Kalshi adapter, an
explicit bounded editorial state machine, claim review contracts, fictional
end-to-end shadow rehearsal, an eight-persona structural diagnostic panel,
private audit/oversight, and a human-label-only offline ML challenger. No
model-generated reporting, semantic fact-checking or live-article publication
has been activated. See the [v3 newsroom blueprint](docs/newsroom-v3.md).

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
python -m marketsignal feature-demo
python -m marketsignal assign-context --archive-file data/archive/2026-11-03.json
python -m marketsignal discover-context --archive-file data/archive/2026-11-03.json
python -m marketsignal evaluate-agents --cases 120
python -m marketsignal source-smoke --archive-dir data/archive
python -m marketsignal investigate-archive --archive-file data/archive/2026-11-03.json
python -m marketsignal newsroom-v3-demo
python -m marketsignal field-trial --case data/private/your_research_case.json --out reports/field-trial.md
python -m marketsignal quantitative-report --archive-file data/archive/2026-11-03.json
# Optional manual, bounded source checks and history capture:
python -m marketsignal kalshi-sample --max-pages 1
python -m marketsignal comment-pulse --archive-file data/archive/2026-11-03.json --max-events 1
python -m marketsignal backfill-history --archive-file data/archive/2026-11-03.json --max-markets 3 --days 30
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
- Active binary Yes/No market normalization and data-quality filters; all
  market topic categories can now be considered, including sports and crypto.
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
- A separate newspaper-feature workflow with an eight-question contextual
  assignment, provenance-checked source documents, exact-matched quotations,
  earlier expectations, societal stakes, attributed alternative explanations,
  editor-determined length, paragraph citation IDs and an independent shadow
  verification gate. The CLI demonstration is deliberately fictional.
- Multi-horizon 1h/24h/7d/30d observation-based ranking from local archives,
  category-specific uncalibrated fallbacks, missing-data abstention, optional
  manual price-history backfill, and a data-only `site/pitches.json` output.
- Optional isolated public Kalshi quote discovery and exceptionally low-trust
  Polymarket discussion signals; neither is silently added as verified factual
  reporting nor merged into incompatible Polymarket trading volume units.
- Versioned newsroom controller with explicit research/editorial return limits,
  claim/dossier provenance contracts, manual-owner release gate, private
  tamper-evident SQLite audit events, eight structural panel perspectives, and
  change proposals with carefully bounded automatic operational authority.
- A fixed-feature, standard-library logistic challenger trained only after
  independently human-labeled historical editorial outcomes; time-ordered
  holdout and explicit nonactivation are required. No training labels exist yet.
- A private evidence-linked **real-topic field trial** on Texas's November 2026
  Senate race: a re-commissioned newspaper-style shadow draft, competing
  investigative story theses, a source-linked chief-editor angle selection,
  unresolved reporting questions and eleven structural checks. Its first
  turnout-uncertainty angle was spiked for inadequate narrative payoff.
  The trial **does not** invent market movement, establish original reporting,
  or certify semantic truth; the real article body is held outside public Git
  and never included in the public site. A fictional fixture runs in CI. See
  [field trial](docs/field-trial.md) and [story thesis gate](docs/story-thesis-v1.md).
- Bounded historical-context discovery across prior, recent and broader
  reporting windows (GDELT metadata only), triggered in daily shadow runs
  and recorded as sanitized counts, with no claim that a news hit is verified.
- Optional PostgreSQL storage with one-time schema setup, 30-day retention
  (preserving signal evidence), stale-run recovery and a CLI health probe.
- Non-root container image, explicit Secret Manager integration and opt-in
  Google Cloud deployment/scheduler scripts (not executed or provisioned).

## What's NOT implemented

- A provisioned hosted database or paging alerts.
- Automatically scheduled backfilled history, orderbook spread validation, or
  validated statistical significance / topic-level threshold calibration.
- Actual model-powered research/writing, independent full-text verification,
  human-rated real-world editorial evaluation and article publication. Source
  **discovery** exists, but discovery is not fact-checking.
- Automatic primary-source/full-text collection across subjects, real-world
  context packets, professional semantic review and unattended newspaper
  articles. The local feature demo's data is synthetic, not live reporting.
- Cross-market clustering, professional licensing review, or fully unattended operation.

CI live-source probes confirmed Polymarket history (49 observations) and,
after increasing the bounded GDELT timeout to 20 seconds, GDELT article
discovery (one article lead). Unauthenticated Bluesky search still returns
**HTTP 403**, so social discovery is currently **degraded**. One successful
news query is not evidence of sustained reliability or verified reporting.
The system holds unsupported story claims rather than scrape around a
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
markets. Sports, crypto, entertainment, and weather are now eligible, though
category parsing and balanced coverage have not been externally validated.
The existing 15pp 24-hour detector remains separate from v3's category-aware
8pp default **pitch** gate. Neither is statistically calibrated.

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

The **newspaper feature path** applies additional research/evidence gates:

```text
signal -> context reporting assignment -> documented background/quotes/stakes
       -> source/digest/quote checks -> editor chooses depth
       -> newspaper writer -> paragraph/evidence verifier -> shadow draft
       -> human semantic review required before any publishing
```

See [agent instructions](docs/agent-instructions-v1.md),
[agent evaluation](docs/agent-evaluation.md),
[v3 newsroom operating manual](docs/newsroom-v3.md),
[newspaper editorial standard](docs/editorial-standard-v2.md),
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
