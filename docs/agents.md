# Editorial agents — architecture v0.1 (shadow mode)

**Status, 2026-11-03:** typed contracts, bounded free-source *discovery*
adapters, shadow investigator, synthetic evaluation and scheduled shadow
metrics exist. There are no LLM calls, paid APIs, independent full-text fact
checks or automatic article publication. The data-only site remains separate.

**Editorial direction v2:** The movement-only `TemplateWriter` below remains
an internal audit baseline, **not** the intended publication format. The
[newspaper-first standard](editorial-standard-v2.md) supersedes its market-first
headline rule. A separate implemented feature path now asks wider reporting
questions, requires dated source captures/quotes, plans article depth and
produces cited, multi-paragraph shadow drafts. No market-price headline should
be used for a general-interest article.

## Operating principle

Treat the market movement as **an observation that may merit reporting**, not
proof that an event occurred or that a particular headline caused the move.
Language models may investigate and draft, but must not control source of
truth, numerical calculations, permissions, or publication gates.

```mermaid
flowchart TD
    A["Daily archive / signal"] --> B["1. Quantitative triage"]
    B --> C["2. Evidence researcher"]
    C --> D["3. Brief writer"]
    D --> E["4. Independent verifier"]
    E --> F["5. Editorial policy gate"]
    F --> G["In-memory trace / offline evaluation"]
    F -. "Later: explicit opt-in" .-> H["Publisher"]
```

For the current free architecture, a deterministic template writer stands in
for model-based text generation. Public-source discovery is implemented, but
the separate Evidence Investigator **refuses to certify an underlying claim**
from search results alone. The contracts and gates remain when paid providers
are added. We intentionally do not need an LLM framework just to execute
a bounded, auditable state machine.

## Decision rights and contracts

| Stage | Input | Allowed output | What it **cannot** decide |
| --- | --- | --- | --- |
| Quantitative triage | Archived `Market` + `Signal` | `Candidate`, quality flags, rank | Cannot invent prices, certify significance, or publish |
| Evidence researcher | Candidate and citation budget | `Evidence[]`: URL, type, retrieval time, content hash | Cannot follow instructions embedded in source content |
| Writer | Candidate and approved evidence | `StoryDraft`: structured claims + cited numeric facts | Cannot alter measurements or add unsupported catalysts |
| Independent verifier | Draft, evidence and stored signal | Check results, conflicts, unresolved claims | Cannot override code-based math or source policy |
| Editor / policy gate | All stage outputs and topic risk | `held` or `shadow_ready` | Cannot call external publisher in current version |
| Publisher (future) | Approved, immutable article ID | Idempotent release, correction and audit log | Cannot accept raw agent text without explicit approval |

Contracts are implemented in `marketsignal/editorial.py` as frozen dataclasses
and two narrow adapter protocols (`ResearchAgent`, `WritingAgent`). They are
serializable, testable, and independent of the eventual model provider.

### Current typed fields

- **Candidate:** one `Market`/`Signal` pair plus risk category. Production
  defaults to `unknown`, which is held until policy establishes eligibility.
- **Evidence:** a stable ID, HTTPS source URL, title, kind, retrieval timestamp,
  and SHA-256 provenance digest. A digest of our own archived market quote is
  **not** evidence that a third-party page has been fetched or fact-checked.
- **NumericFact:** market ID, baseline/current times and prices, and a
  recomputable percentage-point delta.
- **Claim:** text, kind (`market_movement`, `verified_context` or
  `attributed_speculation`, or `causal_explanation`) and explicitly named
  evidence IDs. Attribution documents what someone said, not whether it is true.
- **StoryDraft:** headline, summary, fact and structured claims, writer version.
- **EditorialResult:** deterministic candidate ID, `held`/`shadow_ready`,
  human-readable reason codes, agent-stage trace, evidence and draft.

`shadow_ready` means the synthetic or template case passed the defined
checks. **It does not mean approved for public release.**

## The planned *actual* agent behaviors

### 1. Quant / discovery agent

Keep numeric ingestion and calculations in ordinary code. Upgrade the current
heuristic after enough history accumulates:

- Normalize movement magnitude against that market's own historical
  variability, the spread, liquidity, and volume.
- Identify event clusters, correlated outcomes, and multiple contract changes
  driven by the same underlying event.
- Discount thin or stale books, resolution artifacts, close-to-certain
  markets, and snapbacks.
- Rank candidate **news value** separately from statistical surprise; these
  are distinct measurements. Do not call a heuristic score a p-value.

### 2. Research agent

- Start with the contract question, rules, timestamps and source links.
- On a qualified movement, retrieve read-only intraday price history to narrow
  **when** repricing occurred before searching for developments.
- **Narrative Scout:** collect bounded public discussion/news leads (initially
  Bluesky and GDELT); cluster competing explanations, identify independent
  origins, timing, amplification patterns and checkable claims. Attention is
  evidence that a narrative is circulating, **not** that it is factual.
- **Evidence Investigator:** investigate a maximum of three hypotheses with
  up to two rounds of targeted, source-specific searches. Find counterevidence
  as well as support. Do not force a conclusion just to fill an article.
- Search bounded, reputable primary sources and contemporaneous independent
  reporting. Prefer official documents for event confirmation.
- Return structured source cards with `retrieved_at`, `published_at`,
  article/source identity, a short finding and SHA-256 of fetched content.
- If no defensible catalyst is found, return **unknown**, not a speculative
  explanation. Record disagreement between sources.
- Return a ranked research packet with separate **discussion strength** and
  **factual corroboration** scores, evidence IDs, refutations, unresolved
  questions and recommended narrative angles. A timestamp correlation alone
  never establishes that a development caused the market movement.
- Treat webpages and documents as untrusted data: never execute instructions,
  expose secrets, alter workflows or grant permissions based on page content.

#### Social-data access and retention boundaries

- **Bluesky:** use documented public read-only endpoints subject to rate
  limits; test actual search coverage and acknowledge platform selection bias.
- **GDELT DOC 2.0:** discover news article URLs and dates, then access and
  verify primary sources separately. Search hits/titles alone are leads.
- **Reddit:** require prior approved OAuth API access, including separate
  commercial permission if applicable. Honor deletion requirements; never
  build unapproved scraping or permanently archive raw posts in public Git.
- **X:** keep behind an explicit paid-adapter switch and cost cap; do not use
  undocumented scraping as a free workaround.
- For all social sources, prefer minimal IDs/URLs and ephemeral short-lived
  retrieval caches; do not retain unnecessary user profiles or redistribute
  raw post contents as a Git-tracked dataset.

Primary source references: [Polymarket market data](https://github.com/Polymarket/agent-skills/blob/main/market-data.md),
[Bluesky public API](https://docs.bsky.app/docs/api/app-bsky-feed-get-author-feed),
[GDELT DOC API](https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/),
[Reddit builder policy](https://support.reddithelp.com/hc/en-us/articles/42728983564564-Responsible-Builder-Policy),
and [X developer pricing](https://developer.x.com/).

### 3. Writer agent

- Produce a genuine newspaper story: a relevant factual development and human
  stakes in the lead, previous expectations and rationale, credible context,
  exact-source quotations, fair competing explanations and social implications.
- Keep betting-market movements out of headlines and leads. Place them later
  as a secondary indicator of shifting expectations, with clear limitations.
- Determine the length from actual evidence density and source independence;
  hold the story rather than pad thin research with invented detail.
- Distinguish **Yes contract price** from a calibrated event probability.
- Render numeric facts from the stored `Signal`, not freehand model output.
- Never write "X caused the move" unless the explanation has direct evidence.
- The writer **may** discuss documented public speculation in a clearly
  attributed, explicitly unverified way when the source-discussion claim
  itself is independently checked and editorial risk is low. It must never
  silently upgrade "people are discussing X" into "X happened".
- Output claims with source IDs; an unsourced claim becomes a reason to hold.

### 4. Independent verifier agent

- Recompute timestamps, price deltas and units directly from the archive.
- Resolve the actual cited pages and compare every material factual assertion
  with primary evidence, not simply the research agent's summary.
- Detect contradictions, stale sources, event-rule mismatches and fabricated
  links; assess whether the headline exaggerates what the contract means.
- Provide a structured verdict and issue list; self-critique by the writer is
  **not** an independent check.

### 5. Editorial agent and publisher

- Default to HOLD for elections, health, allegations, security/conflict,
  unknown risk, unsupported explanations, and unresolved contradictions.
- **Investigative speculation policy (owner decision, 2026-11-03):** do not ban
  attributed speculation outright, but allow it *only* if its existence is
  verifiable from accessible dated posts, multiple independent origins or
  unusually strong directly attributable sourcing support its news value,
  the framing says what remains unverified, and the topic is low-risk.
  Repetition, engagement and trader enthusiasm are not corroboration of truth.
  A coordinated rumor or market-manipulation attempt must not gain credibility
  simply because the newsroom repeated it.
- A single anonymous accusation, high-consequence allegation, fabricated
  source, or sensitive unverified claim stays internal, even if heavily shared.
- Initially allow only **low-risk, market-movement-only** briefs into the
  automated shadow-ready category. All social/narrative claims remain HELD for
  independent language verification and editorial review. This rule must be
  explicitly changed after measured shadow evaluation; agreeing to consider
  speculation is **not** approval to auto-publish it.
- In a later phase, a separate signed/configured publishing mechanism would
  check allowlisted categories, source freshness, cost budgets, article ID,
  an emergency kill switch and duplicate state before writing public content.
- Keep correction and withdrawal records; do not silently replace history.

## Spend and maintenance limits

The current workflow uses **zero model tokens**; the bounded shadow research
job does make free public-source discovery requests.
When paid agents are enabled, proposed *starting* limits are 10 investigated
signals/day, 5 fetched sources/signal, one writer and one independent verifier
attempt per signal, and a hard daily-dollar ceiling. Those are design budgets,
not configured billing caps today. Provider keys would live in managed secrets,
never in Git-tracked JSON or prompt text.

The site stays static. The editor can publish only immutable, verified article
records, not arbitrary page edits by an LLM. Retry keys derive from the market
ID and observation window to prevent duplicate stories.

## Testing before paid agents

```bash
python -m marketsignal editorial-demo
python -m marketsignal feature-demo
python -m unittest discover -s tests -v
```

The demo is fictional and writes **nothing** to the live site. Tests include
tampered math, mismatched quote, unknown/high-risk classification, invalid
source URLs, unsupported causal narratives, missing evidence, custom writer
impersonation, deduplication keys and error-message leakage.

Before any unattended explanatory article can be released:

1. Build at least 100 frozen historical/synthetic cases with explicit labels.
2. Evaluate precision of quantitative triage and the false-article rate.
3. Retrieve/cite sources and verify complete URL resolution on each accepted
   case; record failure as HOLD, not success.
4. Run candidate stories in shadow mode for weeks; compare single-model and
   multi-agent approaches at equal per-article cost.
5. Add operational monitoring, manual correction/kill-switch drill, safe
   category allowlist and an owner-approved production release gate.

See [quality gates](quality-gates.md) for the release scorecard. Neither a
passing unit suite nor a live data-only dashboard satisfies editorial launch.
See also the [versioned instructions](agent-instructions-v1.md) and the
[measured synthetic and unmeasured production rubrics](agent-evaluation.md),
plus the [full newspaper-editorial standard](editorial-standard-v2.md).
