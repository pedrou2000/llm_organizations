"""Task-adaptive meta-work judge (M3.3).

Stage A (rubric.py): task spec -> task-specific rubric (fixed schema, fixed
non-saturable 0-10 scale, free dimensions).
Stage B (score.py): (rubric, blind trajectory) -> per-dimension observed levels.
"""
from .rubric import (
    ANCHOR_LEVELS,
    DEFAULT_RUBRIC_MODEL_LABEL,
    SPINE_IDS,
    normalized_weights,
    synthesize_rubric,
    validate_rubric,
)

__all__ = [
    "ANCHOR_LEVELS",
    "DEFAULT_RUBRIC_MODEL_LABEL",
    "SPINE_IDS",
    "normalized_weights",
    "synthesize_rubric",
    "validate_rubric",
]
