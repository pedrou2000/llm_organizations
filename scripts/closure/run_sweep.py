"""Run a probe sweep for one (probe, dataset, model).

A "trial" is one (problem, condition, attempt) instance. The total
trial count is:

    levels_active * n_per_level * len(CONDITIONS=3) * n_trials

Per-cell N (the statistic you care about for one
(model, condition, level) point in the plots) is:

    cell_N = n_per_level * n_trials

So with the defaults: 7 problems/level x 3 trials/problem = N=21 per cell.

Example sizings (defaults skip Levels 1-2 for opus tier):
    --n-per-level  7  --n-trials  3   ->  N=21,  189 trials/sweep
    --n-per-level 10  --n-trials  5   ->  N=50,  450 trials/sweep
    --n-per-level 14  --n-trials 10   ->  N=140, 1260 trials/sweep

Usage:
    python scripts/closure/run_sweep.py --model opus-4.7 [--n-trials 3] [--n-per-level 7]
"""
from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from closure.data.omni_math import build_pool
from closure.probes.verify_probe import VerifyProbe
from closure.sweep import run_sweep


def parse_args():
    ap = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=__doc__,
    )
    ap.add_argument("--probe",       default="verify", choices=["verify"],
                    help="which probe to run (default: verify)")
    ap.add_argument("--dataset",     default="omni-math", choices=["omni-math"],
                    help="which dataset to sample from (default: omni-math)")
    ap.add_argument("--model",       required=True,
                    help="short model label, e.g. 'haiku-4.5', 'opus-4.7'. "
                         "See closure.models.MODELS for the full list.")
    ap.add_argument("--n-per-level", type=int, default=10,
                    help="number of UNIQUE problems sampled from each "
                         "difficulty bucket (Levels 1-5). Higher = broader "
                         "coverage of distinct problems. Default: 10.")
    ap.add_argument("--n-trials",    type=int, default=1,
                    help="number of REPEATED runs per (problem, condition). "
                         "Higher = lower variance for fixed problem coverage. "
                         "Default: 1.")
    ap.add_argument("--seed",        type=int, default=0,
                    help="random seed for problem sampling (default: 0)")
    ap.add_argument("--concurrency", type=int, default=32,
                    help="max in-flight trials. Drop if you see Bedrock "
                         "ThrottlingException. Default: 32.")
    ap.add_argument("--results-dir", default="results",
                    help="root directory for parquets and traces "
                         "(default: 'results')")
    ap.add_argument("--no-traces",   action="store_true",
                    help="skip per-trial markdown traces (faster, less disk)")
    ap.add_argument("--force",       action="store_true",
                    help="re-run even if the output parquet already exists")
    return ap.parse_args()


_PROBES = {"verify": VerifyProbe}


async def main():
    args = parse_args()
    probe = _PROBES[args.probe]()
    pool, _ = build_pool(seed=args.seed, n_per_level=args.n_per_level)

    out_path = (
        Path(args.results_dir) / "closure" / "sweep"
        / f"{args.probe}__{args.dataset}__{args.model}.parquet"
    )
    if out_path.exists() and not args.force:
        print(f"skipping: {out_path} already exists (use --force to re-run)")
        return

    await run_sweep(
        probe,
        model_label=args.model,
        pool=pool,
        n_per_level=args.n_per_level,
        n_trials=args.n_trials,
        seed=args.seed,
        concurrency=args.concurrency,
        results_dir=args.results_dir,
        save_traces=not args.no_traces,
        dataset=args.dataset,
    )


if __name__ == "__main__":
    asyncio.run(main())
