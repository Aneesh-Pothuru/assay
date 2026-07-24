# Limits

This v0.1 is intentionally an honest reference implementation.

## Implemented and verified

- Keyless, deterministic 100-sample replay and expected blocking gate.
- Content-addressed datasets and scorers; unversioned input refusal.
- Hard failure on cross-scorer-version comparisons.
- Paired confidence interval, Bonferroni correction hook, and per-sample diff.
- Structured JSON and static HTML reports.
- Four world-model scorer contracts on a CPU-only synthetic gridworld.
- `UNDETERMINED` is part of the verdict vocabulary. The bundled demo's
  undetermined rate is 0%; synthetic tests cover the abstention path.

## Not supported or not yet measured

- No Gemini/Groq/Ollama live runner is included. No provider reliability,
  latency, cost, or nondeterminism claim is made.
- No public world-model checkpoints or external benchmark adapters are
  included. The target of two public checkpoints is not met.
- The four `wm/*` implementations validate interface and invariants on a tiny
  deterministic fixture; they are not research-grade perceptual metrics.
- No Kaggle/Colab job or public `safe_horizon` measurement is shipped.
  `safe_horizon` is a launch/P1 artifact, not claimed here.
- Seeded-regression detection is exactly 100% on the bundled deterministic
  fixture with 0 false positives. That is a regression test, not evidence of
  performance on naturally occurring failures.
- The confidence interval is a normal approximation over paired sample
  deltas. Small-sample/bootstrap and dependency-aware inference are deferred.
- Parquet/DuckDB persistence is represented by JSON artifacts in the
  dependency-free MVP. The run store is SQLite-first, but the demo uses an
  ephemeral store and does not require a persistent service.
