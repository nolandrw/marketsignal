# Four-case paid research pilot — guarded operating procedure

**Status (November 4, 2026):** owner approved **up to $2 total** for the
four-story shadow evaluation. This is not a standing subscription, per-run
allowance or approval to publish. No key or complete source bundles are
currently present; **no paid call has executed**.

## Security and spend prerequisites

1. In the [OpenAI API platform](https://platform.openai.com/), create a
   dedicated MarketSignal experiment project and a project-scoped API key.
   Set a **$2 monthly spend limit with “Enforce a hard limit” enabled**.
   A mere alert is insufficient. Provider enforcement is not instantaneous,
   so there can be a small overrun; the separate conservative in-process
   reservation ledger is another defense.
2. In GitHub repository settings, create the `research-pilot` Actions
   environment, restrict deployments to a reviewed branch, and ideally
   require manual approval. Add three **environment secrets**:
   `OPENAI_API_KEY`, `MARKETSIGNAL_PILOT_BUNDLE_B64`, and
   `MARKETSIGNAL_PILOT_RESULTS_PASSPHRASE` (a strong independent passphrase
   retained outside GitHub for decrypting the result artifact).
3. Only the manual `workflow_dispatch` action
   `.github/workflows/research-pilot.yml` uses the credential. Normal CI,
   scheduled collection, the public dashboard and PR events do **not** read
   it. The workflow has read-only repository permissions, no publication
   permissions, concurrency control, and no raw research artifact uploads.

**GitHub Actions workflows are available for manual dispatch only once the
workflow file exists on the default branch.** The implementation is in a
draft PR; do not merge until it has been reviewed. A secret cannot be
created or populated by this project code.

## Private source-input preparation

The four frozen subjects are **Hormuz, IPO, Fed, and UAP**. These are
test-only nominations; MarketSignal's production Topic Lead still requires
real quantitative eligibility. The test fixture may bypass only that
particular eligibility gate.

Every case requires a current/frozen `TopicLeadContext` with actual market
terms and prior-coverage review, the exact matching `ResearchTestFixture`,
real dated source captures with provenance, and an explicit rights/host
policy. Search snippets are not substitute evidence. Sources published after
the case's `as_of` timestamp must be excluded; a fresh quote and source
window are necessary for current news. Absent history remains absent.

For a private execution environment, place these input files under
`data/private/` (gitignored). Use
[`examples/research-pilot-manifest.example.json`](../examples/research-pilot-manifest.example.json)
as the **shape**, then save a completed manifest to
`data/private/pilot-manifest.json`. Its four `angle_id: "auto:first"`
entries mean the test proceeds with the first *actual* Topic Lead proposed
angle, never a made-up human-predicted model ID. It cannot be used in
production-like entry without the test fixture.

After all inputs pass the offline preflight:

```bash
python -m scripts.run_research_pilot pack
```

This creates the private `data/private/pilot-bundle.b64`, a bounded
base64-encoded compressed bundle of **only the explicitly referenced JSON
inputs**. Base64 is *not encryption*: store it only as an encrypted GitHub
Actions secret, never in the repository or logs. GitHub secrets have a
48-KB limit; the packer rejects oversized bundles.

Use GitHub's encrypted-secret setup UI (or a suitable private CLI session)
to set `MARKETSIGNAL_PILOT_BUNDLE_B64` to the bundle file's contents.
Do not paste the key, passphrase or bundle into a chat, issue, PR or CI log.

## One manually approved execution

1. Confirm the dedicated API project's enforced hard limit is **$2** and
   its key is limited to that project.
2. Manually dispatch **Four-case research pilot** in GitHub Actions and
   affirm the required hard-limit checkbox. This is **not** triggered by
   pushes, PRs or schedules.
3. The runner checks for all three secrets, runs offline unit tests, unpacks
   and validates *all four* private cases before making any paid call.
4. It runs the cases sequentially through `research-v3-shadow`, reusing
   `data/private/pilot-model-budget.sqlite` and a **shared $2 application
   ceiling**. A case error halts later calls; each actual model result remains
   publication-disabled.
5. Full results and the spending ledger are encrypted using the independent
   passphrase before a seven-day GitHub Actions artifact is uploaded. Nothing
   posts to a newsroom, website, social channel or trading venue.
6. Download `marketsignal-research-pilot-encrypted` and decrypt locally with
   GPG (the passphrase set in step 2 under Security). Preserve original
   outputs and independent human quality labels before any iteration.

**Important per-run boundary:** GitHub-hosted runners are ephemeral.
The SQLite ledger persists across the *four cases within one run*, not
across a manual rerun on a new runner. Never dispatch a second run without
reviewing the first run's artifact and remaining actual provider budget.
The dedicated project's enforced hard $2 limit is the cross-run backstop.
Neither the provider limit nor the ledger can mathematically guarantee the
final provider invoice never exceeds $2 due delayed metering.

## Readiness blockers

- Nolan reported configuring the GitHub environment/API key on November 4.
  This runtime cannot inspect or retrieve the secret, and no paid job has
  been dispatched. The local development process still has no API key.
- There are **zero complete, permissioned four-case source packages** in
  `data/private/` here. Official document URLs already identified in
  [real-case evaluation preparation](real-case-evaluation-v1.md) are source
  leads, not captured documents. The conservative Fed source gateway
  previously returned an HTTP error. No workaround was attempted.
- The [previous HTML-only GitHub CI source-shape probe (run 137)](https://github.com/nolandrw/marketsignal/actions/runs/41923807475)
  found **0 of 5 official leads fully capturable under the old gateway**,
  even on a GitHub-hosted runner. This is a historical result, **not a retest
  of the expanded multi-format gateway**:

  | Lead | Observed outcome | Proper next step |
  |---|---|---|
  | Hormuz / MARAD advisory | HTTPError | Investigate allowed official feeds or alternative first-party records |
  | IPO / SEC filing index | Index retrieved, but no dated primary article-body structure | Find specific dated filings or official EDGAR structured feeds; validate document-level provenance |
  | Fed / FOMC statement | HTTPError | Explore official release feeds/PDFs under publisher permissions |
  | UAP / AARO report index | HTTPError | Identify supported original report formats and rights-compliant ingestion |
  | UAP / NASA FAQ | Exceeded old 240-KB HTML ceiling | Retest 2MB bounded official HTML extraction and date metadata |

  This probe saved only host-level diagnostics, never source text. Robots or
  publisher access denial remains a HOLD, not a reason to change user agents,
  bypass rate limits or treat web snippets as authenticated captures. The
  expanded gateway now supports bounded PDF/JSON/CSV/XML/TSV/text and first-party
  dates, document hashes and excerpt locations with offline regression tests.
  The updated CI shape probe results are recorded below. PDF OCR and blocked
  publisher access remain separate challenges.
- **Expanded gateway re-test:** [CI run 141](https://github.com/nolandrw/marketsignal/actions/runs/41927205114)
  passed all automated checks. The hosted no-model probe found **1/5 source
  leads potentially capturable**: NASA FAQ. SEC index still lacked usable
  publication metadata; MARAD, Fed and AARO returned HTTP errors from that
  runner. A separate local no-model run retrieved both NASA and MARAD, and
  each produced a dated, three-excerpt `ArticleCapture` with a full SHA-256.
  Thus, retrieval availability varies by network; neither result is permission
  to circumvent a blocked site. These two individual captures are **not**
  complete four-case evidence packets and have not undergone semantic review.
- The manual workflow is a draft PR change and is not yet on the default
  branch; nothing can be dispatched through that workflow until reviewed
  and merged.

Do not claim the pilot was run or its research was verified until the
actual encrypted results, source provenance and independent human review
exist. The earlier illustrative model estimate remains **$0.146** for
20 calls at 10,000 input/2,400 output tokens, not a guaranteed invoice.
