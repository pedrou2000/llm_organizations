"""Stage A: task-adaptive rubric synthesis.

`synthesize_rubric(task_spec)` -> a rubric (5 spine dims + up to 5 extras, each
with importance / target_level / 0-10 anchors). Pure helpers (validation,
weights, constants) live in `validate`.
"""
from .synth import DEFAULT_RUBRIC_MODEL_LABEL, synthesize_rubric
from .validate import (
    ANCHOR_LEVELS,
    MAX_EXTRA_DIMENSIONS,
    SPINE_IDS,
    extract_json,
    normalized_weights,
    validate_rubric,
)

__all__ = [
    "DEFAULT_RUBRIC_MODEL_LABEL",
    "synthesize_rubric",
    "ANCHOR_LEVELS",
    "MAX_EXTRA_DIMENSIONS",
    "SPINE_IDS",
    "extract_json",
    "normalized_weights",
    "validate_rubric",
]
