# MarketSignal story thesis handoff v1

**Status:** implemented as a fail-closed structural gate in the local/shadow
feature workflow and the curated field-trial runner. Not a live model agent,
independent fact check, editorial certification or autonomous publication route.

## The editorial failure we are correcting

The original Texas field trial was factually cautious but did not contain an
interesting story: "we cannot infer voter preferences from turnout" is a
research limitation, not a complete newspaper narrative. It nevertheless
passed the older technical rubric because that rubric checked headline length,
the absence of market jargon and citation links. The result was a structural
pass and an editorial miss.

The newsroom must distinguish four different objects:

1. **Signal:** a valid, timestamped trading anomaly or other reporting lead;
   it is not the article and does not prove a cause.
2. **Topic:** the event, people and consequences potentially worth covering.
3. **Story pitch:** a falsifiable explanation or conflict with news peg, prior
   expectation, surprise, stake, counterevidence and incremental value.
4. **Commissioned angle:** the chief editor's selection after the investigator
   and verifier have exchanged evidence. This carries an editor-owned headline
   and rationale; the writer does not silently substitute a new angle.

## Required handoffs

| From | To | Artifact | Gate |
| --- | --- | --- | --- |
| Quantitative triage | Topic lead | Market/volume/time-window trace | Real and recomputable signal; otherwise shadow only |
| Topic lead | Investigator | News peg, background questions, duplication concerns | People/institutions and material stakes identified |
| Investigator | Verifier | At least two `StoryPitch` alternatives, exact claim IDs, contrary IDs, source provenance, source gaps | Missing evidence marked; forum speculation only a lead |
| Verifier | Investigator | Contradictions, unsupported causal arrows, quote failures, independent-origin issues | Rework bounded by loop/timeout budget; can recommend spiking |
| Investigator/verifier | Chief editor | Verified candidate pitches and explicit open questions | Never claim semantic verification from string checks |
| Chief editor | Writer | `EditorialSelection` with selected pitch ID, editor-owned title and why chosen | A selected narrative has development, prior view, public stakes and counterpoint |
| Writer | Editor/verifier | Paragraphs bound to claims and sources, proposed alternative headlines as separate requests | Change in thesis/title requires new selection; no invented detail |
| Copy and release editors | Owner | Structured audit, substantive editorial feedback, residual risks | Independent semantic check and owner approval before release |

The handoff is `StoryPitch` plus `EditorialSelection` in
`marketsignal/story_thesis.py`. Both the live-shaped feature pipeline
(`feature_story.py`) and the offline field-trial pipeline (`field_trial.py`)
validate that handoff. An absent editorial decision holds the story. A
headline can now legitimately differ from the investigator's first suggestion
when the chief editor explicitly selects it.

## Rules for investigating a story, not a topic

Each pitch must provide:

- `thesis`: one sentence explaining what is happening and why it matters.
- `conflict`: identifiable actors, institutions or competing interests.
- `surprise`: what was reasonably expected before, and what contradicts it.
- `why_now`: the material, verifiable development that makes it timely.
- `stakes`: people, institutions, resources or policy outcomes affected.
- `original_value`: what would be newly learned *beyond existing coverage*.
- `supporting_claim_ids` and `contrary_claim_ids`: evidence relationships.

The verifier must try to falsify each pitch, challenge causal attribution,
deduplicate syndicated reporting, confirm quote text, distinguish measured
sentiment from online discussion and label unproven theories. It must not
"solve" risk by replacing every investigative thesis with "we do not know."
An interesting, accurately qualified conflict remains a valid story.

The editor can select, return for research, spin into a different assignment,
or spike the pitch. One headline must not be frozen before the research. A
change after commissioning is permitted only through another explicit
editorial decision and a fresh verification pass.

## Rubrics and truth in evaluation

The **story-value scorecard** is an editorial judgment rubric, not a
deterministic classifer. Weighting is encoded in `RUBRIC_WEIGHTS`:

| Dimension | Maximum |
| --- | ---: |
| Compelling central conflict | 20 |
| Public significance and stakes | 20 |
| Genuine surprise or reversal | 15 |
| Specificity, people, institutions | 15 |
| Support and counterevidence | 15 |
| Original added value | 10 |
| Ability to sustain meaningful narrative | 5 |
| **Total** | **100** |

Working target: 90/100 from an **independent** editorial review, with no fatal
factual defect. Below 75: spike or re-angle. From 75–89: return for reporting.
These numerical thresholds are working hypotheses until real-reader feedback
provides calibration. A structured agent rating itself 93 is not objective
evidence of quality. Keep score provenance and independent blind reviews.

Separately, the **structural provenance rubric** in `field_trial.py` checks
the presence and consistency of the handoff and source-linked article. Its
100/100 result is *not* a statement about narrative excellence, originality,
truth or permission to publish. These remain explicit false flags.

## Texas re-run (pre-election shadow)

- **Old angle:** record turnout leaves voter identity uncertain. Spiked for
  insufficient narrative payoff despite passing the previous technical test.
- **Alternative A:** a costly Senate fight tests Texas Republican dominance.
  Selected provisionally because it ties a 32-year electoral streak, late
  polling, rival campaign messages, spending and the candidate's own words.
- **Alternative B:** economic and religious populism versus conservative
  identity. Worth investigating, but already substantially covered elsewhere.
- **Alternative C:** early-vote mystery. Useful sidebar or explainer but not
  strong enough to carry the piece.

The revised shadow has an editor-owned headline and a distinct narrative
spine. It still relies on existing AP, Texas Tribune, University of Texas and
government records; it is not original independent reporting. The archived
Polymarket quote did **not** show a qualifying move. No model has been
connected to autonomously produce these editorial choices and neither the
article nor its narrative quality has received independent semantic review.
The correct release decision remains **HELD**.

## Adversarial checks

The tests now require: multiple pitches; a selected and rationalized angle;
development, prior view and stakes linked to real claim IDs; an explicit
counterclaim; a non-market headline; an editor-approved final headline; and
separate release approval. They reject the original "raises a question"
headline pattern as an additional weak-form lint signal, but a human editor
can still override style heuristics with documented rationale in a future
version. Deterministic tests cannot prove compelling prose.
