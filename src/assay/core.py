from __future__ import annotations

import hashlib
import json
import math
import sqlite3
import statistics
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

from .schemas.loopkit import Run, Sample, Verdict


def canonical_hash(value: Any) -> str:
    payload = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True)
class Dataset:
    samples: tuple[dict[str, Any], ...]
    content_hash: str

    @classmethod
    def create(cls, samples: Iterable[dict[str, Any]]) -> "Dataset":
        frozen = tuple(dict(sample) for sample in samples)
        return cls(samples=frozen, content_hash=canonical_hash(list(frozen)))

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "Dataset":
        if "dataset_hash" not in payload:
            raise ValueError("refusing unversioned dataset: dataset_hash is required")
        samples = tuple(payload.get("samples", ()))
        actual = canonical_hash(list(samples))
        if payload["dataset_hash"] != actual:
            raise ValueError(
                f"dataset hash mismatch: declared {payload['dataset_hash']}, actual {actual}"
            )
        return cls(samples=samples, content_hash=actual)


@dataclass(frozen=True)
class ScorerSpec:
    name: str
    version: str
    config: dict[str, Any]
    content_hash: str

    @classmethod
    def create(
        cls, name: str, version: str, config: dict[str, Any] | None = None
    ) -> "ScorerSpec":
        if not version.strip():
            raise ValueError("scorer version is required")
        config = dict(config or {})
        digest = canonical_hash({"name": name, "version": version, "config": config})
        return cls(name=name, version=version, config=config, content_hash=digest)


class RunStore:
    """Small SQLite-first store for portable run records."""

    def __init__(self, path: str | Path = ":memory:") -> None:
        self.connection = sqlite3.connect(str(path))
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS runs (
                run_id TEXT PRIMARY KEY,
                dataset_hash TEXT NOT NULL,
                scorer_hash TEXT NOT NULL,
                model_id TEXT NOT NULL,
                payload_json TEXT NOT NULL
            )
            """
        )

    def save(self, run: Run) -> None:
        self.connection.execute(
            """
            INSERT OR REPLACE INTO runs
                (run_id, dataset_hash, scorer_hash, model_id, payload_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                run.run_id,
                run.dataset_hash,
                run.scorer_hash,
                run.model_id,
                json.dumps(run.to_dict(), sort_keys=True),
            ),
        )
        self.connection.commit()

    def get_payload(self, run_id: str) -> dict[str, Any]:
        row = self.connection.execute(
            "SELECT payload_json FROM runs WHERE run_id = ?", (run_id,)
        ).fetchone()
        if row is None:
            raise KeyError(run_id)
        return json.loads(row[0])

    def close(self) -> None:
        self.connection.close()


@dataclass(frozen=True)
class Comparison:
    metric: str
    baseline: float
    candidate: float
    delta: float
    ci_low: float
    ci_high: float
    corrected_alpha: float
    regressions: tuple[str, ...]
    improvements: tuple[str, ...]
    verdict: Verdict
    reason: str
    method: str = "paired normal approximation"

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["verdict"] = self.verdict.value
        return result


def compare_runs(
    baseline: Run,
    candidate: Run,
    metric: str = "accuracy",
    *,
    alpha: float = 0.05,
    metric_count: int = 1,
    tolerance: float = 0.0,
) -> Comparison:
    if baseline.dataset_hash != candidate.dataset_hash:
        raise ValueError("cannot compare runs from different dataset versions")
    if baseline.scorer_hash != candidate.scorer_hash:
        raise ValueError("cross-scorer-version diff is forbidden")
    if metric_count < 1:
        raise ValueError("metric_count must be positive")

    base_by_id = {sample.sample_id: sample for sample in baseline.samples}
    cand_by_id = {sample.sample_id: sample for sample in candidate.samples}
    if base_by_id.keys() != cand_by_id.keys():
        raise ValueError("sample IDs differ between runs")
    if not base_by_id:
        return Comparison(
            metric=metric,
            baseline=math.nan,
            candidate=math.nan,
            delta=math.nan,
            ci_low=math.nan,
            ci_high=math.nan,
            corrected_alpha=alpha / metric_count,
            regressions=(),
            improvements=(),
            verdict=Verdict.UNDETERMINED,
            reason="no paired samples",
        )

    ids = sorted(base_by_id)
    paired: list[float] = []
    regressions: list[str] = []
    improvements: list[str] = []
    for sample_id in ids:
        before = base_by_id[sample_id].scores[metric]
        after = cand_by_id[sample_id].scores[metric]
        paired.append(after - before)
        if after < before:
            regressions.append(sample_id)
        elif after > before:
            improvements.append(sample_id)

    baseline_mean = statistics.fmean(base_by_id[item].scores[metric] for item in ids)
    candidate_mean = statistics.fmean(cand_by_id[item].scores[metric] for item in ids)
    delta = statistics.fmean(paired)
    corrected_alpha = alpha / metric_count
    z = statistics.NormalDist().inv_cdf(1.0 - corrected_alpha / 2.0)
    standard_error = statistics.stdev(paired) / math.sqrt(len(paired)) if len(paired) > 1 else 0.0
    ci_low = delta - z * standard_error
    ci_high = delta + z * standard_error
    if ci_high < -tolerance:
        verdict = Verdict.BLOCKED
        reason = "paired confidence interval excludes the allowed tolerance"
    else:
        verdict = Verdict.PASSED
        reason = "regression threshold was not crossed"

    return Comparison(
        metric=metric,
        baseline=baseline_mean,
        candidate=candidate_mean,
        delta=delta,
        ci_low=ci_low,
        ci_high=ci_high,
        corrected_alpha=corrected_alpha,
        regressions=tuple(regressions),
        improvements=tuple(improvements),
        verdict=verdict,
        reason=reason,
    )


def demo_runs() -> tuple[Run, Run]:
    raw_samples = [
        {
            "sample_id": f"sample-{index:03d}",
            "context": {"request": f"select tool for case {index:03d}"},
            "action": "choose_tool",
            "reference": "search" if index % 2 == 0 else "lookup",
        }
        for index in range(100)
    ]
    dataset = Dataset.create(raw_samples)
    scorer = ScorerSpec.create("exact_tool_selection", "1.0.0")
    baseline_samples: list[Sample] = []
    candidate_samples: list[Sample] = []
    for index, raw in enumerate(raw_samples):
        reference = raw["reference"]
        baseline_samples.append(
            Sample(
                sample_id=raw["sample_id"],
                context=raw["context"],
                action=raw["action"],
                reference=reference,
                prediction=reference,
                scores={"accuracy": 1.0},
            )
        )
        regressed = index < 12
        prediction = ("lookup" if reference == "search" else "search") if regressed else reference
        candidate_samples.append(
            Sample(
                sample_id=raw["sample_id"],
                context=raw["context"],
                action=raw["action"],
                reference=reference,
                prediction=prediction,
                scores={"accuracy": 0.0 if regressed else 1.0},
            )
        )
    shared = {
        "dataset_hash": dataset.content_hash,
        "scorer_hash": scorer.content_hash,
    }
    return (
        Run(
            run_id="demo-baseline",
            model_id="model-v1",
            samples=tuple(baseline_samples),
            metadata={"fixture": True},
            **shared,
        ),
        Run(
            run_id="demo-candidate",
            model_id="model-v2",
            samples=tuple(candidate_samples),
            metadata={"fixture": True, "seeded_regressions": 12},
            **shared,
        ),
    )


def world_model_reference_scores() -> dict[str, Any]:
    truth = [(0.0, 0.0), (1.0, 0.0), (2.0, 1.0), (3.0, 1.0), (4.0, 2.0)]
    predicted = [(0.0, 0.0), (1.0, 0.0), (1.9, 1.0), (2.8, 1.1), (3.7, 2.1)]
    drift_curve = [
        round(abs(px - tx) + abs(py - ty), 6)
        for (px, py), (tx, ty) in zip(predicted, truth)
    ]
    action_effect_target = (1.0, 0.0)
    action_effect_other = (0.0, 0.0)
    grounding = abs(action_effect_target[0]) / (
        abs(action_effect_target[0]) + abs(action_effect_other[0]) + 1e-12
    )
    hidden_state_before = {"object_x": 3, "object_y": 1}
    hidden_state_after = {"object_x": 3, "object_y": 1}
    memory = float(hidden_state_before == hidden_state_after)
    in_model_successes = [1, 1, 1, 1, 0]
    out_model_successes = [1, 1, 1, 0, 0]
    utility = statistics.fmean(out_model_successes) / statistics.fmean(in_model_successes)
    return {
        "fixture": "tiny-gridworld-v1",
        "scope": "contract test, not a public-checkpoint measurement",
        "wm/drift": {"curve": drift_curve, "horizons": list(range(len(truth)))},
        "wm/grounding": {"selectivity": round(grounding, 6)},
        "wm/memory": {"occlusion_consistency": memory},
        "wm/utility": {"policy_transfer_ratio": round(utility, 6)},
    }
