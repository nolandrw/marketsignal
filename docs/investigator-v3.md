# Investigator v3 — source-first, two-tier autonomous research contract

**Status, 2026-11-04:** Implemented and passing **offline structural tests**. This is
an opt-in private shadow component, **not yet the active investigator in the
newsroom controller**. No unattended public-source adapter, live language-model
test, independent source-entailment verifier, calibrated thresholds or publication
authorization exists in this implementation.

## Mission and editorial independence

Investigate the *real-world question* commissioned by Topic Lead, not the
prediction-market movement or Topic Lead's suggested causal narrative. Seek
credible evidence against the starting hypothesis. The investigator may reframe
the assignment when evidence warrants it, may **HOLD** work that needs further
records, and may **SPIKE** a thesis that the research defeats. An unrelated
new story is **not** independently commissionable: return it for Topic Lead
triage. A well-supported negative result is successful reporting, even with
no article pitch.

**Authority:** bounded, read-only public searches and permitted captures.
No interviews, contact with subjects, authenticated portals, payments, trades,
outbound messages, image licensing, private data access or publication. Model
text never grants authority. The researched source is evidence of a statement,
not automatic proof of the statement's truth.

## Assignment and research handoff

The typed `InvestigatorAssignment` contains:

1. Case ID, as-of timestamp, reader-facing research question, commissioned
   Topic Lead angle, Topic Lead GO and numeric triage score.
2. Prior-coverage summary and explicit outstanding research questions.
3. Up to 15 `ResearchCapture` seed sources with HTTPS link, publisher, true
   origin key, publication and capture timestamps, source classification and
   a substantive bounded excerpt.

The `assignment_from_topic_lead` bridge takes an explicit `angle_id`, checks
the GO, story ID and selected angle, and rejects
mismatches between the Topic Lead source metadata and trusted captured
material (URL, publisher, published time, origin and source category).
It carries missing prior-coverage review as an explicit pending research task.
It never elevates metadata-only article leads into verified documents. The
actual newsroom controller **does not yet invoke this bridge**.

## Two-tier process and deterministic gates

| Phase | Intended budget | Required outcome | Stop conditions |
|---|---|---|---|
| Intake | Prior Topic Lead GO ≥65, source manifest, disclosed coverage status | Accept a bounded question and authentic evidence seed | No GO, missing/wrong captures or invalid angle → HOLD |
| Preliminary | About 2–4 min; 1–3 queries, max 4 captures each | Score *potential reader understanding*; name rival explanation and discriminating test | Model HOLD/SPIKE respected; score below 70 or any critical criterion `none` → HOLD |
| Deep reporting | About 10–15 min; 1–5 further queries, max 4 captures each | Compare original reporting, chronology, coverage and contradictory evidence | Budget failure, inaccessible records or no new deep evidence → HOLD |
| Dossier | Up to 30 distinct captures total and 8 search calls | Source-linked claims, dates, rival/null theories, prior coverage context, 0–3 pitches | Malformed/unsourced dossier, future dates, inadequate origin diversity, unreviewed new case, completed score below 75 → HOLD |
| Verification handoff | Private only | `ready_for_verifier` **provisionally**, or explained HOLD/SPIKE | Never auto-publish; independent editorial and fact verification remain necessary |

**Implemented limits are query/capture counts**, not actual stopwatch or
provider monetary ceilings. The 2–4 and 10–15 minute estimates are planning
targets only. A production controller must add elapsed-time, token and dollar
budgets and trustworthy provider instrumentation.

The primary **preliminary hard gates** after a model requests deep research:

- Overall provisional score ≥70/100.
- `reader_question`, `credible_evidence_path`,
  `reader_context_gain`, `specific_development`,
  `discriminating_test` and `affected_parties` cannot be `none`.
- At least one captured non-comment source must exist, along with a concrete
  discriminating test of at least 25 characters and 1–5 bounded next queries.
- A model can voluntarily HOLD or SPIKE regardless of its reported score.

The **completed hard gates** include: all 15 criterion statuses and evidence
references; only known source/claim IDs; material findings citing non-comment
sources; dated non-future chronology; hypotheses linked to claims; explicit
prior-coverage context and departure reason; 0–3 pitches. A verifier-ready dossier
requires ≥3 findings, ≥2 dated timeline events, ≥2 distinct source origins,
≥1 evidence-linked newspaper pitch, and completed score ≥75/100. Originality or
accuracy is **not** established by passing these structural conditions.

## Rubrics: precisely defined scoring dimensions

Each subcriterion receives `none` (0%), `partial` (50%) or `full` (100%) of its
weight. `none` means absent, contradicted or merely asserted; `partial` requires
a demonstrable part with a specific gap; `full` needs the described outcome
substantiated by linked evidence. Each score must include an explanatory
rationale and registered source/artifact identifiers. A high total cannot
override a mandatory gate. These are *model self-scores*, not an independent
editorial grade, and should later be calibrated on blind human reviews.

### Preliminary: reader-understanding *potential*, not article readiness

| Dimension | Subcriteria and maximum points | What merits credit |
|---|---|---|
| Potential reader context · 30 | Reader question 10; credible evidence path 10; reader context gain 10 | A useful question, credible research path and an opportunity to synthesize existing or new information clearly |
| Story potential · 25 | Specific development 10; useful story angle 10; reader premise 5 | An independently dated real-world development and an honest, helpful audience-facing explanation, regardless of prior outlets' coverage |
| Testability · 20 | Alternative explanation 8; discriminating test 8; abandonment condition 4 | A serious rival/null account, a concrete differentiating check and an observable reason to abandon the thesis |
| Significance · 15 | Affected parties 5; impact magnitude 5; timely relevance 5 | Specific exposed people/institutions, proportionate magnitude and why the question matters *now* without relying on betting-market excitement |
| Feasibility · 10 | Source access 4; bounded scope 3; ethical access 3 | A lawful reachable record/source, a test achievable within budget and explicit privacy/licensing/allegation safeguards |

### Completed: quality of actual investigative work

| Dimension | Subcriteria and maximum points | What merits credit |
|---|---|---|
| Evidence integrity · 25 | Claim provenance 10; timeline integrity 8; independent origins 7 | Traceable attributed evidence, correctly dated sequences and meaningful source independence |
| Evidence synthesis · 25 | Supported findings **or negative result** 10; coverage synthesis 10; reproducible analysis 5 | Credible account of the development, accurate context and upstream attribution, and retraceable methods; exclusive facts are not required |
| Disconfirmation · 20 | Alternative theories 6; actual disconfirmation 10; residual uncertainty 4 | Real plausible rival accounts, completed counterchecks and clearly preserved uncertainties; merely suggesting a test does not qualify |
| Reader/editorial value · 20 | Concrete consequences 8; defensible decision 8; contextual timeliness 4 | Specific stakes, an evidence-driven publish/HOLD/SPIKE recommendation, and factual context for why now |
| Efficiency and documentation · 10 | Source log 4; resource proportionality 3; actionable tickets 3 | Query/capture logs and dead ends, proportionate effort for information gained and outstanding checks with sources plus revisit triggers |

`marketsignal/investigator_v3.py` supplies these *individual definitions* to
both evaluation stages as `rubric_contract`, while the model gateway provides
stage instructions and strict structured response schemas. Do not turn these
rubric outcomes into a mandatory sequence of identical search clicks: the
research strategy should remain evidence-responsive.

## Structured dossier and audit trail

Every run returns a final disposition, both available rubric reports, a
source manifest with source identifiers, timestamps, origin, kind and excerpt
SHA-256, the bounded queries and per-query trace, and `publication_enabled:
false`. Completed dossiers contain findings with claim IDs and source IDs,
timestamped chronology, alternative hypotheses with pro/con claim links,
prior coverage for attribution and context, open questions, a departure classification
and 0–3 pitches. Source content is treated as untrusted input; claims are
**not** cryptographically or semantically certified by hashes or IDs.

## Test executed: offline adversarial contract evaluation

Commands:

```bash
python -m unittest discover -s tests -q
python -m compileall -q marketsignal tests
python -m marketsignal newsroom-v3-demo
```

Results on this branch:

- **174/174 unit-test methods passed**, including **six new v3 methods**;
  one of those runs an additional **28-case adversarial scenario matrix**.
  These are scripted contract checks, not a sample of 28 actual reported stories.
- **28/28 synthetic adversarial scenario branches** matched their expected
  routing: **3** `ready_for_verifier`, **23** HOLD, **2** SPIKE.
- Confirmed protection against unknown citations, metadata drift across
  the handoff, non-record source promotion, missing criteria/test plans,
  low scores, future-dated captures/events, duplicate source identifiers,
  unbounded queries, no newly captured deep evidence, suspicious market-led
  headlines and unrelated story promotion.
- One fictional coastal-barrier story was reused in all 28 variants; **no
  external source was fact-checked**. The scores in the scripted test were
  deliberately assigned to exercise policy, not generated by an LLM or
  judged by professional editors.
- The existing `newsroom-v3-demo` completed its **fictional legacy flow**
  and ended `held` at the owner/fact-check publication gate. It does **not**
  call the new Investigator v3 orchestration and cannot establish that the
  new v3 stage works with live records or model outputs.

## Known weaknesses and release criteria

1. **Real research remains unconnected.** A `ReadOnlyResearchProvider` interface
   exists; the current source discovery utilities yield leads, while separate
   capture logic has publisher allowlists and robots constraints. A vetted
   adapter must connect searches to actual lawful page captures without
   treating search-result metadata as evidence.
2. **Independent semantic verification remains missing.** ID/URL/clock checks
   prevent some failure modes, but a cited excerpt may still fail to support
   a claim; two sites may reproduce the same upstream reporting; a model may
   overgrade its own work. The next verifier must read originals independently.
3. **Model-run viability is untested.** Three new stages use strict JSON and
   large 15-criterion scorecards; no paid model calls have been made.
   Test truncation, consistency, long-context leakage and ability to score
   a genuine negative conclusion. If dossier outputs exceed token limits,
   split factual reporting from independent scoring instead of raising limits
   without cost analysis.
4. **Thresholds are policy hypotheses.** 70/75 and half-credit anchors are
   sensible explicit gates but uncalibrated; measure false commissions and
   missed stories on a varied human-labeled evaluation set before adjusting.
5. **Time/budget/error telemetry is partial.** Calls and captures are counted;
   actual wall time, tokens, dollars, cache consistency and provider retries
   need production instrumentation. Preserve immutable original URLs and
   timestamps separately from excerpt hashes.
6. **Workflow integration remains pending.** The Topic Lead handoff helper
   exists but the active newsroom dispatcher uses its previous investigator
   path. The release gate must continue to require trusted external review,
   owner approval and audit trail.

**Recommended next sequence:** connect a compliant read-only research adapter
and v2 handoff in a feature-flagged shadow branch → run 15–25 *different*
source-grounded, editorially blind cases (including solid negatives, rumor,
duplicate coverage, low-volume signals and inaccessible documents) → test
actual model JSON/cost/time behavior with explicit spending permission → have
an independent verifier grade citation entailment, independence and omissions
→ tune the rubric and gates against labeled false-positive/false-negative
rates → shadow-run end to end with no automatic publishing.
