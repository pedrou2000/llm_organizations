"""Task-adaptive meta-work judge (v2, M3.3).

Public contract — judge one trajectory, get a score:

    from metawork.judges.v2_adaptive import judge_metawork
    score = await judge_metawork(trajectory_path, task_spec)   # -> MetaworkScore

Internally: synthesize a task-specific rubric (Stage A) → score the trajectory
with one agentic judge per dimension (Stage B) → aggregate into signed gaps, a
spine profile, and a task-specific rollup. All internal; the caller only sees
`judge_metawork` and the `MetaworkScore` it returns.

`synthesize_rubric` is also exported for standalone rubric inspection (used by
scripts/metawork/judge/v2_adaptive/synth_rubric.py).
"""
from .aggregate import MetaworkScore
from .judge import judge_metawork
from .rubric import synthesize_rubric

__all__ = [
    "judge_metawork",
    "MetaworkScore",
    "synthesize_rubric",
]
