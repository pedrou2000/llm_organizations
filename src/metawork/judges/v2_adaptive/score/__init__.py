"""Stage B: agentic per-dimension trajectory scoring.

`score_dimension(dim, all_dims, task_spec, trajectory_file)` runs one agentic
judge over a blind trajectory and returns a Verdict. `stage_blind_trajectory`
prepares the isolated, identity-scrubbed file; `render_prompt` builds a judge's
system prompt (exposed for inspection).
"""
from .judge import DEFAULT_SCORE_MODEL_LABEL, MAX_JUDGE_TURNS, score_dimension
from .render import render_prompt
from .staging import stage_blind_trajectory

__all__ = [
    "DEFAULT_SCORE_MODEL_LABEL",
    "MAX_JUDGE_TURNS",
    "score_dimension",
    "render_prompt",
    "stage_blind_trajectory",
]
