# MarketSignal newsroom: enterprise-level role and handoff audit

**Audit date:** 2026-11-04  
**Decision:** Retain the specialized newsroom structure, tighten independent
decision boundaries, and do **not** represent the current shadow workflow as a
live autonomous news outlet. A model role, an executable program, and an
independently qualified newsroom judgment are three different things.

This document is the starting playbook for subsequent agent-by-agent review.
It identifies the weakest link, immediate adjustment, exact handoff condition,
evaluation method, and work still missing for each role. `docs/newsroom-v3.md`
contains the wider mission and baseline weights; `docs/topic-lead-v2.md` is
the versioned, already implemented Topic Lead specification. The stage prompt
source of truth is `marketsignal/model_gateway.py`.

## The actual system, not the imagined system

| Role | Current execution | Most consequential remaining weakness | Intervention priority |
| --- | --- | --- | --- |
| 0. Data ingestion and quantitative triage | Deterministic multi-horizon scorer | Thresholds and volume heuristics lack externally labeled precision/recall | High |
| 1. Topic Lead | Versioned prompt, deterministic gates, manually sourced opt-in assessment | Prior-coverage checking and source gathering still depend on an operator | Critical |
| 2. Investigative journalist | Opt-in model, recorded replay, evidence-only shadow loop | Does not independently collect new documents or interview anyone | Critical |
| 3. Pitch / claim verifier | Opt-in model plus claim/source structural checks | Same underlying source packet and possible model biases; no independently authenticated fact-checker | Critical |
| 4. Chief editor | Opt-in model, score/angle gate and new research HOLD | No actual editorial accountability or demonstrated calibration to reader interest | High |
| 5. Writer | Opt-in model under editor-owned headline; deterministic provenance checks | Language can imply facts stronger than excerpt evidence | Critical |
| 6. Paragraph fact verifier | Opt-in model and exhaustive paragraph index gate | Self-consistent model judgments are not independent truth | Critical |
| 7. Editorial quality reviewer | Opt-in model; explicit score and two bounded returns | Scores reward polished recycled material if originality cannot be independently checked | High |
| 8. Copy editor | Newly added deterministic draft/link/image preflight; **no rendering agent** | Real layout, copyright authorization and accessibility review absent | High |
| 9. Synthetic audience diagnostics | Eight fixed transparent heuristics | No evidence that heuristic failures predict human interest or editorial value | Medium |
| 10. Release editor | Deterministic controller; private HOLD by default | Human semantic fact-check and authenticated final approval not integrated | Critical |
| 11. Librarian | Append-only private event hash chain | Not a signed immutable audit, no complete artifact lineage or outcome data | High |
| 12. Overseer | Three-tranche proposal policy and operational counters | Historical quality grades were inferred from self-reported reason codes | High—corrected in this pass |

**Engineering status notation:** **Implemented** means a testable local
control, not newsroom correctness. **Specified** means a requested role or
contract that cannot be evaluated until real source, human review, or deployment
integrations exist.

## Mandatory control plane shared by every role

1. **One immutable case identity.** Carry market ID, observation timestamp,
   source capture timestamps, model/prompt version hash, source IDs, content
   hashes, inputs, outputs and every disposition through a private case ledger.
   A headline, source or allegation changed after approval invalidates any
   earlier approval. **Partial implementation:** stage call hashes and copy
   article digest exist; full cross-system artifact store is specified.
2. **Budgeted graph, not recursive conversations.** Hard call ceilings, two
   reporting returns, two writer returns and one release return. Every loop
   returns a typed request, tracks elapsed time/cost and ends in HOLD or SPIKE.
   A request for more work is never permission to skip the work. **Implemented**
   in the shadow loops; end-to-end retry reconciliation remains specified.
3. **Three independent judgments.** Quant identifies unusual trading; a
   commissioning editor identifies a valuable story; a verifier checks
   evidence. No one stage may pass itself via its own numerical score.
   A model acting under a different prompt is not organizational independence.
4. **Original records outrank inference.** Corroboration means genuinely
   independent origins, not several sites copying one claim. Social and
   Polymarket comments may generate questions, never certified assertions,
   measures of public opinion or narrative causation.
5. **Human editorial responsibility.** An authenticated designated human
   must verify article facts, serious allegations, quote fidelity, headline,
   image rights and corrections before publication. The owner must separately
   authorize article-level release. **Not integrated:** publication remains
   disabled; the fictional example correctly ends in HOLD.
6. **Conflict-of-interest firewall.** Sponsorship, affiliate/referral programs,
   trading positions and potential advertiser relationships must not alter
   inclusion thresholds, fact grades, tone, story angles, headlines or
   release decisions. Disclose relevant conflicts and distinguish sponsored
   material. A prediction-platform affiliate link must never replace an
   ordinary editorial source URL.
7. **A second clock for replay.** Evidence must have been *available* at the
   relevant as-of moment, not just published with an older date. Late edits,
   corrections and delayed market snapshots are replays' most dangerous
   leakage sources. **Specified:** captured-at lineage must be persisted for
   all source versions before quantitative/ML backtests become reliable.

## Revised role contracts and pass/fail instructions

### 0. Quantitative triage / data scientist

- **Sole objective:** maximize *interesting leads surfaced per editor-hour*
  within a fixed triage budget, not maximize movements or claim a statistical
  p-value from an uncalibrated score.
- **Required inputs:** market wording and resolution, venue/units, liquidity,
  current bid/ask or quote caveat, 1h/24h/7d/30d history, freshness, category,
  missingness and event correlation/market clustering.
- **Output:** timestamped feature vector, baseline sources, absolute
  percentage-point changes, unusually high/low activity explanation,
  confounders and `GO_FOR_TOPIC_REVIEW` / `HOLD_FOR_DATA`. Scores rank leads;
  they do not represent probabilities of relevance.
- **Rubric, 100:** as-of/time integrity 25, quote and venue unit accuracy 20,
  signal-versus-noise robustness 20, category/historical context 15,
  interpretable ranking 10, completeness/operating cost 10.
- **Hard gates:** invalid contract or impossible quotes -> HOLD; missing 1h
  history does not masquerade as an observed 1h movement; illiquid or
  materially stale snapshots -> HOLD; correlated contracts deduplicated by
  event before counting story opportunities.
- **Evaluation:** human-labeled *precision@K and recall at editor-hour budget*,
  false-positive volume, missed major stories, category stratification, time
  leakage audit, prospective challenger-versus-fixed backtest.
- **Status:** historical movement and HOLD controls implemented; event
  clustering, empirical thresholds and measured labels are **not**.

### 1. Topic Lead / assigning editor

- **Sole objective:** find a *specific, consequential, original story worth
  investigating*; neither celebrate a dramatic odds movement nor write a
  generic uncertainty piece.
- **Inputs:** structured quantitative pitch; exact resolution wording; dated
  source leads; real prior-coverage search results with which angles were
  already reported. An upstream `coverage_checked=True` boolean alone is
  not enough to evidence a search.
- **Outputs:** up to three provisional story angles, each with an honest
  reader-facing headline, central question, thesis-to-test, falsification
  path, independent source IDs, public stakes, original contribution and
  concrete research ticket; plus a scored GO/HOLD/SPIKE and revisit trigger.
- **Rubric, 100:** news peg 20, consequences 20, editorial potential 20,
  originality 15, research feasibility 15, timeliness 10. Hard news peg,
  source, relevance and duplication gates *cannot be averaged away*.
- **Hard gates:** passing score >=65 and defensible news peg or testable
  original analysis; coverage duplication, vague premises, low-reliability
  sourcing and unexplained moves produce HOLD/SPIKE with reason; a high-impact
  uncertainty must be held for bounded research rather than invented causality.
- **Evaluation:** blinded editor GO agreement, high-value pitch recall,
  novelty against actually published stories, accepted dossiers per 100
  investigated leads, and high-risk false-positive rate.
- **Status:** detailed v2 prompt/schema/gates implemented and regression
  tested; active source acquisition/archive similarity is **not**.

### 2. Investigative journalist

- **Sole objective:** convert the assignment into a *falsifiable reporting
  dossier with novel information*, including contrary evidence. Do not
  manufacture multiple theories merely to appear balanced.
- **Inputs:** Topic Lead source leads and story question, dated context,
  available original documents, previously published coverage, research
  tickets and accepted investigation budget.
- **Outputs:** 1–3 supported candidate narratives with why-now, dated
  sequence, affected parties, supporting and counter-claim IDs, origin
  independence and explicit unverified causes; unanswered questions become
  tickets with evidence types, not paragraphs of hand-waving.
- **Rubric, 100:** provenance/timeline accuracy 25, original evidence 25,
  disconfirmation 20, reader stakes and depth 20, cost/replayability 10.
- **Hard gates:** no original documents or new angle -> report `HOLD`;
  plausible but unsupported explanation -> label hypothesis; comment-derived
  claims -> source-search direction only; one strong angle is enough.
- **Handoff:** `pitch_id`, full claim/source index, unproven assertions,
  alternate/null explanation, disconfirmation method and named missing work.
- **Evaluation:** independently verified original contributions per hour,
  source diversity, false causal explanations, quality of answered tickets.
- **Status:** instructions and 1–3-pitch contract improved; autonomous
  external research, interviews and new capture ingestion **not integrated**.

### 3. Pitch / claim verifier

- **Sole objective:** falsify unsupported assertions rather than help the
  investigator get approved. Review independently from *original source
  excerpts* instead of inheriting the investigator's preferred conclusion.
- **Inputs:** entire dossier including dated original captures, source
  provenance tree, all pitches, counterevidence and relevant market terms.
- **Outputs:** one review per pitch and one future claim-level disposition
  for each material assertion: approve with source, qualify, research or
  reject, with concrete tickets and an explicit residual-risk statement.
- **Rubric, 100:** unsupported-claim detection 30, source interpretation 25,
  adversarial testing 20, risk/attribution 15, actionable tickets 10.
- **Hard gates:** `accept` plus any issue or research request is rejected
  by deterministic orchestration; missing or duplicate reviews HOLD; serious
  personal allegations, health/safety or price-sensitive causal claims need
  additional human/source review; deadline or cost pressure cannot waive.
- **Evaluation:** seeded unsupported-claim false accepts, quote/context
  mismatch detection, sensitivity/specificity on independent editorial labels,
  escalation accuracy, provenance audit and appeals.
- **Status:** reject `accept-with-unresolved-issues` implemented; source
  independence remains limited to the same packet; human verification is
  **not** provided by changing model role.

### 4. Chief editor / commissioner

- **Sole objective:** decide whether the evidence supports a *compelling,
  accurate and original article*, then own the angle, headline, lede premise
  and assignment—not simply pick the highest-scoring market pitch.
- **Inputs:** provisionally verified pitches, exact source and contradiction
  summaries, prior coverage, risk flags, costs and competing editorial value.
- **Outputs:** `COMMISSION`, `HOLD` or `SPIKE`, selected pitch ID, headline,
  single-sentence reader promise, writer length/section guide, forbidden
  assertions, and concrete `requested_work` if any.
- **Rubric, 100:** reader stakes/consequences 25, specificity/lede 20,
  independently supported novelty 20, evidence/risk 20, contextual fairness
  10, length/efficiency 5; a separate editorial score is **not** fact safety.
- **Hard gates:** any nonempty `requested_work` -> research HOLD before
  writer; no evidence-grounded compelling headline -> HOLD rather than 'we
  don't know' article; no quote, angle or source upgrades by enthusiasm.
- **Handoff:** editor-owned exact headline, commissioned thesis and sources,
  verbatim claim IDs, prohibited extrapolations and approved length tier.
- **Evaluation:** blinded editor commission agreement and actual article
  acceptance; estimated versus realized reader value without rewarding
  clickbait; revision waste and duplicate coverage.
- **Status:** `requested_work` now enforced; model guidance updated;
  accountable human commissioning **not connected**.

### 5. Writer

- **Sole objective:** make the real-world development clear, valuable and
  absorbing to a nonexpert while preserving every source's meaning.
- **Inputs:** commissioned angle/headline; verified claim ledger; source
  captures; section order; forbidden claims; requested length and style.
- **Outputs:** exact editor-approved headline, accurate deck and linked
  paragraphs; each factual assertion traceable to a supporting claim/source,
  competing hypotheses explicitly attributed, market mechanics secondary.
- **Rubric, 100:** factual faithfulness 30, narrative and lede 20, reader
  explanatory value 20, attribution and fairness 20, concision 10.
- **Hard gates:** no invented quotes/scenes; no unapproved headline change;
  source links alone do not prove text; a reporting hole causes a ticket/HOLD;
  no more than two writer revision returns.
- **Evaluation:** blinded human paragraph support, reader comprehension,
  originality versus source packet, factual corrections per 1,000 words and
  time/cost to acceptable draft.
- **Status:** revised prompt and deterministic source-link, quote and exact
  headline gates implemented; semantic certainty still **requires a human**.

### 6. Article fact verifier

- **Sole objective:** catch the plausible *untrue implication*, including
  hidden causal framing and omitted caveats, in **every** paragraph.
- **Inputs:** rendered draft, exact source capture used, complete claim
  ledger, correction history and release risk tier.
- **Outputs:** one verdict per numbered paragraph, sentence-level issue and
  fix instructions, article-wide chronology/frame risks, no residual claims
  silently ignored. Distinguish model provisional assessment from independent
  human approval.
- **Rubric, 100:** source-entailment fidelity 35, critical risk recall 25,
  independent corroboration 20, precise corrections 10, coverage 10.
- **Hard gates:** full paragraph-index coverage; `supported` with issue(s)
  is not a pass; unverifiable quotation, misleading juxtaposition or copied
  secondary source is a return/HOLD. Human/editor approval remains separate.
- **Evaluation:** planted misleading causality, forged quote, fact-without-
  context, timeline mismatch and attribution stress cases, using a human key.
- **Status:** systematic all-paragraph checks and prompt strengthened;
  not a substitute for an independent fact-checking desk.

### 7. Editorial quality reviewer

- **Sole objective:** improve useful journalism **after** factual review,
  without conflating elegant prose with actual new reporting.
- **Inputs:** final draft, editor assignment, original contribution claim
  and prior-coverage index; exclude the writer's self-score and earlier quality
  scores to avoid anchoring.
- **Outputs:** `PASS`, `REVISE` or `HOLD`, score by published rubric,
  paragraph-specific actionable markup, missing reader questions and strong
  elements; a high score never overrides unresolved verifier issues.
- **Rubric, 100:** substantive original contribution 25, specific lede and
  relevance 20, context/explanation 20, clarity/narrative 20, fairness 15.
- **Hard gates:** absence of original value or a defensible headline is HOLD
  even if high prose quality; do not force artificial surprise or length;
  no more than two writer returns.
- **Evaluation:** blinded experienced editor agreement, human comprehension,
  added-value over equivalent wire brief and correction-adjusted engagement.
- **Status:** prompt revised; existing `story_thesis` rubric retains its
  earlier weights and is **not** silently changed without calibrated A/B.

### 8. Copy editor

- **Sole objective:** make an *already approved* article accessible and
  navigable without changing the reporting, and never assume image rights.
- **Inputs:** editor-approved article hash, exact source URLs and permissions,
  approved photos if independently licensed, publication metadata and format.
- **Outputs:** immutable text fingerprint, verified canonical source links,
  attribution/alt-text/right-reference manifest, accessible output preview,
  copy issues and final package digest.
- **Rubric, 100:** link/source fidelity 30, no semantic drift 25,
  accessibility 20, verified rights 20, layout quality 5.
- **Hard gates:** prose or headline mutation -> editor re-review; missing,
  altered or referral-contaminated source links -> HOLD; photo without
  validated rights reference, alt text or credit -> omit/HOLD; HTML should
  not be confused with source-verification status.
- **Evaluation:** deterministic tamper and malformed-URL tests; link
  clickthrough/404 checks; human accessibility and rights spot checks.
- **Status:** `copy_preflight.py` now checks structural text/link invariance,
  rights references and scheme; **does not** render HTML or verify license
  records, so its success must be called a *preflight*, not copy approval.

### 9. Audience diagnostic panel

- **Sole objective:** find avoidable clarity/citation defects cheaply;
  never manufacture a metric of public interest using fictional readers.
- **Inputs:** copy-edited shadow article and source counts, separately
  collected consented genuine feedback once available.
- **Outputs:** transparent heuristics for headline length, market-centric
  framing, thin explanations, length and attribution; suggestions marked
  `synthetic_structural_heuristics`, no publication authority.
- **Rubric, 100:** truthful method labeling 35, actionable defects 30,
  low false-alarm burden 20, bounded cost 15.
- **Hard gates:** never block an evidence-correct story merely because a
  simulated persona disliked it; no panel reweight from agent feedback;
  real feedback at >=30 respondents may suggest modest weights **only after**
  consent, representative checks and owner review.
- **Evaluation:** correlation with real readability interviews, genuine
  opens/retention and human editor usefulness; no synthetic engagement proxy.
- **Status:** eight cheap static heuristics implemented; no actual human
  panel or predictive utility demonstrated.

### 10. Release editor

- **Sole objective:** provide a genuinely independent final legal/ethical
  and factual checkpoint with **asymmetric risk**: a false publication may
  do far more harm than a delayed article.
- **Inputs:** exact final article hash, reviewed human claim matrix and
  reference, links/assets/copyright approval, risk tier, logged editorial
  signoff and outstanding correction/complaint history.
- **Outputs:** detailed `HOLD`, `RETURN` (once) or
  `PENDING_OWNER_APPROVAL`, with fingerprint and factual-review ID; owner
  approval is its own subsequent step.
- **Rubric, 100:** critical fact prevention 35, sensitive-risk handling 25,
  version/citation integrity 20, rights/compliance 10, decisive reason codes 10.
- **Hard gates:** source-structural or model approval cannot stand in for
  independently verified facts; no human review token for the *same exact*
  article digest -> HOLD; any high-risk/unknown risk -> HOLD; one failed
  release return -> HOLD; no implicit publishing credentials.
- **Evaluation:** seeded fact/risk failures, revision-fingerprint attacks,
  independent editor agreement and production corrections by severity.
- **Status:** controller now requires human fact-check reference and hash
  match, low risk and separate owner authorization; **authentication and the
  actual fact-checking service are not integrated**.

### 11. Librarian

- **Sole objective:** preserve a private, comprehensible, tamper-evident
  history of decisions, evidence versions, spikes, rework and corrections.
- **Inputs:** each typed transition, role version, source/copy hashes,
  quantitative scores, review dispositions, actual externally labeled
  outcomes and resource spend.
- **Outputs:** searchable case/version graph; source and quote lineage;
  spike/hold analysis by reason, time and category; actionable audit files
  without PII/raw unlicensed content in public repositories.
- **Rubric, 100:** lineage completeness 30, privacy 25, audit integrity 20,
  faithful metrics 15, retrieval/retention 10.
- **Hard gates:** never treat status reason strings as validated quality
  labels, never quietly overwrite a spiked version, never expose raw sources
  in Git or public dashboards; preserve correction/retraction links.
- **Evaluation:** replay completeness, tamper detection, record retention and
  incident reconstruction drills; separate security/rights assessment.
- **Status:** SQLite event hash chain exists; no signed append-only service,
  user access controls or complete artifact/feedback archive.

### 12. Overseer / mediator

- **Sole objective:** identify *causal recurring process failures* and propose
  measurable changes; it may not become an unaccountable publisher or editor.
- **Inputs:** operational event counters **separately** from externally
  reviewed, distinct human editorial cases with reviewer/evidence provenance,
  cost and latency, audience outcomes and frozen baseline versions.
- **Outputs:** (a) bounded auto retry/backoff only; (b) versioned, fully
  evaluated bespoke prompt/rubric/routing proposal for owner accept/reject;
  (c) conceptual study; explicit confidence, sample size and rollback plan.
- **Rubric, 100:** correct failure attribution 30, independent evidence 25,
  safe authority limits 20, out-of-sample improvement 15, traceability 10.
- **Hard gates:** repeated model self-scored `quality_pass` events yield **no
  grade**; >=20 unique human-editor-attested cases can compute only a
  *provisional/unverified* grade until reviewer identity is authenticated;
  duplicate cases cannot inflate samples. No auto changes to story selection,
  truth thresholds, persona weights, fact policy, prompts or publication.
- **Evaluation:** false-change recommendation rate, offline held-out
  regression and rollback, production incident reoccurrence, net edit-hour
  reduction and critical safety escapes.
- **Status:** self-grade laundering fixed in `oversight.py`; reviewer identity
  authentication, causal experiment attribution and formal grade publication
  remain **future work**.

## Workflow and authority gates: revised wire protocol

| Transition | Required artifact/decision | Hold or return if missing |
| --- | --- | --- |
| Quant -> Topic Lead | dated, unit-consistent `QuantitativePitch` | bad quote, missing comparison, low depth |
| Topic Lead -> Investigator | GO >=65 plus topical hard gates, versioned source/coverage packet | vague angle, unjustified news peg, unresolved source problem |
| Investigator -> Pitch Verifier | 1–3 falsifiable pitches and claim/quote/source matrix | fabricated alternative, no counterclaim, empty provenance |
| Verifier -> Chief Editor | every pitch checked, zero unresolved work on accepted pitch | accept-with-issues, unsupported claim, duplicate/missing review |
| Chief Editor -> Writer | exact headline, selected pitch, instructions, `requested_work=[]` | extra research requested, no defensible reader promise |
| Writer -> Fact Verifier | linked factual paragraphs, no headline rewrite | uncited/asserted material, invented quote, invalid length |
| Fact Verifier -> Quality Review | one clean verdict for every paragraph | any unresolved article-level or paragraph issue |
| Quality -> Copy | bounded human/editorial draft acceptance | score-only self approval, unsupported original value |
| Copy -> Audience | exactly matching approved article digest, canonical links, rights record | tamper, referral rewrite, unlicensed image or missing source |
| Audience -> Release | diagnostic recorded, not necessarily favorable | only if no diagnostic exists; synthetic dislike never vetoes |
| Release -> Owner | low risk plus authenticated future human factcheck of exact final digest | unknown/high risk, stale human review, missing signoff |
| Owner -> Manual publish | explicit owner approval for that version | default HOLD; publishing credentials unavailable |
| Any stage -> Librarian | stable case ID and reasoned event | store private, protect raw allegations and PII |
| Overseer -> Changed policy | demonstrated held-out improvement, owner signoff except bounded retry | self-grade, insufficient evidence, runaway recursion |

### Suggested finite newsroom state machine

The existing `WorkflowController` is the deterministic authority. A human
reporter can continue manual research outside the loop; the machine should
re-enter only after the new sources and tickets have been captured and
verified. A specific `requested_work` must **never** be silently cleared by
rerunning the same packet. Model errors, cost overrun, unavailable reviewer
or ambiguous judgment should leave an explicit terminal HOLD with retry
criteria. `SPIKE` means editorially rejected with archived rationale; `HOLD`
means open and awaiting a measurable condition.

## Quantifying success without optimizing nonsense

The scoreboard should not be "how many agents scored 90/100". Scorecards
must be externally labeled and stratified. Recommended weekly newsroom KPIs:

1. **Story discovery:** interesting new stories surfaced per 100 valid
   category-balanced market changes, recall of important missed topics, and
   duplicate burden on the topic desk.
2. **Reporting:** independently corroborated original facts per commissioned
   dossier, number of verified versus unsupported causal theories, time to
   evidence and percentage of cases held for missing sources.
3. **Editing:** blinded readers' comprehension and interest; headline clarity;
   original value over wire coverage; actual rewrites and edit-time costs.
4. **Safety:** unsourced proposition rate, quote/context errors, corrections
   per published article with severity, high-risk holds, source rights and
   after-approval drift detected.
5. **Economics:** human editor minutes, model calls/tokens, source access
   cost and latency per accepted *factual* article; operational reliability.
6. **External validity:** real reader outcomes, newsletter opens/retention,
   expert editor scores and source complaints, with opt-out and privacy.

Use a **held-out, chronologically split**, category-stratified set of 100+
market leads and 20+ real editorial drafts, alongside deliberately injected
misinformation and source-tampering cases. Freeze and version the rubric first.
Never optimize solely on the articles that passed; measure false negatives
and the outcomes of spiked/held ideas. ML remains a challenger until human
quality labels, time-safe feature capture and a prospective trial exist.

## Implementation decisions from this audit

- **Changed and tested:** investigator prompts now seek disconfirmation and
  allow one defensible angle; verifier cannot `accept` with outstanding work;
  chief editor's reporting requests cause an actual HOLD; writer, fact
  verifier and quality-reviewer prompts are source-first and concrete.
- **Changed and tested:** the copy desk produces a hash-bound source/link
  artifact preflight and rejects article edits, unsafe/altered links and
  unsourced/unattributed images.
- **Changed and tested:** release transitions require consistent article
  fingerprint, human fact-check reference and a separate owner step.
- **Changed and tested:** letter grades no longer consume unverified
  `quality_pass` ledger reason codes; externally supplied human labels are
  deduplicated and can yield only indicative grades without authentication.
- **Deliberately not changed:** Topic Lead 65/100 weights, quantitative
  category thresholds and quality-review score weights. There are no reliable
  independently labeled observations with which to justify tuning them yet.
- **Unbuilt, highest priority:** source-acquisition service with capture
  lineage; actual archive-coverage index; authenticated human review/copy
  rights workflow; version-linked private dossier store; human outcome labels;
  error/corrections process; real audience research and production monitoring.

## Relevant editorial and agent standards

- AP News Values and Principles: accuracy, correction, attribution, original
  reporting and independence.
- Reuters Trust Principles and Journalistic Standards: verification,
  transparent correction, separation of editorial from commercial influence.
- OpenAI agent orchestration, guardrails, tracing and independent evals:
  bounded role responsibilities and measurable outcomes.
- NIST AI Risk Management Framework: Govern, Map, Measure and Manage;
  independent risk evaluation and documented accountability.

This playbook is a **critical engineering draft** for Nolan's forthcoming
agent-by-agent edits, not a claim of enterprise certification. No real article
was published, no trading or affiliate action was taken, and no paid model
service was invoked by this audit.
