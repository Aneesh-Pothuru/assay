"""ASSAY: deterministic, versioned evaluation gates."""

from .core import (
    Comparison,
    Dataset,
    RunStore,
    ScorerSpec,
    compare_runs,
    demo_runs,
)

__all__ = [
    "Comparison",
    "Dataset",
    "RunStore",
    "ScorerSpec",
    "compare_runs",
    "demo_runs",
]
__version__ = "0.1.0"
