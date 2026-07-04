"""Pure aggregation + shared data types for the v2 meta-work judge.

No LLM / IO: turns a Rubric + per-dimension Verdicts into a MetaworkScore
(signed gaps, spine profile, task-specific rollup, scalars).
"""
from .compute import aggregate_scores
from .types import (
    Dimension,
    DimensionScore,
    MetaworkScore,
    Rubric,
    Verdict,
)

__all__ = [
    "aggregate_scores",
    "Dimension",
    "DimensionScore",
    "MetaworkScore",
    "Rubric",
    "Verdict",
]
