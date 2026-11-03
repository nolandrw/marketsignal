# Editorial agents — architecture v0.1 (shadow mode)

**Status, 2026-11-03:** code contracts and an executable synthetic replay exist;
there are no LLM calls, paid API dependencies, external article fetches, or
automatic article publication. The data-only daily site continues separately.

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
for model-based text generation and a market-record adapter stands in for
external research. The orchestration and evaluation boundaries stay the same
when paid providers are added. We intentionally do **not** need an LLM
framework just to execute a five-step state machine.

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
  `causal_explanation`) and explicitly named evidence IDs.
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
- Search bounded, reputable primary sources and contemporaneous independent
  reporting. Prefer official documents for event confirmation.
- Return structured source cards with `retrieved_at`, `published_at`,
  article/source identity, a short finding and SHA-256 of fetched content.
- If no defensible catalyst is found, return **unknown**, not a speculative
  explanation. Record disagreement between sources.
- Treat webpages and documents as untrusted data: never execute instructions,
  expose secrets, alter workflows or grant permissions based on page content.

### 3. Writer agent

- Produce a concise market-first headline, short factual summary, why the
  movement may matter, and linked evidence.
- Distinguish **Yes contract price** from a calibrated event probability.
- Render numeric facts from the stored `Signal`, not freehand model output.
- Never write "X caused the move" unless the explanation has direct evidence.
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
- Initially allow only **low-risk, market-movement-only** briefs into a
  reviewed shadow queue. Never equate a shadow pass with publish approval.
- In a later phase, a separate signed/configured publishing mechanism would
  check allowlisted categories, source freshness, cost budgets, article ID,
  an emergency kill switch and duplicate state before writing public content.
- Keep correction and withdrawal records; do not silently replace history.

## Spend and maintenance limits

The current workflow has **zero tokens and zero external research calls**.
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
