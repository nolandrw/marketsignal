# Quality gates and evaluation backlog

The CI test suite covers parsing, malformed/missing data, price deltas,
ineligible liquidity, missing baselines, idempotent collection, snapshot
retention, stale-run recovery and safeguards around production credentials.

## Phase 1: market-data quality

- [x] Clear data-source conventions (`outcomePrices` rather than bid/ask midpoint)
- [x] Immutable stored price observations
- [x] Rejection of missing numeric data and closed/expired markets
- [x] 1h and 24h rule-based detector
- [x] Duplicate signal cooldown
- [x] Real read-only API connectivity and schema smoke test
- [x] Mark incomplete collector runs as interrupted after a bounded interval
- [x] Production fails closed rather than silently using ephemeral SQLite
- [ ] Historical price backfill / recovery of missing observations
- [ ] Real PostgreSQL integration test in a disposable database
- [ ] Spread / stale quote quality gates
- [ ] Validated market category taxonomy
- [ ] Standardized settlement-state exclusions
- [ ] Historical evaluation of ranking precision

## Phase 2: agent quality (offline scaffolding implemented)

- [x] Independent candidate, evidence, numeric-fact and claim contracts
- [x] Executable synthetic triage → researcher → writer → verifier → editor
- [x] Unknown/high-risk, causal-claim and attributed-social-speculation holds;
  no publisher attached
- [x] Unit cases for bad math, evidence provenance, agent failure and retry ID
- [ ] Actual primary-source retrieval and rights-compliant evidence archive
- [ ] Social-source coverage, independence, narrative-amplification and
  source-deletion compliance tests before any public speculative context
- [ ] Model writer, independent verifier and versioned prompt registry
- [ ] Calibrated evaluation of models and story usefulness on historical cases
- [ ] Idempotent publication state machine and operational kill switch

Create 100 golden cases covering genuine and spurious repricing, thin books,
time-window mistakes, event clustering, contract-rule mismatches, bogus URLs,
misleading external text, unknown catalysts, and high-risk allegations.

Target before any unattended explanatory publication:

- 100% recomputable numeric claims from stored observations.
- 100% resolvable source links for cited material facts.
- Zero knowingly fabricated causal explanations in the golden set.
- >=90% human-rated editorial usefulness on a documented rubric.
- No duplicate publication for a repeated workflow execution.
- A reversible publishing pause, exception log and correction mechanism.

Independent model review alone does **not** meet these gates. Numeric
assertions, source access and publication permissions require conventional
software checks. External source text is untrusted input.

## Portfolio report card

Publish only measured metrics: collection coverage, candidate precision,
articles drafted/accepted, source failure rate, confirmed corrections,
replay test pass rate, dollar cost per accepted article, and time to publish.
Use the same frozen historical cases to compare single-model and multi-agent
workflows; the latter should only be retained if it improves outcomes.
