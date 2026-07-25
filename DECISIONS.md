# Decisions

## 2026-07-24 — dependency-free P0

The replay path uses only the Python standard library so a clean clone works
keylessly and offline. Optional provider, Parquet, DuckDB, and PyTorch paths
are deferred and are not simulated.

## 2026-07-24 — expected gate exit

The brief requires `assay demo` to produce `BLOCKED` and exit `1`, while the
portfolio requires `make demo` to pass. The CLI preserves exit `1`; the
Makefile asserts that result and exits successfully.

## 2026-07-24 — P0 world-model scope

The brief labels all four world-model scorers P0 but schedules them at v0.2.
This repo includes deterministic CPU reference implementations now. Public
checkpoint adapters and the P1 `safe_horizon` publication remain deferred.

## 2026-07-24 — statistical method

The comparison engine uses paired deltas, a two-sided 95% normal-approximation
interval, and a Bonferroni-adjusted alpha when multiple metrics are requested.
The method is explicit in the report rather than implying universal validity.

## 2026-07-25 — local service is the operational path

The public Pages experience remains a static, embedded replay. The installed
package now owns the mutable path: verified run+scorer envelopes, immutable
SQLite records, actual comparison-engine execution, durable evidence, and a
same-origin operator UI. HTTP and CLI call one `EvaluationService` so verdict
semantics cannot drift between interfaces.

## 2026-07-25 — local security boundary

The dependency-free HTTP service binds to loopback by default and deliberately
does not imply hosted multi-tenant readiness. Non-loopback binds emit a warning;
authentication, TLS, authorization, rate limiting, and tenant isolation remain
external responsibilities and are named in `LIMITS.md`.

## 2026-07-25 — immutable records and deterministic comparisons

Dataset/scorer contracts and run IDs are immutable. Identical ingestion retries
are idempotent; conflicting reuse is an error. Comparison IDs derive from the
two immutable run IDs and inference parameters, so a retry returns the original
timestamped evidence rather than manufacturing duplicates.
