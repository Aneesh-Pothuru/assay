"""Vendored loopkit-compatible records.

This intentionally lives in-repository: standalone projects exchange these
records as files and never depend on a live loopkit service.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


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

