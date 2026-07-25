from __future__ import annotations

import hashlib
import json
import math
import sqlite3
import statistics
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .schemas.loopkit import Run, Sample, Verdict, validate_content_hash


def canonical_hash(value: Any) -> str:
    payload = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def dataset_records_for_run(run: Run) -> list[dict[str, Any]]:
    return [
        {
            "sample_id": sample.sample_id,
            "context": sample.context,
            "action": sample.action,
            "reference": sample.reference,
        }
        for sample in run.samples
    ]


def validate_run_dataset_hash(run: Run) -> None:
    actual = canonical_hash(dataset_records_for_run(run))
    if run.dataset_hash != actual:
        raise ValueError(
            f"run dataset hash mismatch: declared {run.dataset_hash}, actual {actual}"
        )


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

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "ScorerSpec":
        if not isinstance(payload, dict):
            raise ValueError("scorer must be an object")
        name = payload.get("name")
        version = payload.get("version")
        config = payload.get("config", {})
        if not isinstance(name, str) or not name.strip():
            raise ValueError("scorer name is required")
        if not isinstance(version, str) or not version.strip():
            raise ValueError("scorer version is required")
        if not isinstance(config, dict):
            raise ValueError("scorer config must be an object")
        scorer = cls.create(name, version, config)
        declared = validate_content_hash(payload.get("scorer_hash"), "scorer_hash")
        if scorer.content_hash != declared:
            raise ValueError(
                f"scorer hash mismatch: declared {declared}, actual {scorer.content_hash}"
            )
        return scorer

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "config": self.config,
            "scorer_hash": self.content_hash,
        }


class RunStore:
    """Thread-safe SQLite store for immutable contracts, runs, and evidence."""

    def __init__(self, path: str | Path = ":memory:") -> None:
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self.connection = sqlite3.connect(self.path, check_same_thread=False)
        self.connection.execute("PRAGMA busy_timeout = 5000")
        self.connection.execute("PRAGMA foreign_keys = ON")
        if self.path != ":memory:":
            self.connection.execute("PRAGMA journal_mode = WAL")
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
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS datasets (
                dataset_hash TEXT PRIMARY KEY,
                payload_json TEXT NOT NULL
            )
            """
        )
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS scorers (
                scorer_hash TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                version TEXT NOT NULL,
                payload_json TEXT NOT NULL
            )
            """
        )
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS comparisons (
                comparison_id TEXT PRIMARY KEY,
                baseline_run_id TEXT NOT NULL,
                candidate_run_id TEXT NOT NULL,
                verdict TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                FOREIGN KEY (baseline_run_id) REFERENCES runs(run_id),
                FOREIGN KEY (candidate_run_id) REFERENCES runs(run_id)
            )
            """
        )
        self.connection.execute("PRAGMA user_version = 1")
        self.connection.commit()

    @staticmethod
    def _stable_json(payload: Any) -> str:
        return json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)

    def is_ready(self) -> bool:
        try:
            with self._lock:
                row = self.connection.execute("SELECT 1").fetchone()
            return row == (1,)
        except sqlite3.Error:
            return False

    def _save_immutable(
        self,
        *,
        table: str,
        key_column: str,
        key: str,
        payload_json: str,
        insert_sql: str,
        values: tuple[Any, ...],
    ) -> bool:
        existing = self.connection.execute(
            f"SELECT payload_json FROM {table} WHERE {key_column} = ?", (key,)
        ).fetchone()
        if existing is not None:
            if existing[0] != payload_json:
                raise ValueError(f"{key_column} {key} already exists with different content")
            return False
        self.connection.execute(insert_sql, values)
        return True

    def save(self, run: Run, scorer: ScorerSpec | None = None) -> bool:
        validate_run_dataset_hash(run)
        if scorer is not None and scorer.content_hash != run.scorer_hash:
            raise ValueError(
                "run scorer hash does not match the supplied scorer contract"
            )
        dataset_payload = {
            "dataset_hash": run.dataset_hash,
            "samples": dataset_records_for_run(run),
        }
        run_json = self._stable_json(run.to_dict())
        with self._lock:
            try:
                self.connection.execute("BEGIN")
                self._save_immutable(
                    table="datasets",
                    key_column="dataset_hash",
                    key=run.dataset_hash,
                    payload_json=self._stable_json(dataset_payload),
                    insert_sql=(
                        "INSERT INTO datasets (dataset_hash, payload_json) VALUES (?, ?)"
                    ),
                    values=(run.dataset_hash, self._stable_json(dataset_payload)),
                )
                if scorer is not None:
                    scorer_json = self._stable_json(scorer.to_dict())
                    self._save_immutable(
                        table="scorers",
                        key_column="scorer_hash",
                        key=scorer.content_hash,
                        payload_json=scorer_json,
                        insert_sql=(
                            "INSERT INTO scorers "
                            "(scorer_hash, name, version, payload_json) VALUES (?, ?, ?, ?)"
                        ),
                        values=(
                            scorer.content_hash,
                            scorer.name,
                            scorer.version,
                            scorer_json,
                        ),
                    )
                elif self.connection.execute(
                    "SELECT 1 FROM scorers WHERE scorer_hash = ?", (run.scorer_hash,)
                ).fetchone() is None:
                    raise ValueError(
                        "scorer contract is not registered; supply the versioned scorer"
                    )
                created = self._save_immutable(
                    table="runs",
                    key_column="run_id",
                    key=run.run_id,
                    payload_json=run_json,
                    insert_sql=(
                        "INSERT INTO runs "
                        "(run_id, dataset_hash, scorer_hash, model_id, payload_json) "
                        "VALUES (?, ?, ?, ?, ?)"
                    ),
                    values=(
                        run.run_id,
                        run.dataset_hash,
                        run.scorer_hash,
                        run.model_id,
                        run_json,
                    ),
                )
                self.connection.commit()
                return created
            except Exception:
                self.connection.rollback()
                raise

    def get_payload(self, run_id: str) -> dict[str, Any]:
        with self._lock:
            row = self.connection.execute(
                "SELECT payload_json FROM runs WHERE run_id = ?", (run_id,)
            ).fetchone()
        if row is None:
            raise KeyError(run_id)
        return json.loads(row[0])

    def get(self, run_id: str) -> Run:
        return Run.from_dict(self.get_payload(run_id))

    def list_runs(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self.connection.execute(
                """
                SELECT run_id, dataset_hash, scorer_hash, model_id, payload_json
                FROM runs ORDER BY run_id
                """
            ).fetchall()
        result = []
        for run_id, dataset_hash, scorer_hash, model_id, payload_json in rows:
            payload = json.loads(payload_json)
            result.append(
                {
                    "run_id": run_id,
                    "dataset_hash": dataset_hash,
                    "scorer_hash": scorer_hash,
                    "model_id": model_id,
                    "sample_count": len(payload.get("samples", [])),
                    "metadata": payload.get("metadata", {}),
                }
            )
        return result

    def save_comparison(self, evidence: dict[str, Any]) -> bool:
        comparison_id = str(evidence["comparison_id"])
        payload_json = self._stable_json(evidence)
        with self._lock:
            try:
                self.connection.execute("BEGIN")
                created = self._save_immutable(
                    table="comparisons",
                    key_column="comparison_id",
                    key=comparison_id,
                    payload_json=payload_json,
                    insert_sql=(
                        "INSERT INTO comparisons "
                        "(comparison_id, baseline_run_id, candidate_run_id, verdict, payload_json) "
                        "VALUES (?, ?, ?, ?, ?)"
                    ),
                    values=(
                        comparison_id,
                        evidence["baseline_run_id"],
                        evidence["candidate_run_id"],
                        evidence["comparison"]["verdict"],
                        payload_json,
                    ),
                )
                self.connection.commit()
                return created
            except Exception:
                self.connection.rollback()
                raise

    def get_comparison(self, comparison_id: str) -> dict[str, Any]:
        with self._lock:
            row = self.connection.execute(
                "SELECT payload_json FROM comparisons WHERE comparison_id = ?",
                (comparison_id,),
            ).fetchone()
        if row is None:
            raise KeyError(comparison_id)
        return json.loads(row[0])

    def list_comparisons(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self.connection.execute(
                """
                SELECT comparison_id, baseline_run_id, candidate_run_id, verdict
                FROM comparisons ORDER BY comparison_id
                """
            ).fetchall()
        return [
            {
                "comparison_id": item[0],
                "baseline_run_id": item[1],
                "candidate_run_id": item[2],
                "verdict": item[3],
            }
            for item in rows
        ]

    def close(self) -> None:
        with self._lock:
            self.connection.close()

    def __enter__(self) -> "RunStore":
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()


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
        for key in ("baseline", "candidate", "delta", "ci_low", "ci_high"):
            value = result[key]
            if isinstance(value, float) and not math.isfinite(value):
                result[key] = None
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
    if not 0.0 < alpha < 1.0:
        raise ValueError("alpha must be between 0 and 1")
    if metric_count < 1:
        raise ValueError("metric_count must be positive")
    if tolerance < 0.0:
        raise ValueError("tolerance must be non-negative")

    base_by_id = {sample.sample_id: sample for sample in baseline.samples}
    cand_by_id = {sample.sample_id: sample for sample in candidate.samples}
    if len(base_by_id) != len(baseline.samples):
        raise ValueError("baseline run contains duplicate sample IDs")
    if len(cand_by_id) != len(candidate.samples):
        raise ValueError("candidate run contains duplicate sample IDs")
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
        base_sample = base_by_id[sample_id]
        cand_sample = cand_by_id[sample_id]
        if (
            base_sample.context != cand_sample.context
            or base_sample.action != cand_sample.action
            or base_sample.reference != cand_sample.reference
        ):
            raise ValueError(f"paired sample definition differs for {sample_id}")
        before = base_sample.scores[metric]
        after = cand_sample.scores[metric]
        if not math.isfinite(before) or not math.isfinite(after):
            raise ValueError(f"non-finite {metric} score for {sample_id}")
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
        reason = "upper confidence bound is at or above the allowed tolerance"

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
