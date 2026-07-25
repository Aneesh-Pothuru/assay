# ASSAY user journeys

The product loop is:

> Pin the measuring system → compare paired runs → inspect uncertainty → open
> changed specimens → issue or withhold a merge verdict → export the record.

Every journey shares the same run, dataset, scorer, comparison, and verdict
objects. Persona-specific views change the decision emphasis, not the evidence.

## Verdict vocabulary

| Verdict | Meaning | Interface behavior |
| --- | --- | --- |
| `PASSED` | The interval is not entirely below the declared negative tolerance; its upper bound is at or above the boundary. | Show “merge permitted,” the tolerance and interval, remaining changed samples, and the limits of the method. Never say the system is safe or correct. |
| `BLOCKED` | The interval excludes the allowed tolerance in the negative direction. | Show “merge blocked,” attach the exact regressed samples, retain both content hashes, and export a failing CI status. |
| `UNDETERMINED` | The comparison cannot support an inference, for example because no paired samples exist. | Withhold a merge recommendation, explain which evidence is missing, and offer a repair path. |
| Hard error | The comparison contract is invalid, for example different datasets, scorer versions, or sample IDs. | Stop before inference. Name the mismatched object and require a new compatible baseline; do not downgrade this to `UNDETERMINED`. |

## Persona 1 · ML engineer shipping a change

### Trigger

An engineer changes a prompt, model, tool policy, or checkpoint and wants to
know whether it is safe to open or merge a pull request.

### Primary flow

1. Open the evaluation bench from CI or run `assay demo` locally.
2. Confirm the production suite, baseline branch, candidate, scorer version,
   and allowed regression.
3. Run the assay. The interface pins contracts, replays paired samples, scores,
   estimates uncertainty, and gates in visible steps.
4. Read baseline, candidate, delta, and interval as one comparison.
5. Filter the sample plate to “Regressed.”
6. Open each red well to compare request, expected tool, baseline prediction,
   candidate prediction, and score transition.
7. Copy the review note into the pull request and, if appropriate, rerun after a
   fix.

### Success

- `PASSED` is supported by a compatible baseline/scorer/dataset and reviewable
  sample evidence.
- The engineer can explain both the aggregate movement and any individual
  tradeoffs before requesting review.
- CI receives a structured success result.

### Failure / block

- `BLOCKED` names the paired interval and exact changed samples.
- The engineer fixes or explicitly changes the declared tolerance through the
  team’s review process; they do not silently select a more lenient threshold.
- CI exits non-zero.

### Undetermined / invalid

- No paired samples → `UNDETERMINED`; add or repair the fixture.
- Dataset hash, scorer hash, or sample IDs differ → hard error; choose a
  compatible baseline or establish a new baseline.

## Persona 2 · Reviewer deciding whether to merge

### Trigger

A pull request claims an improvement or acceptable tradeoff and includes an
ASSAY status check.

### Primary flow

1. Open the check detail rather than relying on the green/red badge.
2. Verify that the candidate, baseline, dataset pin, scorer pin, sample count,
   and declared tolerance match the pull request’s intended release contract.
3. Inspect the interval and method before the means.
4. Filter to regressions and inspect representative and high-risk specimens.
5. Check whether changed samples cluster in a meaningful slice.
6. Read the scope and limits, then decide whether to accept the evidence,
   request a fix, or ask for a broader suite.
7. Retain the exported evidence with the review.

### Success

- Evidence is compatible, sufficiently scoped, and the interval does not
  establish a regression beyond the pre-declared tolerance.
- Remaining changed samples are understood and explicitly accepted.

### Failure / block

- The interval is entirely below the block boundary, a critical specimen
  regresses, or the selected suite omits the behavior changed by the pull
  request.
- Reviewer withholds approval and links to exact sample IDs.

### Undetermined / invalid

- Insufficient paired samples, missing labels, or an interval too unstable for
  the decision → withhold a recommendation.
- Hash mismatch → reject the comparison itself; never reason from its scores.

## Persona 3 · Eval author maintaining the instrument

### Trigger

An eval author adds examples, changes labels, revises a scorer, or creates a
world-model scoring contract.

### Primary flow

1. Version the dataset content and scorer configuration separately.
2. Validate the scorer on deterministic positive, negative, and abstention
   cases.
3. Register optimization direction and expected output semantics.
4. Run the old and new scorer against a held-out calibration slice.
5. If the scorer changes, publish a new scorer hash and establish a new
   baseline; never compare scores across the boundary.
6. Document covered and uncovered failure modes.
7. Monitor human agreement when using judge models.

### Success

- Deterministic contracts reproduce, changed labels are reviewable, and the
  scorer’s optimization direction and limits are clear.
- Dataset/scorer evolution cannot be mistaken for model movement.

### Failure / block

- Scorer nondeterminism, poor judge/human agreement, leaked examples, or
  ambiguous labels prevent promotion.
- The author keeps the prior scorer version active while repairing the new
  instrument.

### Undetermined / invalid

- Too few labeled cases to estimate agreement or scorer variance → mark the
  scorer experimental and block use as a required gate.
- Cross-version comparison attempt → hard error.

## Persona 4 · Governance / infrastructure operator

### Trigger

An operator must enforce evaluation policy, audit a release, or connect ASSAY
to protected-branch requirements.

### Primary flow

1. Define which ASSAY suites and tolerance policies are required per repository
   or risk tier.
2. Configure the status check as required for the protected branch.
3. Verify the latest commit SHA is the one evaluated.
4. Retain the evidence bundle: run IDs, commit context, hashes, method,
   uncertainty, verdict, sample changes, scope, and limits.
5. Periodically review whether the suite represents deployment conditions and
   whether the metrics still support the intended risk decision.
6. Track exceptions separately from measured passes.

### Success

- Every release has a repeatable go/no-go record tied to immutable inputs and a
  specific commit.
- Policy distinguishes a measured pass from an exception or missing evidence.

### Failure / block

- Required check fails, evidence targets an older commit, a required suite is
  missing, or the configured tolerance violates policy.
- Merge remains blocked until the correct evidence is produced.

### Undetermined / invalid

- Evaluation cannot measure the relevant risk or deployment condition → record
  the gap, require human review or compensating controls, and do not translate
  missing evidence into a pass.

## Static demo journey

The GitHub Pages app is a deterministic interaction model over checked-in
fixture data. It is designed to teach and exercise the real contract:

1. Choose a suite, paired runs, and versioned scorer.
2. Set an allowed regression tolerance.
3. Run all five stages or step through them manually.
4. Watch derived scores and the confidence trace develop.
5. Filter and inspect the sample plate.
6. Observe the verdict change when the declared tolerance changes.
7. Copy a review note or export a structured evidence bundle.
8. Reset and compare another deterministic candidate.

To exercise contract recovery, select the deliberately incompatible
`scorer-v2` candidate and run or step the protocol. ASSAY stops during pinning,
withholds the merge verdict, and keeps evidence export locked. Selecting “Use
compatible pins” restores the default candidate, but still requires a new run
before any verdict or evidence package exists.

The additional candidate profiles are explicitly demo fixtures. The repository’s
measured claim remains the 100-sample, twelve-regression `model-v1` versus
`model-v2` replay generated by the Python implementation.
