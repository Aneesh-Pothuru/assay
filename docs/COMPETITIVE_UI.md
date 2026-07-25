# ASSAY competitive UX review

Reviewed 2026-07-24 against current primary product documentation. The goal was
not to reproduce an experiment tracker. It was to identify the shortest,
most defensible path from a model change to a merge decision.

## Products and patterns

| Product / standard | Relevant surface | Useful pattern | ASSAY response |
| --- | --- | --- | --- |
| [Braintrust experiment comparison](https://www.braintrust.dev/docs/evaluate/compare-experiments) | Baseline comparison, regression sorting, output diff, summary, export, CI | Keep aggregate impact and per-test deltas in one comparison; make the baseline persistent; export the decision artifact. | The bench pairs named runs, exposes mean/delta/CI, links every changed sample to a specimen drawer, and exports/copies the evidence. |
| [Braintrust experiment creation](https://www.braintrust.dev/docs/evaluate/run-evaluations) | Immutable experiment snapshots, local/keyless iteration, repeated trials | A run should be a durable object, and non-final or local runs should be labeled honestly. | ASSAY pins the replay to dataset and scorer hashes and calls the browser experience a deterministic fixture. |
| [Arize Phoenix experiments](https://arize.com/docs/phoenix/datasets-and-experiments/how-to-experiments/run-experiments) | Dataset → task → evaluators → results; sort/filter by score; inspect low-scoring examples and traces | The results table is a debugging doorway rather than a final dashboard. | The sample plate is the dominant second-level interaction and keeps input, expected value, prediction, slice, and transition together. |
| [Arize Phoenix server evals](https://arize.com/docs/phoenix/evaluation/server-evals/overview) | Evaluator input mappings, code and LLM evaluators, traceability from score to evaluator execution | A score needs instrument provenance and a route back to its evidence. | The scorer selector is visibly versioned and the full hash remains in the protocol rail and export. |
| [GitHub status checks](https://docs.github.com/en/enterprise-cloud@latest/pull-requests/reference/status-checks) | Checks expose running/pass/fail state, detailed output, annotations, and links | CI status must be terse at the merge box but deep when opened. | The verdict card is blunt; the rest of the bench provides the detailed run, interval, and sample evidence behind it. |
| [GitHub protected branches](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches) | Required successful status before merge | A gate should map cleanly to a real repository control. | ASSAY retains the existing exit-code contract and ships a ready-to-paste Actions example. |
| [NIST AI RMF Measure](https://airc.nist.gov/airmf-resources/airmf/5-sec-core/) | Measurement uncertainty, benchmark comparison, formal reporting, repeatable TEVV, and documented limits | A governance record needs uncertainty, context, method, and limitations—not only a score. | The site makes confidence interval, version pins, method, scope, and honest limits first-class; the evidence package is designed for independent review. |

## Journey-level findings

### Before a run

- The engineer needs a fast default, not an empty configuration canvas.
- The eval author needs dataset and scorer identity visible before execution.
- The reviewer needs to understand whether the interface is a replay, preview,
  or live provider run.
- The operator needs a clear relationship between the product verdict and a
  required repository check.

ASSAY therefore opens with a filled protocol, visible hashes, a synthetic-fixture
label, and one primary action. Advanced provider configuration is not simulated.

### During a run

- Progress should correspond to real conceptual stages: pin, replay, score,
  infer, gate.
- A reviewer should be able to step the protocol instead of waiting through a
  decorative animation.
- Partial data must not masquerade as a final verdict.

The interactive bench supports full run and manual step modes. Measurements
appear after scoring, uncertainty after inference, and the verdict only at the
gate step.

### After a run

- A merge verdict needs a reason, declared tolerance, and uncertainty.
- Changed cases must be sortable or visually scannable.
- One click should open the exact specimen rather than moving through multiple
  nested screens.
- Review and governance need a portable evidence artifact.

The paired plate supports all/regressed/held/improved filters, each well opens a
specimen record, and the final section copies a review note or exports
structured JSON. A deliberately incompatible scorer profile stops during
pinning, withholds the verdict and export, and offers an explicit compatible-pin
recovery.

## Distinctive visual direction

The product is deliberately **not** another dark analytics dashboard or
editorial score. It is a cool, sterile clinical instrument crossed with a
chain-of-custody dossier:

- white and ice-blue instrument substrates, deep technical ink, cobalt
  reference signals, and red exception marks;
- chromatography lanes for run progress and comparison rather than generic
  glowing gradients;
- circular specimen wells as the primary sample-level navigation;
- condensed technical sans headlines paired with machine-readable Courier
  labels;
- lightly molded controls, inset surfaces, restrained radii, and optical depth
  instead of offset-print shadows;
- claims and scope presented like chain-of-custody annotations.

The metaphor reinforces the product thesis: evaluators are measuring
instruments, samples are specimens, version hashes establish custody, and a
merge verdict is a signed result—not an ambient KPI.

## Deliberate differences

- ASSAY does not present traces because this implementation does not collect
  model traces.
- ASSAY does not offer a live provider playground because the repository does
  not ship provider runners.
- The additional candidate and tolerance states in the static demo are
  deterministic workflow fixtures, not measured external runs.
- “Passed” never means “proven safe”; it means the interval is not entirely
  below the declared negative tolerance under the shown method.
