# Limits

This v0.2 is intentionally an honest local reference implementation.

## Implemented and verified

- Keyless, deterministic 100-sample replay and expected blocking gate.
- Content-addressed datasets and scorers; unversioned input refusal.
- Hard failure on cross-scorer-version comparisons.
- Paired confidence interval, Bonferroni correction hook, and per-sample diff.
- Structured JSON and static HTML reports.
- Keyless local HTTP/CLI path for verified run ingestion, durable SQLite
  comparison evidence, health/readiness, and a packaged same-origin operator UI.
- Immutable run IDs, idempotent retries, strict JSON, request IDs, basic
  response hardening, and structured 4xx contract errors.
- Four world-model scorer contracts on a CPU-only synthetic gridworld.
- `UNDETERMINED` is part of the verdict vocabulary. The bundled demo's
  undetermined rate is 0%; service tests persist and retrieve an empty-pair
  undetermined record with unavailable values encoded as JSON `null`.

## Not supported or not yet measured

- No Gemini/Groq/Ollama live runner is included. No provider reliability,
  latency, cost, or nondeterminism claim is made.
- The HTTP service is local-first and has no authentication, authorization,
  TLS, tenant isolation, rate limiting, or horizontal coordination. Loopback is
  the default; non-loopback use requires a trusted external security boundary.
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
- Parquet/DuckDB persistence is not implemented. The installed service uses
  SQLite; the static Pages demo remains an embedded replay with no persistence.
- The SQLite schema is single-node and records a schema version, but no
  automated migration framework is shipped yet.
