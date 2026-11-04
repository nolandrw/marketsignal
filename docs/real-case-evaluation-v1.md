# Real-case newsroom evaluation — preparation and limitations

**Prepared:** 2026-11-04. **State:** zero-cost harness ready; real model/evidence
evaluation **not executed**. No release, trading, paid inference or outreach.

## Why this test-only route exists

The November 3 market archive has one quote per contract and **no historical
baseline**. Its quantitative pitches correctly fail ordinary production entry.
We should not manufacture momentum to make a hand-selected story eligible.

`ResearchTestFixture` is a separate, explicitly named test harness input for
the opt-in `research-v3-shadow` command. It can bypass **only quantitative
entry eligibility**, while keeping the original unmodified `QuantitativePitch`
(including absent history and its reason codes), dated source evidence,
Topic Lead score/gates, Investigator research gates, Contract Gateway, Verifier,
read-only retrieval restrictions and publication-disabled status.

- Production `TopicLeadAgent.assess(context)` **still holds** an ineligible pitch.
- Test entry calls `evaluate_topic_fixture(model, context, fixture)` with a
  matched case/market ID, exact `as_of`, bounded purpose and `test_only_manual_subject` mode.
- An evaluation assessment is marked `evaluation_only` and the model receives
  the actual quantitative ineligibility and test reason. No scheduled collector
  invokes this route. It cannot authorize publishing.
- The same named sources and quotes must exist as real, date-consistent captures.
  URLs, search snippets, or a journalist's manual notes are **not** accepted as
  a substitute for source documents.

## Initial frozen subject set (not agent-selected)

Market IDs and quotes below originate from `data/archive/2026-11-03.json` at
**2026-11-03 08:00 UTC**. For an actual current shadow run, capture a fresh
market snapshot and set the case clock accordingly; never change the timestamp
of the old quote to pretend it is current. The manual preliminary conclusions
are *not* expected model outputs or authoritative truth labels.

| Subject | Market ID | Archived Yes quote | Research question | Manual seed expectation |
|---|---|---:|---|---|
| Strait of Hormuz | `2176270` | 11.0% | Are AIS transit counts and oil-flow estimates measuring comparable traffic? | Investigate metric definitions, hold any unsupported numerical comparison |
| Anthropic / SpaceX IPO | `1321561` | 66.5% | What comparable valuation measure could determine the largest 2026 IPO? | Investigate SEC documents, reject unpriced private-valuation extrapolation |
| December Fed hike | `3215008` | 72.5% | Can borrower/deposit pass-through be calculated beyond already-covered Fed reporting? | Investigate original data path, hold duplicate generic Fed recap |
| Government alien confirmation | `703257` | 3.7% | Is there an authenticated official finding, as opposed to an unverified UAP claim? | Spike unsupported alien-confirmation thesis; possible separate records angle |

### Source leads that require actual capture and provenance

These are public pointers verified through source discovery, **not completed
source packets**. Capture attempts must obey host permissions, robots, date,
size and copyright constraints. A failed route is logged as a coverage gap.

- Hormuz: [MARAD Advisory 2026-011](https://www.maritime.dot.gov/msci/2026-011-persian-gulf-strait-hormuz-and-gulf-oman-iranian-attacks-commercial-vessels),
  [IMF PortWatch dataset](https://portwatch.imf.org/datasets/3da2b9ca97684916b75c4013f95d18ab_0/about),
  and independently dated cargo series. Do not compare unlike units.
- IPO: [Anthropic SEC S-1/A filing index](https://www.sec.gov/Archives/edgar/data/2130357/000162828026068676/0001628280-26-068676-index.html)
  (November 2, 2026),
  [SpaceX final prospectus](https://www.sec.gov/Archives/edgar/data/1181412/000162828026042639/spaceexplorationtechnologi.htm),
  and the exact market resolution rule. The Anthropic filing is large and needs
  bounded, rights-compliant full-document parsing, not a snippet-only claim.
- Fed: [October 28 FOMC statement](https://www.federalreserve.gov/newsevents/pressreleases/monetary20261028a.htm),
  [BLS CPI release](https://www.bls.gov/news.release/archives/cpi_10142026.htm),
  and dated consumer-rate series. Direct capture of the FOMC page returned
  an HTTP error under the current read-only bot transport; it remains a HOLD.
- UAP: [NASA UAP FAQ](https://science.nasa.gov/uap/faqs/),
  [AARO report index](https://www.aaro.mil/Congressional-Press-Products/),
  and any authenticated new committee/agency statement.

## Executable route once source packets and credentials exist

Keep all files under `data/private/`:

```bash
python -m marketsignal research-v3-shadow \
  --context-file data/private/case-topic-context.json \
  --captures-file data/private/case-captures.json \
  --policy-file data/private/research-policy.json \
  --angle-id selected-angle-id \
  --test-fixture-file data/private/case-test-fixture.json \
  --max-model-spend-usd 2.00 \
  --model-budget-db data/private/model-budget.sqlite \
  --out data/private/case-shadow-result.json
```

The `$2.00` ceiling above is an **example, not an approved expenditure**.
An explicit approved ceiling and an API key are required before any live run.
Use the **same ledger file and ceiling for all four cases**; the limit is
persistent across separate CLI invocations and is not reset for each case.
`--max-model-spend-usd` is mandatory. Reservations are debited *before* network
calls based on a conservative estimate of the bounded request and output; only
a complete provider usage record can reduce a reservation. Failed calls and
missing usage retain their full reserved charge. Exhaustion stops before HTTP.
The private SQLite ledger is not a general provider billing cap, so apply an
independent OpenAI project-level limit before live use. This opt-in safeguard
currently applies to `research-v3-shadow`, not every legacy model CLI.

The no-key, no-cost estimate command is:

```bash
python -m marketsignal model-budget-estimate --cases 4
```

A fresh, actual four-market Gamma snapshot and partial, date-attributed
government source packets can be generated locally with
`python -m scripts.prepare_pilot_evidence`. These are not substituted into
the November 3 frozen quotes; each new case keeps its actual observation
time and the genuine missing historical baselines. The producer leaves
coverage assessment and permissioned reporting incomplete, so a failed
pilot preflight is the intended outcome until those gaps are addressed.

The illustrative five calls per case × 10,000 input and 2,400 output tokens
per call produce **$0.146** of model charges at the `gpt-5-mini` rate card
checked November 4, 2026 ($0.25 per million input; $2.00 per million output;
$0.025 per million cached input tokens). Actual call counts, outputs, retries,
and provider fees may differ; the shared preflight ledger intentionally
reserves more than the point estimate. The price card must be rechecked
before execution.

The fixture JSON must contain exactly `case_id`, `market_id`, `as_of`,
`purpose`, `mode: "test_only_manual_subject"`, and
`publication_enabled: false`. Its IDs and clock must match the topic context.
Omit `--test-fixture-file` for ordinary production-like triage testing.

## Test protocol and acceptance evidence

1. Freeze fresh market quote, case `as_of`, original source capture timestamps,
   source content hashes, origin groups, and coverage-search window.
2. Run the ordinary quantitative route on genuine movement-triggered cases,
   and the explicitly labeled fixture route on the four manually chosen cases.
3. Run real structured Topic Lead and Investigator v3 stages only with a model
   credential and a **preapproved bounded call/spend budget**. Preserve failed
   calls, held cases and all structured artifacts.
4. Contract Gateway checks lineage; the independent provisional Verifier checks
   each material claim's meaning. A valid citation ID is not semantic support.
5. A blinded human editor independently assesses novelty, factual accuracy,
   incompatible metrics, disconfirmation, reader utility and overconfident
   assertions. Preserve negatives and false negatives.
6. Process Overseer clusters failures across distinct cases and proposes
   **unapplied** versioned changes. Freeze control/held-out replay sets before
   tuning any rubric thresholds. No independent 90/100 claim from four cases.

## Current blockers (not silently resolved)

- No model API key is configured in the present runtime; no paid/model stages
  were executed in this preparation phase.
- No complete, dated, permissioned original-source capture packet has been
  assembled for these four cases. The official Fed direct capture failed under
  the earlier HTML gateway; no bypass was attempted. The expanded multi-format
  ingestion path has offline tests, but still requires a fresh live source
  readiness probe and dated original packets for the four cases.
- The newest Investigator v3 dossier still needs a faithful mapping to the
  downstream Writer; the fictional replay uses an older feature fixture.
- Missing historical price points prevent real movement-triggered selection
  from the November 3 archive. New snapshots can start a forward history; they
  do not retrospectively fill the gap.

**Result today:** a reproducible **test-only entry mechanism**, not a tested
autonomous newsroom. The next empirical milestone is at least one actual
model-executed case with original captures and an independent human label.
