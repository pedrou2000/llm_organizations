"""Batch v2 task-adaptive meta-work scoring over the PUBLISHED corpus.

The v2 counterpart of `judge_corpus` (which runs the frozen v1 checklist judge).
Where v1 passes `flat_text` to a single-call judge, v2 runs the full task-adaptive
instrument: a task-specific rubric (Stage A) + one agentic judge per dimension
(Stage B) exploring the trajectory.

Two deliberate choices for the published corpus:

  1. flat_text as input. The published harvest has no raw trajectory.json — only
     the flattened `flat_text` (with `[step N]` markers). We write it to a file
     and point the judge at it. NOTE: this text is far more lossy for some models
     than others (the harvest kept ~8x more prose for DeepSeek than GPT-5.5), so
     CROSS-MODEL comparisons partly reflect harvest fidelity, not just meta-work.
     Within-model / within-task comparisons are unaffected.

  2. One rubric per TASK, reused across all models. Rubric synthesis is the
     dominant variance source (sigma_rubric ~ 3x sigma_scoring), so pinning a
     single rubric per task means every model on that task is judged against the
     IDENTICAL ruler — removing rubric noise from cross-model comparisons. The
     rubric is synthesized once from the task spec (blind to any trajectory).

Output:
  results/metawork/judged/v2_adaptive/experiments/published_<tag>/scored_published_<tag>__<score_model>.parquet
  + per-trajectory inspection trees under experiments/published_<tag>/scores/<id>/
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import pandas as pd

from common.concurrency import gather_with_progress

from ..judges.v2_adaptive import judge_metawork, synthesize_rubric
from ..judges.v2_adaptive.aggregate.types import Rubric
from ..judges.v2_adaptive.rubric import DEFAULT_RUBRIC_MODEL_LABEL
from ..judges.v2_adaptive.score import DEFAULT_SCORE_MODEL_LABEL

_TASKS_DIR = Path("vendor/swe-marathon/tasks")
_META_KEYS = ("model", "reward", "partial", "correctness", "ux", "gates", "steps")


def _one_per_cell(harvest: pd.DataFrame) -> pd.DataFrame:
    """Pick one trajectory per (model, task) cell — the balanced full grid.

    Deterministic: the first row per cell after a stable sort by id, so re-runs
    select the same trajectories.
    """
    h = harvest.sort_values("id")
    return h.groupby(["model", "task"], as_index=False, sort=True).first()


def _task_spec(task: str) -> str:
    p = _TASKS_DIR / task / "instruction.md"
    return p.read_text() if p.exists() else ""


async def _rubric_for_task(task: str, model_label: str,
                           cache: dict[str, Rubric]) -> Rubric | None:
    """Synthesize (once) and cache the rubric for a task. None on failure."""
    if task in cache:
        return cache[task]
    spec = _task_spec(task)
    if not spec:
        cache[task] = None
        return None
    synth = await synthesize_rubric(spec, model_label=model_label)
    rubric = Rubric.from_dict(synth["rubric"]) if synth.get("rubric") else None
    cache[task] = rubric
    return rubric


async def score_published_corpus(
    *,
    size: str = "l",
    tag: str = "grid",
    rubric_model: str = DEFAULT_RUBRIC_MODEL_LABEL,
    score_model: str = DEFAULT_SCORE_MODEL_LABEL,
    concurrency: int = 4,
    dim_concurrency: int = 8,
    results_dir: Path | str = "results",
    one_per_cell: bool = True,
    limit: int | None = None,
) -> pd.DataFrame:
    """Score the published corpus with the v2 adaptive judge.

    `one_per_cell` selects the balanced 1-per-(model,task) grid (default).
    `concurrency` bounds how many trajectories score at once; each fans out
    `dim_concurrency` dimension judges internally. Task specs must exist under
    vendor/swe-marathon/tasks/<task>/instruction.md.
    """
    results_dir = Path(results_dir)
    harvest = pd.read_parquet(
        results_dir / "metawork" / "trajectories" / "published" / f"harvest_{size}.parquet")
    grid = _one_per_cell(harvest) if one_per_cell else harvest.copy()
    if limit is not None:
        grid = grid.head(limit).copy()

    tasks = sorted(grid["task"].unique())
    print(f"scoring {len(grid)} published trajectories with v2 judge "
          f"(tag={tag}, {grid['model'].nunique()} models x {len(tasks)} tasks, "
          f"rubric={rubric_model}, score={score_model}, conc={concurrency})")

    # --- Stage A: one rubric per task, synthesized once (blind to trajectories) ---
    print(f"[A] synthesizing {len(tasks)} task rubrics (cached, reused across models) ...")
    rubric_cache: dict[str, Rubric] = {}
    for t in tasks:
        await _rubric_for_task(t, rubric_model, rubric_cache)
    ok = sum(1 for r in rubric_cache.values() if r is not None)
    print(f"    {ok}/{len(tasks)} rubrics synthesized")

    # Everything for this experiment lives under experiments/published_<tag>/:
    # the summary parquet + per-trajectory score trees under scores/.
    exp_dir = (results_dir / "metawork" / "judged" / "v2_adaptive"
               / "experiments" / f"published_{tag}")
    scores_root = exp_dir / "scores"

    async def score_one(row: pd.Series) -> dict:
        rubric = rubric_cache.get(row["task"])
        if rubric is None:
            return {"id": row["id"], "task": row["task"],
                    **{k: row.get(k) for k in _META_KEYS},
                    "cost_usd": 0.0, "n_errors": 1,
                    "overall_gap": None, "overall_observed": None,
                    "error": "no_rubric"}
        # write flat_text to an isolated file; judge_metawork stages + scrubs it
        with tempfile.TemporaryDirectory(prefix="mw_pub_") as td:
            fpath = Path(td) / "trajectory.txt"
            fpath.write_text(row["flat_text"])
            score = await judge_metawork(
                fpath, _task_spec(row["task"]),
                rubric=rubric,   # pinned per-task ruler (identical across models)
                score_model=score_model,
                concurrency=dim_concurrency,
                out_dir=scores_root / str(row["id"]),
            )
        return {"id": row["id"], "task": row["task"],
                **{k: row.get(k) for k in _META_KEYS},
                **score.summary_row()}

    # --- Stage B: score every cell, bounded outer concurrency ---
    rows = await gather_with_progress(
        [score_one(r) for _, r in grid.iterrows()],
        limit=concurrency,
        label=f"v2-published-{tag}",
        log_each=True,
        log_fields=("task", "overall_gap"),
    )

    out = pd.DataFrame(rows)
    out["rubric_model"] = rubric_model
    out["score_model"] = score_model
    out["corpus"] = f"published_{tag}"

    suffix = f"_limit{limit}" if limit is not None else ""
    out_path = exp_dir / f"scored_published_{tag}__{score_model}{suffix}.parquet"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(out_path)

    tot_err = int(out["n_errors"].sum()) if "n_errors" in out.columns else 0
    scored = out["overall_gap"].notna().sum()
    print(f"\nscored {len(out)} trajectories  ok={scored}  dimension_errors={tot_err}")
    if scored:
        print(f"  mean overall_gap = {out['overall_gap'].mean():+.2f}  "
              f"mean observed = {out['overall_observed'].mean():.2f}")
    print(f"  cost=${out['cost_usd'].sum():.2f}  -> {out_path}")
    return out
