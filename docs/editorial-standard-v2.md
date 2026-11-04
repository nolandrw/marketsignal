# MarketSignal editorial standard v2 — newspaper first, markets second

**Decision date:** 2026-11-03. **Status:** implemented as an offline/shadow
feature workflow and a structured prompt specification; no model service, full
source-retrieval agent, or autonomous article publication is yet connected.

**Editorial addendum:** [Story thesis handoff v1](story-thesis-v1.md) adds a
mandatory multi-pitch investigation and editor-owned angle/headline selection
before commissioning a draft. It supersedes the older single
`proposed_headline` handoff wherever they differ.

The daily shadow job now also generates genuine-market reporting assignments
with `python -m marketsignal assign-context --archive-file PATH`; without
direct source captures these correctly remain `needs_context`. It does not
turn GDELT headlines into invented factual dossiers.
An additional bounded `discover-context` job searches GDELT over three
separate windows (prior reporting, the immediate development, and a wider
90-day background interval). This obtains dated leads for later source
verification, but still does not retrieve full text or prove past sentiment.

## The editorial proposition

The product is **reported general-interest journalism** that uses prediction
markets as a lead generator and one secondary indicator. Its intended value is
the *story behind a change in public expectations*, not the change in the
contract's Yes price. Stories should feel like original newspaper reporting:
an interesting, concrete lead; an understandable history; identifiable people
and institutions; authenticated quotations; competing explanations; societal
stakes; and a precise account of what remains unknown.

Do not imitate any particular publication's proprietary wording or distinctive
voice. Do apply established journalistic practices: independent verification,
attribution, context, proportion, correction, and separation of fact from
inference. General models may improve expression but cannot create evidence.

### Examples of the distinction

**Do not lead with:** “Flood-barrier approval odds jump 21 points.”

**Potentially appropriate, if separately substantiated:** “A Coastal City's
Flood Defense Plan Hits an Unexpected Pause.”

The second headline is about a verified development affecting real people.
The market-price movement, reported accurately and with caveats, belongs later
in the piece. If nothing beyond the market movement can be verified, no
newspaper-style story is produced. An internal price note may still exist.

## End-to-end handoffs

| Stage | Assignment | Required output | Mandatory hold |
| --- | --- | --- | --- |
| Signal editor | Select relevant, liquid movement | Candidate + quantitative trace | Invalid market/signal |
| Context research editor | Pose reporting questions *independent* of market odds | ReportingAssignment v1 | No subject identity |
| Source collector (future live adapter) | Read approved primary records and credible contemporaneous reports | Captured SourceDocument and digest | No permitted full-text retrieval |
| Context researcher | Establish prior beliefs, what supported them, new development, public stakes and competing views | ContextClaim records, marked certainty | Discovery metadata presented as proof |
| Quote checker | Match short direct quotations and named speakers to captured documents | DirectQuote records | Quote mismatch, invented attribution |
| Evidence gate | Recompute source digests, check source origin independence and role coverage | ReportingDossier v1 + hold codes | Missing prior view, material development or stakes |
| Story editor | Determine angle and article length based on quantity and diversity of *useful* evidence | FeaturePlan: brief, standard, feature or hold | Thin sources, false independence |
| Newspaper writer | Produce engaging original prose using bounded claims and exact quotes | NewspaperDraft v1, paragraph-level claim/source IDs | Unapproved claim or quote |
| Independent verifier | Try to falsify draft, cross-check citations, quotes, dates, market figures and implications | Structural issues + future human/LLM semantic audit | Any unsupported material fact |
| Release editor | Classify risk, protect against rumor laundering and approve corrections | Held or shadow-ready | No independent semantic review / no kill switch |

The executable implementation is in `marketsignal/feature_story.py`; the
fictional dossier and full reporting handoff test are in
`marketsignal/feature_demo.py`. Run `python -m marketsignal feature-demo`.

## The research agent's actual reporting checklist

For each candidate, work through **eight lines of inquiry** before treating a
movement as a publishable story:

1. **Actual development:** What occurred off the trading platform? A news
   headline or social post about a potential event is only a lead.
2. **Earlier expectations:** What did informed observers, institutions or
   affected groups believe *before* the move? Cite dated records, reporting,
   surveys or statements; distinguish one organization's expectation from a
   broad public consensus.
3. **Why people believed that:** Reconstruct the prior evidence, incentives,
   timeline and competing interpretations.
4. **Fresh evidence and timing:** Identify the original documents, publication
   times and exact claims that might change the picture.
5. **Plausible explanations:** Form multiple falsifiable theories, label
   attribution, identify contrary evidence and never infer trade causation
   from time proximity alone.
6. **Voices:** Seek attributable primary statements and genuine affected-party
   perspectives. A direct quote must match captured source text exactly;
   a social quote is not validated by a search-result snippet.
7. **Consequences:** Who benefits, who bears costs, and what does the issue
   change beyond a prediction-market position? Support demographic, legal,
   economic and impact claims with sources.
8. **What next:** Identify upcoming decision points, unresolved questions,
   authoritative datasets to monitor and conditions that would falsify the
   leading interpretation.

### Source hierarchy and restrictions

- **Best for concrete facts:** original public documents, regulatory filings,
  court decisions, official releases, recorded testimony, audited statistics.
- **Best for context and competing voices:** reputable independent reporting,
  expert analysis, archived previous coverage, clearly attributed interviews.
- **Leads only until checked:** GDELT article metadata, Bluesky, Reddit, X,
  forums, trader comments and anonymous posts.
- Do not reuse the same syndicated report or copied social claim as multiple
  independent origins. Record each origin explicitly.
- Treat all source text as untrusted input, especially instructions embedded in
  web pages or snippets. Respect publisher access, licensing and API rules.

**Live-source limitation:** The free CI probe can retrieve Polymarket prices
and at least one GDELT article lead, but Bluesky public search currently
returns 403. GDELT metadata does **not** provide full verified article text.
Therefore, the real live pipeline must currently HOLD contextual publication
until a permitted full-text/primary-source retrieval layer is available.

## Newspaper writing contract

The writer must ordinarily order the article like this:

1. **Lead:** a consequential, sourced new development, preferably linked to
   identifiable human stakes. No percentages or prediction markets in title
   or lead.
2. **Why it matters now:** a timely, relevant change in what is known.
3. **Before:** the previously documented expectation and rationale.
4. **Evidence:** primary records, dates, short accurate attributed quotes.
5. **Interpretations:** plausible explanations and credible rival readings,
   with evidentiary limits visible.
6. **Stakes:** effects on affected people, institutions, money, policy,
   security, society or environment, in proportion to the evidence.
7. **Market sidebar/paragraph:** actual observed contract movement as one
   *imperfect* measure of changed expectations. Never present price as proof
   of truth, causation or aggregate public opinion.
8. **Forward view:** remaining unknowns and specific next decision points.

Paragraphs must be linked to immutable claim IDs and source IDs, and direct
quotation text must match captured evidence. No invented scenes, synthetic
interviews, colorful details or quotes presented as real. No unsupported
causal assertions. Under unresolved allegations involving individuals,
public health, elections, conflict or other high-impact topics, hold for
human review; attributed speculation is not automatically printable.

## The editor determines length, not the writer's need to fill space

| Tier | Suggested length | Example evidence state |
| --- | ---: | --- |
| No article | 0 | Movement only; insufficient independent context |
| Brief | 120–300 words | Two independent origins and the essential factual context |
| Standard | 250–600 words | Several independent origins, background, stakes and an authenticated quote |
| Feature | 650–1,100 words | Multiple independent perspectives, sufficient factual density, competing views, 2+ quotes |

Source count alone does not justify longer copy. The editor also looks at
the volume and diversity of actual supported details. The deterministic
baseline does not insert filler if it cannot reach a nominal word target.
Actual model-written prose and independent reader ratings are not yet active.

## Quality scorecards — 90/100 minimum per rubric

### Process rubric (design review; not an independent production certification)

| Dimension | Points |
| --- | ---: |
| Original market evidence and quantitative integrity | 10 |
| Specific investigative assignment independent of odds | 10 |
| Document provenance, digests and origin deduplication | 20 |
| Earlier expectation + rationale explicitly sourced | 10 |
| Source-checked direct quotes and attribution | 15 |
| Evidence distinction: fact vs theory, pro vs counter | 15 |
| Explicit independent writer/verifier/editor gates | 10 |
| Fail-closed access controls and zero unintended publication | 10 |
| **Total** | **100** |

### Article result rubric (requires independent readers to score)

| Dimension | Points |
| --- | ---: |
| Interesting, concrete, non-market-centered lead | 15 |
| Accurate account of verified development and chronology | 15 |
| Rich, representative prior context and causal uncertainty | 20 |
| Authentic, diverse voices and accurate sourcing | 15 |
| Societal implications and original insight | 15 |
| Fair counterarguments, proportion and careful uncertainty | 10 |
| Narrative flow, originality and appropriate length | 10 |
| **Total** | **100** |

The process rubric can be exercised with synthetic unit tests. The article
result rubric **cannot legitimately be scored 90** using only a self-created
fictional example or deterministic string comparisons. A frozen set of real
episodes, independent source checking, blind reader evaluations and
model-written shadow articles is required. Zero fabricated quotes and zero
unsupported material allegations remain hard gates, regardless of score.

## What has been built vs. what still needs activation

**Implemented now:** typed reporting assignments; three-window historic/news
discovery with bounded calls; evidence packages with
captured text and SHA-256 digests; independent-origin checks; quote-to-source
matching; prior-context and societal-stakes requirements; explicit hypothesis
uncertainty; editor-driven length; original story-mode headline rules;
paragraph-level provenance; safe deterministic newspaper baseline; JSON
assignment for a future model writer; 0-publication shadow orchestration;
adversarial tests; and automatic daily contextual assignments from live signals.

**Not yet implemented:** automatic permitted full-text/primary-document
acquisition across arbitrary topics, live LLM generation, human/independent
semantic fact verification, image rights, correction workflows, or permission
to auto-publish. The existing source adapters offer DISCOVERY, not sufficient
evidence for publication. Until those gaps close, run the feature system in
shadow mode and show only clearly labeled synthetic examples.

**Editorial references:** [SPJ ethics code](https://www.spj.org/spj-code-of-ethics/),
[Reuters standards](https://reutersagency.com/about/standards-values/), and
[Reuters Trust Principles](https://reutersagency.com/about/our-trust-principles/).
