"""ASSAY: deterministic, versioned evaluation gates."""

from .core import (
    Comparison,
    Dataset,
    RunStore,
    ScorerSpec,
    compare_runs,
    demo_runs,
)
from .service import EvaluationService

__all__ = [
    "Comparison",
    "Dataset",
    "RunStore",
    "ScorerSpec",
    "compare_runs",
    "demo_runs",
    "EvaluationService",
]
__version__ = "0.2.0"
