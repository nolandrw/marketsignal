# Lightweight MarketSignal Briefs — experimental, unpublished

## Editorial decision

MarketSignal is a **filter of current events prompted by changing market quotes**.
It can also surface an intriguing mismatch: broad, recent public coverage of an
active topic while its corresponding prediction contract barely changes.
An existing news story can be valuable to a reader because the market helps them
discover or prioritize it. **Originality is not a commissioning requirement**.
This new, deliberately lower-bar lane complements rather than replaces the
deep-research Investigator and the long-form feature workflow.

An interesting subject and a sufficiently relevant dated external headline can
justify a short *curation brief*. They do **not** justify an assertion that a
reported event occurred, that the market predicted it, or that the event caused
the market quote to move.

## Source and stage rules

| Stage | What's required | Why a case can still hold |
| --- | --- | --- |
| Genuine signal (two entry paths) | **Movement:** same contract in two immutable adjacent archives (within 48h), at least 1.0 percentage-point change, $50k 24h volume and $25k liquidity. **Coverage attention:** same-contract change *under* 1.0 point, the same liquidity floors, plus a bounded news-index probe showing at least six recent distinct dated headlines from at least four publishers, with either a three-headline increase over the preceding 48h sample or at least nine recent leads | Unmatched contracts, stale quotes, insufficient publisher diversity, weak/repetitive coverage |
| Scout | One or two bounded searches for *reporting on the topic* | No meaningful discoverable reader question |
| Coverage discovery | At least one dated HTTPS publisher headline from Google News RSS, with Bing News RSS fallback | Connector error or no relevant indexed coverage |
| Curation editor | Reader usefulness >=50/100; an intelligible connection and a truthful, non-platform headline; up to four real source IDs | Irrelevance, no substance, deceptive or dubious title |
| Writer | 120–450 words, 3–6 paragraphs, valid market and external references | Unsupported details, missing citations, malformed structure |
| Brief fact check | Independent model review of each paragraph against exactly the dated quote and the indexed title text; one revision allowed | Misrepresentation, spurious causal inference, numerical errors |
| **Batch release editor (new)** | Compare all completed briefs across markets by real-world news peg and reader takeaway. One model comparison per batch, plus a deterministic rule that complementary contracts in the same event cannot both be considered unique | Overlapping stories are retained as drafts but moved to `held_redundant_brief`; an unavailable or malformed batch decision holds the queue for manual comparison |
| Release | **Always private pending human review** | All AI-checked drafts remain unpublished |

The **independent process overseer** remains a separate retrospective role:
it examines recurring gate failures, missed triggers, drift and pipeline
efficiency. It is **not** an extra article-factchecking or release gate. The
batch release editor owns story-level deduplication.
After each manually approved pilot, this read-only overseer creates an encrypted
private HTML/dashboard JSON report plus a **public-safe aggregate GitHub Actions
job summary**. No overseer change is applied without owner approval. See the
[private overseer runbook](process-overseer-dashboard.md).

### Coverage-attention signal: an intentionally modest proxy

The early quantitative scout probes at most eight high-activity, nearly
unchanged *events* per run (one representative contract per event), and
reserves up to three of twelve story slots only when coverage attention
actually qualifies. It compares two adjacent 48-hour samples from the
fixed-host news RSS index, using dated headlines, distinct links and distinct
publishers. The index returns only a **ranked, capped sample**, not a census of
articles, search volume, press mentions or social chatter. Do not report the
sample counts as exhaustive news volume, statistically validated media spikes,
or proof that traders ignored an event. The scout and editor still must
establish that the *specific headlines actually concern the specific contract*.

This is a low-cost exploratory trigger, not a live attention model. A fuller
production signal would need stored hourly/daily per-topic coverage time series,
entity resolution and source-family deduplication before claiming a measurable
coverage anomaly. Cases may also merit a future separate
"coverage is surprisingly low despite price movement" track; neither trigger
presumes an event occurred or forecasts are calibrated.

The external source material in this pilot is **only news-index title
metadata and a link**, not the full article text. That is deliberately labeled
in each private result. The article must attribute anything about external
events to the relevant publisher and must not embellish the publisher's title.
These briefs are useful prototypes for a news-filter product, **not verified
original journalism**. Publication requires an editor to open and read the
linked original reporting, independently confirm material claims and review
licensing and style before releasing anything.

## Pilot bounds and workflow

- Manual GitHub Action: `Lightweight MarketSignal briefs (manual, unpublished)`.
- Automatically selects **up to 12** real cases from the latest two committed
  daily archives, including up to three qualified stable-market/coverage-attention
  cases; retains the 72-hour live-data freshness requirement.
- Dedicated `gpt-5-mini` Responses API inference, up to six calls per market,
  a local $2.00 spending ledger, and an independently configured provider-side
  $2 hard limit required by the manual dispatch form.
- Tests run before spending; no automated publication, syndication, mailing,
  paid ads, or changes to the live collector.
- The late batch editor adds at most one more model call when two or more
  drafts reach the provisional queue. Its disposition and duplicate reference
  are retained in each private result, never shown in public workflow logs.
- Private drafts, publisher headline leads and the ledger are archived only
  in an AES-256-encrypted GitHub Actions artifact with seven-day retention.
  Workflow logs expose market identifiers, scores, gate statuses and spending,
  **never article text or source leads**.
- The original, more demanding investigative pilot is unchanged and remains an
  option for stories that justify deeper research.

**First live result (2026-11-04):** 12/12 cases held at coverage discovery;
provider health diagnostics identified GDELT HTTP 429. A subsequent cost-free
GitHub Actions probe confirmed Google News RSS and Bing News RSS connectivity.
The curation lane now uses those indexes, with dated publisher attribution
and the same provisional-review restrictions. The earlier no-coverage result
is not evidence that the news subjects lacked coverage.

## What to evaluate after the run

Review the shortlist for **reader usefulness**, clarity of connection, and
whether an ordinary reader would have learned something from the filtered
coverage. Also record headline-level overreach, duplicate subjects, excessive
hedging, and any broken references. None of the automated gates independently
verify external events, and these outputs are not ready for public distribution.
