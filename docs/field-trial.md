# Texas real-topic shadow trial: editorial re-commission, November 2026

This is the next milestone after the fictional newsroom architecture test:
**can we produce a contextual article based on actual reporting,
while preserving source-level accountability and declining to claim facts
we have not verified?**

## Status

- Source-led, human-curated reporting brief: **complete**.
- Re-commissioned narrative shadow article: **complete**, not published.
- Link/claim/quotation/as-of/rights/story-thesis structural checks: **11/11 pass**.
- Independent editorial originality and reader-value score: **not performed**.
- Independent semantic fact-check: **not performed**.
- Validated movement in the underlying prediction market: **not available**.
- Editorial result: **HELD**, never an article-publication payload.

Run the exact case from the repository root:

```bash
python -m marketsignal field-trial \
  --case data/private/texas_senate_2026_election_day.json \
  --out reports/texas-shadow.md
```

The command does no API calls, costs nothing, and outputs a Markdown preview
to the ignored local `reports/` folder. It refuses to write to `site/`,
`archive/`, or `docs/`. The **real** case JSON is held privately in ignored
`data/private/` (and is not shipped in the GitHub repository). A separate
fictional demonstration fixture is included in CI. A case JSON includes each
source's publication date, publisher, origin, a small excerpt, a claim inventory
with supporting excerpt matches, multiple investigative `story_pitches`, a
chief-editor `editorial_selection`, source-linked paragraphs and open questions.

See [story thesis handoff v1](story-thesis-v1.md) for the newsroom changes.

## The substantive story we tested

The **first** shadow story centered on voter-turnout uncertainty. We spiked
that angle as insufficiently compelling despite its structural audit passing.
The re-commissioned angle is **a $400 million Senate campaign testing Texas's
32-year Republican statewide winning streak**. Its narrative rests on:

1. **Historical expectation:** no Texas Democrat has won statewide since
   1994, yet several late polls indicated an unusually close Senate contest.
2. **Verifiable conflict:** the campaigns have spent a combined $408 million
   on advertising and made contrasting appeals to identity, economic interest
   and religious values.
3. **Reporting tension:** the Republican nominee himself warned that the
   state could slip away; an independent outlet described difficulty uniting
   his own party. Neither proves a specific causal mechanism or election result.
4. **Counterevidence:** polls have sampling uncertainty; turnout totals do
   not identify voters' preferences; actual results remain unknown at the
   shadow's as-of cutoff.

Primary research and contemporary reporting:

- [Texas Secretary of State early-vote release (Oct. 26)](https://www.sos.texas.gov/about/newsreleases/2026/102626.shtml)
- [Texas Secretary of State registered-voter release (Oct. 16)](https://www.sos.texas.gov/about/newsreleases/2026/101626.shtml)
- [University of Texas Texas Politics Project polling tracker](https://texaspolitics.utexas.edu/blog/texas-2026-u-s-senate-poll-tracker)
- [Texas Tribune's early-vote analysis](https://www.texastribune.org/2026/10/31/texas-early-voting-turnout-rate-election-2026/)
- [Texas Tribune's cautions about reading turnout](https://www.texastribune.org/2026/10/20/texas-early-voting-records-election/)
- [Associated Press's historical context](https://apnews.com/article/66df71a7c2bfa962cffd4134ef1a0364)
- [Associated Press's closing-day candidate remarks](https://apnews.com/article/trump-vance-midterm-elections-0f444fe8f424960dd820795e20b00237)
- [Texas Tribune's campaign spending and message analysis](https://www.texastribune.org/2026/10/31/texas-us-senate-election-paxton-talarico-final-push-election-day/)
- [MarketSignal's Nov. 3 morning market snapshot](https://github.com/nolandrw/marketsignal/blob/main/data/archive/2026-11-03.json)

The market snapshot recorded a Democratic Yes quote but **zero new
signals**. The sample story is a *manual editorial topic*, not a claimed
quantitative-triage success. We do not misrepresent the quote as a trade,
the quote as the election outcome, or high turnout as proof of either party's
success.

## What we learned from the field trial

The original article demonstrated a **story-selection failure**: a perfectly
cautious, citation-linked explanation may still be uninteresting. A good
general-interest article needs a concrete development, specific conflict,
characters, surprising tension and credible stakes. The new handoff requires
multiple story theses and explicitly documents why the editor preferred one.
The new title belongs to the editor rather than being frozen at the
investigator's first suggestion. This trial remains derivative of existing
reporting; it has not established enough original value for publication.

The limiting factor is **semantic source verification**. Our `field_trial`
auditor detects missing citations, source mismatches, invented quotation text,
future-dated source claims, and improper publication state. It does **not**
establish that a free-form sentence is entailed by its cited excerpt.
Claim-level semantic accuracy still needs either an independently reviewed
human annotation or an appropriately evaluated verification model **plus**
human signoff. Dates shown as midnight UTC for date-only source metadata
represent the documented calendar day, not verified publication hours.

The first iteration deliberately omitted paid AI. This case is a human-curated
gold-standard *candidate*, not a measurement of agents doing autonomous
research. It should not train the ML news ranker or serve as human feedback.

## Next experiment

Run 5–10 deliberately varied market-topic cases through the same schema,
including at least two **no-go** cases, then commission independent reviewers
to grade claim accuracy, story originality, sourcing diversity and reader
value against the 100-point rubrics. In parallel, accumulate actual price
snapshots so the first production candidate can be selected by the
quantitative gate rather than editorial intervention. Only after those two
steps should a model-based investigator/writer replace any of the manual
curation shown here.
