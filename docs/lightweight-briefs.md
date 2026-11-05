# Lightweight MarketSignal Briefs — experimental, unpublished

## Editorial decision

MarketSignal is a **filter of current events prompted by changing market quotes**.
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
| Genuine signal | Same contract in two immutable, consecutive daily archive snapshots, within 48 hours; at least 1.0 percentage-point price move; $50k 24-hour volume and $25k liquidity | Incompatible tokens, missing history, stale quotes, thin markets |
| Scout | One or two bounded searches for *reporting on the topic* | No meaningful discoverable reader question |
| Coverage discovery | At least one dated HTTPS publisher headline from the bounded GDELT metadata index | Connector error or no relevant indexed coverage |
| Curation editor | Reader usefulness >=50/100; an intelligible connection and a truthful, non-platform headline; up to four real source IDs | Irrelevance, no substance, deceptive or dubious title |
| Writer | 120–450 words, 3–6 paragraphs, valid market and external references | Unsupported details, missing citations, malformed structure |
| Brief fact check | Independent model review of each paragraph against exactly the dated quote and the indexed title text; one revision allowed | Misrepresentation, spurious causal inference, numerical errors |
| Release | **Always private pending human review** | All AI-checked drafts remain unpublished |

The external source material in this first pilot is **only news-index title
metadata and a link**, not the full article text. That is deliberately labeled
in each private result. The article must attribute anything about external
events to the relevant publisher and must not embellish the publisher's title.
These briefs are useful prototypes for a news-filter product, **not verified
original journalism**. Publication requires an editor to open and read the
linked original reporting, independently confirm material claims and review
licensing and style before releasing anything.

## Pilot bounds and workflow

- Manual GitHub Action: `Lightweight MarketSignal briefs (manual, unpublished)`.
- Automatically selects **up to 12** true market movers from the latest two
  committed daily archives, with a 72-hour live-data freshness requirement.
- Dedicated `gpt-5-mini` Responses API inference, up to six calls per market,
  a local $2.00 spending ledger, and an independently configured provider-side
  $2 hard limit required by the manual dispatch form.
- Tests run before spending; no automated publication, syndication, mailing,
  paid ads, or changes to the live collector.
- Private drafts, publisher headline leads and the ledger are archived only
  in an AES-256-encrypted GitHub Actions artifact with seven-day retention.
  Workflow logs expose market identifiers, scores, gate statuses and spending,
  **never article text or source leads**.
- The original, more demanding investigative pilot is unchanged and remains an
  option for stories that justify deeper research.

## What to evaluate after the run

Review the shortlist for **reader usefulness**, clarity of connection, and
whether an ordinary reader would have learned something from the filtered
coverage. Also record headline-level overreach, duplicate subjects, excessive
hedging, and any broken references. None of the automated gates independently
verify external events, and these outputs are not ready for public distribution.
