"""The v2 task-adaptive meta-work judge — public conductor.

`judge_metawork(trajectory_path, task_spec)` runs the whole instrument on ONE
trajectory and returns a MetaworkScore:

    task_spec ─► synthesize_rubric              (Stage A, internal)
    trajectory ─► stage_blind_trajectory        (isolate + scrub identity)
               ─► score_dimension × N in parallel (Stage B, one judge per dim)
               ─► aggregate_scores              (gaps / profile / rollup / scalars)

Rubric synthesis is fully internal (fresh per call). Never raises — stage/judge
failures surface as `errors` on the score.
"""
from __future__ import annotations

import json
from pathlib import Path

from common.concurrency import gather_with_progress

from .aggregate import MetaworkScore, Rubric, Verdict, aggregate_scores
from .rubric import DEFAULT_RUBRIC_MODEL_LABEL, synthesize_rubric
from .rubric.synth import RUBRIC_SYSTEM_PROMPT
from .score import (
    DEFAULT_SCORE_MODEL_LABEL,
    score_dimension,
    stage_blind_trajectory,
)


async def judge_metawork(
    trajectory_path: Path | str,
    task_spec: str,
    *,
    rubric: Rubric | dict | None = None,
    rubric_model: str = DEFAULT_RUBRIC_MODEL_LABEL,
    score_model: str = DEFAULT_SCORE_MODEL_LABEL,
    concurrency: int = 8,
    out_dir: Path | str | None = None,
) -> MetaworkScore:
    """Judge the meta-work quality of one agent trajectory.

    Args:
        trajectory_path: a trial dir (with agent/trajectory.json) or the file.
        task_spec: the task the agent was given (judge sees it; blind to
            outcome + identity).
        rubric: pin a pre-synthesized rubric (a Rubric or its dict form) and
            SKIP Stage A. Default None → synthesize fresh (the public contract).
            Pinning is for rubric caching and for variance experiments that need
            to hold the ruler fixed while re-running only Stage B.
        out_dir: if given, persist a stage-mirrored inspection tree under it:
            inputs/ (task_spec, blind trajectory), stage_a_rubric/ (synth prompt
            + rubric), stage_b_scoring/ (per-dimension prompts + verdicts), and
            score.json (the aggregate).

    Returns a MetaworkScore (never raises; failures recorded in `.errors`).
    """
    out_dir = Path(out_dir) if out_dir is not None else None
    synth_cost = 0.0
    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "inputs").mkdir(exist_ok=True)
        (out_dir / "stage_a_rubric").mkdir(exist_ok=True)
        (out_dir / "stage_b_scoring").mkdir(exist_ok=True)
        (out_dir / "inputs" / "task_spec.md").write_text(task_spec)
        # The meta-judge's (static) system prompt — its input alongside the task.
        (out_dir / "stage_a_rubric" / "prompt.md").write_text(RUBRIC_SYSTEM_PROMPT)

    # --- Stage A: rubric (skipped when a rubric is pinned) ---
    if rubric is not None:
        rubric = rubric if isinstance(rubric, Rubric) else Rubric.from_dict(rubric)
        rubric_dict = rubric.to_dict() if hasattr(rubric, "to_dict") else None
    else:
        synth = await synthesize_rubric(task_spec, model_label=rubric_model)
        synth_cost = synth.get("cost_usd", 0.0)
        if synth["rubric"] is None:
            rubric = Rubric(task_read="", dimensions=[])
            score = aggregate_scores(rubric, [])
            score.errors.append(f"rubric_synth_failed: {synth.get('error')}")
            score.cost_usd += synth_cost
            return score
        rubric = Rubric.from_dict(synth["rubric"])
        rubric_dict = synth["rubric"]
    if out_dir is not None and rubric_dict is not None:
        (out_dir / "stage_a_rubric" / "rubric.json").write_text(
            json.dumps(rubric_dict, indent=2))

    # --- stage the blind trajectory (isolated + identity-scrubbed) ---
    stage_dir = (out_dir / "inputs") if out_dir is not None else None
    blind_file = stage_blind_trajectory(trajectory_path, dest_dir=stage_dir)

    # --- Stage B: one agentic judge per dimension, in parallel ---
    want_prompts = out_dir is not None
    coros = [
        score_dimension(dim, rubric.dimensions, task_spec, str(blind_file),
                        model_label=score_model, return_prompt=want_prompts)
        for dim in rubric.dimensions
    ]
    results = await gather_with_progress(
        coros, limit=concurrency, label="score-dims",
        log_each=True, log_fields=("dimension_id", "observed_level"),
    )
    # score_dimension returns dicts (+ optional _prompt); split prompt off,
    # persist it, and wrap the rest in a Verdict.
    prompts: dict[str, str] = {}
    verdicts: list[Verdict] = []
    for r in results:
        if not isinstance(r, dict):
            continue
        prompt = r.pop("_prompt", None)
        v = Verdict.from_dict(r)
        v.cost_usd = float(r.get("cost_usd", 0.0))
        v.turns_used = r.get("turns_used")
        v.error = r.get("error")
        verdicts.append(v)
        if prompt:
            prompts[v.dimension_id] = prompt

    if out_dir is not None:
        _persist_verdicts(out_dir, verdicts, prompts)

    # --- aggregate ---
    score = aggregate_scores(rubric, verdicts)
    score.cost_usd += synth_cost
    if out_dir is not None:
        (out_dir / "score.json").write_text(json.dumps(score.to_dict(), indent=2))
    return score


def _persist_verdicts(out_dir: Path, verdicts: list[Verdict],
                      prompts: dict[str, str]) -> None:
    """Write each dimension's rendered prompt + verdict for inspection."""
    prompts_dir = out_dir / "stage_b_scoring" / "prompts"
    verdicts_dir = out_dir / "stage_b_scoring" / "verdicts"
    prompts_dir.mkdir(exist_ok=True)
    verdicts_dir.mkdir(exist_ok=True)
    for v in verdicts:
        if v.dimension_id in prompts:
            (prompts_dir / f"{v.dimension_id}.md").write_text(prompts[v.dimension_id])
        (verdicts_dir / f"{v.dimension_id}.json").write_text(
            json.dumps(vars(v), indent=2))
