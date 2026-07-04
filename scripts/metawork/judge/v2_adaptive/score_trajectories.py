"""Score OUR Harbor trajectories with the v2 task-adaptive meta-work judge.

The v2 counterpart of judge/v1_fixed/judge_harbor.py. Reads a Harbor job under
results/metawork/trajectories/harbor/<job>/, and for each trial runs the full
task-adaptive instrument: synthesize a task-specific rubric (Stage A), then one
agentic judge per dimension scores a signed gap over the RAW trajectory
(Stage B). Outcome metadata is joined back after scoring so the meta-work gap
can't be contaminated by the result.

Outputs a job summary parquet plus a per-trajectory inspection tree under
results/metawork/judged/v2_adaptive/scores/<job>/<trial_id>/.

Usage:
    python scripts/metawork/judge/v2_adaptive/score_trajectories.py --job m1_gpt55_final16
    python scripts/metawork/judge/v2_adaptive/score_trajectories.py --job my_job --task excel-clone --limit 2
    python scripts/metawork/judge/v2_adaptive/score_trajectories.py --job my_job --rubric-model opus-4.8 --score-model opus-4.8
"""
from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from metawork.harbor import score_harbor_job
from metawork.judges.v2_adaptive.rubric import DEFAULT_RUBRIC_MODEL_LABEL
from metawork.judges.v2_adaptive.score import DEFAULT_SCORE_MODEL_LABEL


def parse_args():
    ap = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=__doc__,
    )
    ap.add_argument("--job", required=True,
                    help="Harbor job dir name under results/metawork/trajectories/harbor/")
    ap.add_argument("--task", default=None,
                    help="optional task prefix filter (e.g. excel-clone)")
    ap.add_argument("--model", default=None,
                    help="convenience: set BOTH rubric + score model at once. "
                         "Overridden by --rubric-model / --score-model.")
    ap.add_argument("--rubric-model", default=None,
                    help=f"Stage-A rubric synthesizer (default: {DEFAULT_RUBRIC_MODEL_LABEL})")
    ap.add_argument("--score-model", default=None,
                    help=f"Stage-B dimension judge (default: {DEFAULT_SCORE_MODEL_LABEL})")
    ap.add_argument("--dim-concurrency", type=int, default=8,
                    help="max in-flight dimension judges per trajectory (default: 8)")
    ap.add_argument("--limit", type=int, default=None,
                    help="score only the first N trajectories (cheap probe)")
    ap.add_argument("--results-dir", default="results")
    ap.add_argument("--jobs-dir", default="results/metawork/trajectories/harbor")
    ap.add_argument("--force", action="store_true",
                    help="re-score even if the summary parquet exists")
    return ap.parse_args()


async def main():
    args = parse_args()
    rubric_model = args.rubric_model or args.model or DEFAULT_RUBRIC_MODEL_LABEL
    score_model = args.score_model or args.model or DEFAULT_SCORE_MODEL_LABEL

    suffix = f"_limit{args.limit}" if args.limit is not None else ""
    out_path = (Path(args.results_dir) / "metawork" / "judged" / "v2_adaptive"
                / f"scored_{args.job}__{score_model}{suffix}.parquet")
    if out_path.exists() and not args.force:
        print(f"skipping: {out_path} already exists (use --force to re-score)")
        return

    await score_harbor_job(
        args.job,
        rubric_model=rubric_model,
        score_model=score_model,
        task=args.task,
        dim_concurrency=args.dim_concurrency,
        results_dir=args.results_dir,
        jobs_dir=args.jobs_dir,
        limit=args.limit,
    )


if __name__ == "__main__":
    asyncio.run(main())
