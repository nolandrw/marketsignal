# The $0 daily proof of concept

**Scope:** one daily Polymarket snapshot, deterministic movement detection,
an auditable archive and a public, static, data-only briefing. This runs on
GitHub Actions and GitHub Pages; there is no paid cloud service, database,
wallet, LLM API call or newsletter subscription.

## How it works

1. At 7:17 a.m. America/Los_Angeles, GitHub Actions runs the Python tests,
   fetches the public Gamma market sample and writes `data/archive/YYYY-MM-DD.json`.
2. The runner reconstructs recent SQLite state **in memory** from those JSON
   records. No SQLite database file is committed to Git.
3. The existing detector identifies movements passing the daily threshold:
   at least 15 percentage points, $50k 24h volume and $25k liquidity.
   Missing days are tolerated. Every signal records the actual elapsed hours.
4. A static, escaped HTML report is written to `site/index.html`, with
   machine-readable `site/latest.json` beside it.
5. The built-in GitHub workflow identity commits the new date and report to
   the public repository. No personal access token is necessary.
6. If Pages is enabled, the same workflow uploads and deploys the site.

The first run establishes a baseline; signals ordinarily begin on the next
day. A rerun on the same UTC date uses the existing record and avoids fetching
new observations. Failed fetches do not produce an empty archive.

## One-time activation

The workflow is committed with a daily schedule and a manual run option.
Collection is ready to run without any API credentials. To publish the
website, perform these two GitHub settings steps:

1. In **Settings → Pages → Build and deployment → Source**, select
   **GitHub Actions**.
2. In **Settings → Secrets and variables → Actions → Variables**, add a
   repository variable `MARKETSIGNAL_PAGES_ENABLED` set to `true`.

Then open **Actions → Daily MarketSignal → Run workflow** to collect the first
real observation. The default site URL will be
`https://nolandrw.github.io/marketsignal/` after a successful Pages deployment.
Do not represent the URL as live until the GitHub deployment confirms it.

To stop daily automation, disable the workflow in the Actions tab. To keep
collecting but stop public-site deployments, set the repository variable to
`false`.

## Local reproducibility

```bash
python -m unittest discover -s tests -v
python -m marketsignal daily --archive-dir data/archive --out site/index.html
```

The second command fetches real public data. Without an existing archive,
it creates a baseline and should not invent movements.

## Costs, reliability and limitations

- **Expected operating expense:** $0 using standard runners on a public repo
  and default GitHub Pages hosting. External paid services are not configured.
- **Scheduled execution is best-effort:** GitHub may delay or skip jobs, and
  inactive public repositories can have cron workflows disabled after 60 days.
- **Git repository is a small-scale data store, not a production database:**
  records accumulate by date and remain immutable. Revisit size after 6–12
  months or if coverage expands substantially.
- **Daily comparisons:** this is not live news or a full statistical anomaly
  model. Overnight repricing may have occurred at any time between samples;
  actual elapsed intervals are disclosed.
- **Data rights:** public API access is not a license for unrestricted
  commercial republication. Review Polymarket's terms before monetization.
- **No causality claims:** market outcome prices are not guarantees of event
  probability, and price movements do not independently verify an event.
- **No AI-authored articles:** this avoids paid inference and hallucinated
  explanations in the first public release. Agent research/writing remains a
  separate, gated milestone.

## Upgrade path without throwing away work

The JSON archive has a versioned schema (`schema_version: 1`) with the same
`Market` and `Signal` fields used by PostgreSQL. An upgrade can ingest these
records into hosted PostgreSQL, move the collector from daily Actions to
Cloud Run every 15 minutes, add historical and orderbook features, and insert
bounded research / writer / verifier agents **downstream** of the detector.
The website can still be generated statically from validated output.

For the paid deployment design, see [deployment.md](deployment.md) and
[architecture.md](architecture.md).
