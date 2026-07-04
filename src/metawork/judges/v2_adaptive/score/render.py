"""Render the per-dimension judge system prompt from the template.

Fills score/prompt.md's placeholders for one dimension. The dimension's
`target_level` is deliberately NOT exposed to the judge (it scores the observed
level blind to what was 'appropriate'; the gap is computed downstream).
"""
from __future__ import annotations

from pathlib import Path

from ..aggregate.types import Dimension
from ..rubric.validate import ANCHOR_LEVELS

_PROMPT_PATH = Path(__file__).with_name("prompt.md")
SCORE_PROMPT_TEMPLATE = _PROMPT_PATH.read_text()


def _anchors_block(dim: Dimension) -> str:
    return "\n".join(f"  [{lv:>2}] {dim.anchors.get(lv, '(no anchor)')}"
                     for lv in ANCHOR_LEVELS)


def _siblings_block(dim: Dimension, all_dims: list[Dimension]) -> str:
    others = [d for d in all_dims if d.id != dim.id]
    if not others:
        return "  (none)"
    return "\n".join(f"  - {d.name}: {d.description}" for d in others)


def render_prompt(dim: Dimension, all_dims: list[Dimension],
                  task_spec: str, trajectory_path: str) -> str:
    """Produce the fully-rendered system prompt for `dim`'s judge."""
    return (
        SCORE_PROMPT_TEMPLATE
        .replace("{{TASK_SPEC}}", task_spec)
        .replace("{{DIMENSION_ID}}", dim.id)
        .replace("{{DIMENSION_NAME}}", dim.name)
        .replace("{{DIMENSION_DESCRIPTION}}", dim.description)
        .replace("{{WHY_IT_MATTERS}}", dim.why_it_matters)
        .replace("{{ANCHORS_BLOCK}}", _anchors_block(dim))
        .replace("{{SIBLINGS_BLOCK}}", _siblings_block(dim, all_dims))
        .replace("{{TRAJECTORY_PATH}}", trajectory_path)
    )
