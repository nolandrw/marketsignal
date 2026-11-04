# Source capture and autonomous reporting foundations (v1)

**Status:** source-capture transport and research-case assembly implemented,
tested against an offline web/robots harness. Live independent research and
article-quality evaluation are **not certified**. No real articles are
automatically published.

## Why this is a separate layer

In the old shadow run, the investigator could only work with a source inventory
that a person had already researched. That is not an autonomous reporting
operation. A new layer now joins discovery leads to *permissioned page
captures*, short excerpts and source-linked proposed claims. It must not
silently promote a news-search result or a market comment into a fact.

```mermaid
flowchart TD
  A["Archived qualifying price signal"] --> B["GDELT historical/recent discovery"]
  B --> C{"Publisher allowlist + robots"}
  C -- denied --> H["Research hold with reason"]
  C -- allowed --> D["Bounded HTML capture"]
  D --> E["Publisher date + digest + short excerpts"]
  E --> F{"Independent origins and primary record?"}
  F -- no --> H
  F -- yes --> G["Opt-in model claim extraction"]
  G --> I{"Exact excerpt provenance + required roles"}
  I -- no --> H
  I -- yes --> J["Provisional research case"]
  J --> K["Existing investigator → verifier → editor loop"]
```

### Permissions and source fidelity

- Fetches are HTTPS-only on **exact hosts** explicitly listed in the publisher
  policy, not every URL returned by GDELT. No credentials, cookies, redirects,
  arbitrary ports, IP-literal hosts, local endpoints or access circumvention.
- Fetches publisher `robots.txt` and declines captures it disallows or whose
  crawl delay exceeds the bounded job budget. A missing/unreadable robots
  document is a hold. Only HTML with an identifiable `article`/`main` body
  is accepted; client-rendered or blocked pages remain holes in the dossier.
- A publisher's own publication date is required, not the GDELT discovery
  timestamp. The source must predate the candidate's **as-of** timestamp.
- A full-page SHA-256 fingerprint is kept for provenance; only up to three
  intact short paragraphs (each ≤370 characters) are saved as excerpts. This
  is not permission to reproduce copyrighted reporting or images.
- Captures from one domain count as **one origin**, no matter how many excerpts
  are saved. Before paid claim extraction, the package needs three origins,
  a primary source and an authorized independent reporting source.
- The optional claim-extractor model must attach valid source IDs and exact
  contiguous excerpts. Deterministic checks reject fabricated excerpts and
  unsupported category-role labels. This does **not** constitute semantic
  truth verification: the claim could still overstate the excerpt.

### Source policy

The example policy contains federal primary-source domains only. It
intentionally does **not** authorize scraping AP, the Texas Tribune or other
copyrighted journalism. Before adding independent reporting hosts, review
publisher terms and obtain an appropriate text-extraction permission or
licensed feed. The gateway requires `permissioned_short_excerpt` for that
classification, but a JSON configuration is a declaration of permission,
not evidence that rights have actually been obtained.

The current GDELT discovery adapter returns **article metadata**, not
verified source content. Polymarket comments and social chatter are even
lower-trust leads and are excluded from the claim-evidence stream.

## Command sequence

From the repository root, after a daily archive has at least one qualifying
signal and a host policy has been approved:

```bash
python -m marketsignal capture-context \
  --archive-file data/archive/YYYY-MM-DD.json \
  --policy-file examples/source-capture-policy.example.json \
  --max-pages 4 \
  --out data/private/captured-context.json

# Explicitly opt-in to paid inference. Requires OPENAI_API_KEY.
python -m marketsignal assemble-research-case \
  --capture-file data/private/captured-context.json \
  --case-id specific-story-unique-id \
  --out data/private/working-research-case.json

python -m marketsignal shadow-loop \
  --mode openai \
  --case data/private/working-research-case.json \
  --out reports/investigation.md \
  --trace reports/investigation.json
```

Without a qualifying movement, capture returns `no_qualifying_market_signal`
without fetching articles. Without diverse approved sources, assembly returns
`needs_more_sources` **before** any paid claim-generation call. Without a model
credential, it holds and makes no implicit paid request. The final newsroom
command always remains an **unpublished shadow**.

## What was actually tested

- Controlled three-publisher HTML captures with three independently named
  origins and first-party publication timestamps.
- Publisher `robots.txt` allows and blocks; blocked links never reach article
  fetching.
- HTML script/prompt injection is not treated as article evidence.
- Nonallowlisted/local URLs, future-dated articles, and missing publisher dates
  fail closed.
- An in-memory claim extractor can produce an excerpt-linked working case,
  while missing independent reporting prevents a model call entirely.
- The existing downstream shadow newsroom remains disconnected from release.

**Empirical limitation:** the runtime has no model API credential, and web
fetching from arbitrary publishers is not enabled in this execution
environment. The tests prove orchestration and source controls, not that the
live source corpus is rich enough or that a model can independently report
an original, high-quality story. A real trial should include 5–10 categories
and record *research yield, citation correctness, novelty, editorial score,
human disagreements,* and cost per candidate. Do not optimize to reach 90 by
having the agent grade its own output more generously.
