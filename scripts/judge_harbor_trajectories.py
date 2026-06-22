"""Run the meta-work judge over OUR Harbor trajectories (Source B).

Reads a Harbor job under results/harbor_jobs/<job>/, flattens each trial's
ATIF trajectory to blind text, judges it with the pinned judge model, and joins
the outcome metadata back for analysis. Independent of the published-corpus
harvest path (harvest.py / run.py).

Usage:
    python scripts/judge_harbor_trajectories.py --job m1_gpt55_final16 --judge-model opus-4.8
    python scripts/judge_harbor_trajectories.py --job m1_gpt55_final16 --task excel-clone --limit 2
"""
from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from metawork.judge import DEFAULT_JUDGE_MODEL_LABEL
from metawork.judge_harbor import judge_harbor_job


def parse_args():
    ap = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=__doc__,
    )
    ap.add_argument("--job", required=True,
                    help="Harbor job dir name under results/harbor_jobs/ "
                         "(e.g. m1_gpt55_final16)")
    ap.add_argument("--task", default=None,
                    help="optional task prefix filter (e.g. excel-clone)")
    ap.add_argument("--judge-model", default=DEFAULT_JUDGE_MODEL_LABEL,
                    help="short label of the judging model (see closure.models.MODELS). "
                         f"Default: {DEFAULT_JUDGE_MODEL_LABEL}.")
    ap.add_argument("--concurrency", type=int, default=8,
                    help="max in-flight judge calls (default: 8)")
    ap.add_argument("--parity", action="store_true",
                    help="published-parity flattening (action arc only, no agent "
                         "prose) for head-to-head comparison against published "
                         "numbers. Default is full-fidelity (prose kept).")
    ap.add_argument("--limit", type=int, default=None,
                    help="judge only the first N trajectories (cheap probe)")
    ap.add_argument("--results-dir", default="results")
    ap.add_argument("--jobs-dir", default="results/harbor_jobs")
    ap.add_argument("--force", action="store_true",
                    help="re-judge even if the output parquet exists")
    return ap.parse_args()


async def main():
    args = parse_args()
    suffix = "" if not args.parity else "_parity"
    out_path = (Path(args.results_dir) / "metawork"
                / f"judged_harbor_{args.job}__{args.judge_model}{suffix}.parquet")
    if out_path.exists() and not args.force and args.limit is None:
        print(f"skipping: {out_path} already exists (use --force to re-judge)")
        return
    await judge_harbor_job(
        args.job,
        judge_model_label=args.judge_model,
        task=args.task,
        concurrency=args.concurrency,
        results_dir=args.results_dir,
        jobs_dir=args.jobs_dir,
        limit=args.limit,
        keep_prose=not args.parity,
    )


if __name__ == "__main__":
    asyncio.run(main())
