"""Batch v2 task-adaptive meta-work scoring over OUR Harbor trajectories.

The v2 counterpart of `judge_job.judge_harbor_job` (which runs the frozen v1
checklist judge). Where v1 flattens each trajectory to blind text and scores it
against a fixed rubric, v2 hands the judge the RAW trial dir and runs the full
task-adaptive instrument (`metawork.judges.v2_adaptive.judge_metawork`): a
task-specific rubric is synthesized per task, then one agentic judge per
dimension explores the trajectory and scores a signed gap.

For each trial we:
  - resolve the task spec once from vendor/swe-marathon/tasks/<task>/instruction.md
    (all trials of a task share the same spec — the judge sees it, blind to
    outcome + identity);
  - run judge_metawork on the raw trial dir, persisting a stage-mirrored
    inspection tree under scores/<job>/<trial_id>/;
  - join the trial's outcome metadata back AFTER scoring (reusing source's
    _trial_metadata), so the meta-work gap can't be contaminated by the result.

Outputs:
  - per-trajectory inspection trees:
      results/metawork/judged/v2_adaptive/scores/<job>/<trial_id>/
  - job summary parquet (small, tracked, sits BESIDE scores/ so it isn't ignored):
      results/metawork/judged/v2_adaptive/scored_<job>__<score_model>.parquet
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from ..judges.v2_adaptive import judge_metawork
from ..judges.v2_adaptive.rubric import DEFAULT_RUBRIC_MODEL_LABEL
from ..judges.v2_adaptive.score import DEFAULT_SCORE_MODEL_LABEL
from .source import _trial_metadata

_TASKS_DIR = Path("vendor/swe-marathon/tasks")

# Outcome/identity metadata carried alongside the judge's gap scores. Joined
# back AFTER scoring — never seen by the (blind) judge.
_META_KEYS = ("reward", "partial", "correctness", "ux", "gates")


def _load_task_spec(task: str) -> str:
    """The instruction.md the agent saw at t=0 (blind to solution/tests)."""
    p = _TASKS_DIR / task / "instruction.md"
    if not p.exists():
        raise FileNotFoundError(f"no instruction.md for task {task!r} at {p}")
    return p.read_text()


def _iter_trial_dirs(job_dir: Path, task: str | None):
    """Yield the trial dirs under a Harbor job (same filter as source.load_job)."""
    for trial_dir in sorted(job_dir.iterdir()):
        if not trial_dir.is_dir() or "__" not in trial_dir.name:
            continue  # skip config/logs and other non-trial dirs
        if task and not trial_dir.name.startswith(f"{task}__"):
            continue
        if not (trial_dir / "agent" / "trajectory.json").exists():
            continue  # errored trial with no trajectory
        yield trial_dir


async def score_harbor_job(
    job: str,
    *,
    rubric_model: str = DEFAULT_RUBRIC_MODEL_LABEL,
    score_model: str = DEFAULT_SCORE_MODEL_LABEL,
    task: str | None = None,
    dim_concurrency: int = 8,
    results_dir: Path | str = "results",
    jobs_dir: Path | str = "results/metawork/trajectories/harbor",
    limit: int | None = None,
) -> pd.DataFrame:
    """Score every trajectory in one Harbor job with the v2 adaptive judge.

    Trajectories are scored SEQUENTIALLY at the outer (trial) level; each
    judge_metawork call fans out `dim_concurrency` agentic dimension-judges
    internally. This keeps in-flight agent count and cost/log volume
    predictable (the alternative — trials × dimensions all at once — is
    API-heavy and noisy). `limit` caps the number of trials (cheap probe).

    Returns a summary DataFrame (one row per trajectory) and persists it to
    scored_<job>__<score_model>.parquet, plus a per-trial inspection tree.
    """
    results_dir = Path(results_dir)
    job_dir = Path(jobs_dir) / job
    if not job_dir.is_dir():
        raise FileNotFoundError(f"no such Harbor job dir: {job_dir}")

    trial_dirs = list(_iter_trial_dirs(job_dir, task))
    if limit is not None:
        trial_dirs = trial_dirs[:limit]
    if not trial_dirs:
        raise ValueError(f"no trajectories found for job={job!r} task={task!r}")

    scores_root = (results_dir / "metawork" / "judged" / "v2_adaptive"
                   / "scores" / job)
    print(f"scoring {len(trial_dirs)} Harbor trajectories with v2 judge "
          f"(job={job}, task={task or 'all'}, rubric={rubric_model}, "
          f"score={score_model}, dim_conc={dim_concurrency})")

    # Task spec is shared across a task's trials — cache to avoid re-reads.
    spec_cache: dict[str, str] = {}
    rows: list[dict] = []
    for i, trial_dir in enumerate(trial_dirs, 1):
        trial_id = trial_dir.name
        trial_task = task or trial_id.split("__", 1)[0]
        if trial_task not in spec_cache:
            spec_cache[trial_task] = _load_task_spec(trial_task)
        spec = spec_cache[trial_task]

        print(f"  [{i}/{len(trial_dirs)}] {trial_id} (task={trial_task}) ...")
        score = await judge_metawork(
            trial_dir, spec,
            rubric_model=rubric_model,
            score_model=score_model,
            concurrency=dim_concurrency,
            out_dir=scores_root / trial_id,
        )

        # Blind-then-join: outcome metadata attached only after scoring.
        meta = _trial_metadata(trial_dir)
        row = {"id": trial_id, "task": trial_task,
               **{k: meta.get(k) for k in _META_KEYS},
               **score.summary_row()}
        rows.append(row)
        print(f"      overall_gap={score.overall_gap:+.2f} "
              f"observed={score.overall_observed:.2f} "
              f"cost=${score.cost_usd:.2f} errors={len(score.errors)}")

    out = pd.DataFrame(rows)
    out["job"] = job
    out["rubric_model"] = rubric_model
    out["score_model"] = score_model

    suffix = f"_limit{limit}" if limit is not None else ""
    out_path = (results_dir / "metawork" / "judged" / "v2_adaptive"
                / f"scored_{job}__{score_model}{suffix}.parquet")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(out_path)

    tot_err = int(out["n_errors"].sum()) if "n_errors" in out.columns else 0
    print(f"\nscored {len(out)} trajectories  dimension_errors={tot_err}")
    if len(out):
        print(f"  mean overall_gap = {out['overall_gap'].mean():+.2f}  "
              f"mean observed = {out['overall_observed'].mean():.2f}")
    print(f"  cost=${out['cost_usd'].sum():.2f}  -> {out_path}")
    print(f"  inspection trees -> {scores_root}/")
    return out
