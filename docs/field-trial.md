# First real-topic shadow trial: Texas early voting, November 2026

This is the next milestone after the fictional newsroom architecture test:
**can we produce an original, contextual article based on actual reporting,
while preserving source-level accountability and declining to claim facts
we have not verified?**

## Status

- Source-led, human-curated reporting brief: **complete**.
- Original contextual shadow article: **complete**, not published.
- Link/claim/quotation/as-of/rights structural checks: **10/10 pass**.
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
fictional demonstration fixture is included in CI. A case JSON includes each source's publication date,
publisher, origin, a small excerpt, a claim inventory with supporting excerpt
matches, seven source-linked paragraphs, and questions for further reporting.

## The substantive story we tested

An exceptionally large early vote in Texas seemed to coexist with a more
competitive Senate race than the state's long Republican statewide streak
would ordinarily imply. An original analysis of these conflicting clues
needs to distinguish three questions:

1. **What changed?** Preliminary reports put advance voting above 7.7
   million; the Texas secretary of state earlier counted more than 4.2
   million in the first six days.
2. **What did people expect?** A Democrat had not won a Texas statewide
   office since 1994, yet the late university-compiled poll tracker included
   a New York Times/Siena survey favoring the Democrat by seven points.
3. **What does it mean?** High turnout alone does not tell us which party
   benefited; geographic returns and the composition of new versus
   shifted early voters are key uncertainties.

Primary research and contemporary reporting:

- [Texas Secretary of State early-vote release (Oct. 26)](https://www.sos.texas.gov/about/newsreleases/2026/102626.shtml)
- [Texas Secretary of State registered-voter release (Oct. 16)](https://www.sos.texas.gov/about/newsreleases/2026/101626.shtml)
- [University of Texas Texas Politics Project polling tracker](https://texaspolitics.utexas.edu/blog/texas-2026-u-s-senate-poll-tracker)
- [Texas Tribune's early-vote analysis](https://www.texastribune.org/2026/10/31/texas-early-voting-turnout-rate-election-2026/)
- [Texas Tribune's cautions about reading turnout](https://www.texastribune.org/2026/10/20/texas-early-voting-records-election/)
- [Associated Press's historical context](https://apnews.com/article/66df71a7c2bfa962cffd4134ef1a0364)
- [MarketSignal's Nov. 3 morning market snapshot](https://github.com/nolandrw/marketsignal/blob/main/data/archive/2026-11-03.json)

The market snapshot recorded a Democratic Yes quote but **zero new
signals**. The sample story is a *manual editorial topic*, not a claimed
quantitative-triage success. We do not misrepresent the quote as a trade,
the quote as the election outcome, or high turnout as proof of either party's
success.

## What we learned from the field trial

The promising part is that the evidence can support a much better angle than
"Prediction market moves X%." The article's stakes are clear: whether a
historically stable political pattern may be changing and how much can be
inferred from early turnout. The article can explain the prior consensus,
present a plausible change, offer multiple theories, and provide useful
counterevidence without claiming a cause.

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
