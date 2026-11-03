# Architecture decision record — 001

**Decision date:** 2026-11-02  
**Owner:** Nolan Watson  
**Current phase:** Free daily proof of concept / optional paid-cloud upgrade

## Goal

A low-maintenance, public portfolio artifact demonstrating AI engineering
(roughly 60%) and data science (roughly 40%). The publication is a visible
consequence of a measurable, well-guarded autonomous operating process.

## Constraints

- Minimal recurring expense; no paid accounts or schedules provisioned.
- Structured, explainable and replayable decisions.
- External text is untrusted and cannot trigger publication or credential use.
- Numeric market values are never invented by language models.
- Automated publication, when enabled, must be opt-in, bounded and reversible.
- High-risk narratives and unexplained moves are held or discarded.
- The website can remain static and be regenerated when approved stories change.

## Current implementation

- Single-process Python with no third-party local dependency; optional `psycopg`
  adds PostgreSQL support in the production container.
- Current Gamma keyset API instead of deprecated offset listing.
- Schema-normalized Yes/No market quotes with stringent missing-value rules.
- SQLite or PostgreSQL append-only snapshots, one per market per 15-minute bucket.
- Threshold detector: 1h / 24h, liquidity and volume filters, cooldown.
- Audit records for successful and failed collection runs.
- Static HTML report, synthetic replay and CI unit tests.
- PostgreSQL schema bootstrap isolated from restricted runtime credentials,
  retention preserving signal evidence, stale-run recovery and health checks.
- Non-root container, optional Cloud Run deployment script and separately
  activated Cloud Scheduler script; **none have been deployed**.
- Free GitHub Actions daily workflow with versioned JSON records, an in-memory
  SQLite replay and a static, data-only market briefing. The first live
  deployment succeeded on 2026-11-03 (800 events scanned, 92 markets observed).
- Offline editorial-agent interfaces, a shadow pipeline, structured claims,
  conservative risk holds and synthetic verification cases. See [agents.md](agents.md).
- Bounded public-source adapters (Polymarket intraday history, Bluesky,
  GDELT), independent investigation handoff, versioned agent instructions and
  a synthetic quality-gated shadow run. Model inference and publication remain
  disabled.

## Planned production architecture

1. Provision hosted PostgreSQL with a restricted runtime role and actual backups.
2. Schedule the Python container with retries, backfill, external data freshness
   monitoring, and alerting after a manual trial. No assumption that a GitHub
   Actions cron runs on time.
3. Historical price retrieval and quantitative baseline calibration.
4. Source-citation evidence store with URLs, timestamps and retrieval hashes.
5. Activate bounded agent adapters with versioned prompts and structured
   outputs, using the already implemented offline shadow pipeline.
6. Code-based verification of numeric claims and URLs, plus independent
   model-based checking of material factual claims.
7. A publication state machine with idempotent operations and a kill switch.
8. Site exposing current and archived signals, approved article sources,
   corrections, provenance and operational metrics.

### Proposed publication policy

- Data-only observations may publish after deterministic checks pass.
- Explanatory articles remain drafts until objective evaluation thresholds
  and a shadow trial pass; then only low-risk classes can auto-publish.
- Conflicts, public-health, elections, allegations, and high-consequence
  unsupported claims require escalation, or are simply not published.
- Newsletter delivery is out of initial scope; avoid irrevocable broadcasts.

## Known limitations of current detector

- Outcome price can differ from bid/ask midpoint and an inferred probability.
- No spread or orderbook quality measure is yet collected.
- Market discovery ranks high-volume events; the sample is not exhaustive.
- Category classification is metadata dependent and imperfect.
- A single 1h/24h threshold is not a validated anomaly score.
- Market expirations and resolution complications require broader testing.
- The simplistic scoring function is intentionally not labeled statistically
  significant and should be calibrated before editorial use.

## Next acceptance criteria

- 7 days of scheduled snapshots with >99% recovery-adjusted collection coverage.
- Baseline backfill tested with API snapshots and stored historical prices.
- Golden cases cover bad data, missing baselines, thin markets and false signals.
- Provenance for every value in one candidate editorial report.
- No model can publish without passing deterministic policy checks.
