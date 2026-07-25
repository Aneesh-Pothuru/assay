"""Vendored loopkit-compatible records.

This intentionally lives in-repository: standalone projects exchange these
records as files and never depend on a live loopkit service.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
import math
import re
from typing import Any


HASH_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")


def _required_text(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a non-empty string")
    return value


def validate_content_hash(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not HASH_PATTERN.fullmatch(value):
        raise ValueError(f"{field_name} must be sha256 followed by 64 lowercase hex characters")
    return value


class Verdict(str, Enum):
    PASSED = "PASSED"
    BLOCKED = "BLOCKED"
    UNDETERMINED = "UNDETERMINED"
    UNATTRIBUTED = "UNATTRIBUTED"


@dataclass(frozen=True)
class Sample:
    sample_id: str
    context: dict[str, Any]
    action: Any
    reference: Any
    prediction: Any
    scores: dict[str, float]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "Sample":
        if not isinstance(payload, dict):
            raise ValueError("sample must be an object")
        context = payload.get("context")
        if not isinstance(context, dict):
            raise ValueError("sample context must be an object")
        raw_scores = payload.get("scores")
        if not isinstance(raw_scores, dict) or not raw_scores:
            raise ValueError("sample scores must be a non-empty object")
        scores: dict[str, float] = {}
        for name, raw_value in raw_scores.items():
            if not isinstance(name, str) or not name:
                raise ValueError("score names must be non-empty strings")
            if isinstance(raw_value, bool) or not isinstance(raw_value, (int, float)):
                raise ValueError(f"score {name} must be numeric")
            value = float(raw_value)
            if not math.isfinite(value):
                raise ValueError(f"score {name} must be finite")
            scores[name] = value
        return cls(
            sample_id=_required_text(payload, "sample_id"),
            context=dict(context),
            action=payload.get("action"),
            reference=payload.get("reference"),
            prediction=payload.get("prediction"),
            scores=scores,
        )


@dataclass(frozen=True)
class Run:
    run_id: str
    dataset_hash: str
    scorer_hash: str
    model_id: str
    samples: tuple[Sample, ...]
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["samples"] = [sample.to_dict() for sample in self.samples]
        return result

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "Run":
        if not isinstance(payload, dict):
            raise ValueError("run must be an object")
        raw_samples = payload.get("samples")
        if not isinstance(raw_samples, list):
            raise ValueError("run samples must be an array")
        metadata = payload.get("metadata", {})
        if not isinstance(metadata, dict):
            raise ValueError("run metadata must be an object")
        return cls(
            run_id=_required_text(payload, "run_id"),
            dataset_hash=validate_content_hash(payload.get("dataset_hash"), "dataset_hash"),
            scorer_hash=validate_content_hash(payload.get("scorer_hash"), "scorer_hash"),
            model_id=_required_text(payload, "model_id"),
            samples=tuple(Sample.from_dict(sample) for sample in raw_samples),
            metadata=dict(metadata),
        )
