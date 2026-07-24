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

