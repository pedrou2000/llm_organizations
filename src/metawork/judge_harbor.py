"""Batch meta-work judging over OUR Harbor trajectories (Source B).

The job-keyed counterpart of `run.py` (which judges the published Source-A
corpus by "size"). Loads a Harbor job via `harbor_source.load_job`, judges each
trajectory BLIND with the same durable judge (`judge.py`), then joins the
outcome metadata back for analysis.

Output: results/metawork/judged/judged_harbor_<job>__<judge_model>.parquet
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from common.concurrency import gather_with_progress

from .harbor_source import load_job
from .judge import DEFAULT_JUDGE_MODEL_LABEL, judge_trajectory

# Metadata columns carried alongside the judge's rubric scores.
_META_COLS = [
    "id", "task", "model", "reward", "partial", "correctness", "ux",
    "gates", "steps", "n_rows", "n_plan_tool", "n_write", "n_bash",
    "n_submit", "first_write_frac", "flat_chars",
]


async def judge_harbor_job(
    job: str,
    *,
    judge_model_label: str = DEFAULT_JUDGE_MODEL_LABEL,
    task: str | None = None,
    concurrency: int = 8,
    results_dir: Path | str = "results",
    jobs_dir: Path | str = "results/metawork/harbor_jobs",
    limit: int | None = None,
    keep_prose: bool = True,
) -> pd.DataFrame:
    """Judge every trajectory in one Harbor job.

    Judges blind (passes ONLY flat_text); metadata is joined back afterward so
    the meta-work score can't be contaminated by the outcome. Persists to
    judged_harbor_<job>__<judge_model>.parquet. `keep_prose=False` switches to
    published-parity flattening (action arc only) for head-to-head comparison
    against the published numbers; the parquet name gets a `_parity` suffix.
    """
    results_dir = Path(results_dir)
    rows = load_job(job, jobs_dir=jobs_dir, task=task, keep_prose=keep_prose)
    if limit is not None:
        rows = rows[:limit]
    if not rows:
        raise ValueError(f"no trajectories loaded for job={job!r} task={task!r}")

    harvest = pd.DataFrame(rows)
    flats = harvest["flat_text"].tolist()
    print(f"judging {len(flats)} Harbor trajectories "
          f"(job={job}, task={task or 'all'}, judge={judge_model_label}, "
          f"conc={concurrency})")

    verdicts = await gather_with_progress(
        [judge_trajectory(ft, judge_model_label) for ft in flats],
        limit=concurrency,
        label=f"metawork-harbor-{job}",
        log_each=False,
        log_fields=("overall_meta_work", "pattern"),
    )

    vdf = pd.DataFrame(verdicts).reset_index(drop=True)
    meta = harvest[[c for c in _META_COLS if c in harvest.columns]].reset_index(drop=True)
    out = pd.concat([meta, vdf], axis=1)
    out["judge_model"] = judge_model_label
    out["job"] = job
    out["flatten_mode"] = "full" if keep_prose else "parity"

    suffix = "" if keep_prose else "_parity"
    out_path = (results_dir / "metawork" / "judged"
                / f"judged_harbor_{job}__{judge_model_label}{suffix}.parquet")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(out_path)

    err = out["error"].notna().sum() if "error" in out.columns else 0
    parsed = out["overall_meta_work"].notna().sum()
    print(f"\njudged {len(out)} trajectories  parsed_ok={parsed}  errors/parse_fail={err}")
    if parsed:
        print(f"  mean overall_meta_work = {out['overall_meta_work'].mean():.2f}  "
              f"median = {out['overall_meta_work'].median():.1f}")
    print(f"  cost=${out['cost_usd'].sum():.2f}  -> {out_path}")
    return out
