"""Run the substrate (no-tools) sanity check for one (probe, dataset, model).

Substrate measures the model's solo pass rate per difficulty level — no
MCP tools, no verify, just answer-the-problem. Establishes the x-axis
for the verify-vs-passrate plot. One attempt per problem (no repeats).

Total problems run = 5 levels x n_per_level. With the default 7,
that's 35 problems.

Usage:
    python scripts/closure/run_substrate.py --model haiku-4.5 [--n-per-level 7] [--no-traces]
"""
from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from closure.data.omni_math import build_pool
from closure.probes.verify_probe import VerifyProbe
from closure.sweep import run_substrate


def parse_args():
    ap = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=__doc__,
    )
    ap.add_argument("--probe",       default="verify", choices=["verify"],
                    help="which probe's substrate options to use (default: verify). "
                         "Substrate prompts are probe-specific because they need to "
                         "match the conditions the same probe will use later.")
    ap.add_argument("--dataset",     default="omni-math", choices=["omni-math"],
                    help="which dataset to sample from (default: omni-math)")
    ap.add_argument("--model",       required=True,
                    help="short model label, e.g. 'haiku-4.5', 'opus-4.7'. "
                         "See closure.models.MODELS for the full list.")
    ap.add_argument("--n-per-level", type=int, default=7,
                    help="number of UNIQUE problems sampled from each "
                         "difficulty bucket. Substrate runs each problem "
                         "exactly once (no n-trials concept here). Default: 7.")
    ap.add_argument("--seed",        type=int, default=0,
                    help="random seed for problem sampling. Use the same "
                         "seed as the sweep so the substrate measurement "
                         "matches the same problem set. Default: 0.")
    ap.add_argument("--concurrency", type=int, default=32,
                    help="max in-flight problems. Drop if you see Bedrock "
                         "ThrottlingException. Default: 32.")
    ap.add_argument("--results-dir", default="results",
                    help="root directory for parquets and traces "
                         "(default: 'results')")
    ap.add_argument("--no-traces",   action="store_true",
                    help="skip per-problem markdown traces (faster, less disk)")
    return ap.parse_args()


_PROBES = {"verify": VerifyProbe}


async def main():
    args = parse_args()
    probe = _PROBES[args.probe]()
    pool, _ = build_pool(seed=args.seed, n_per_level=args.n_per_level)

    out_path = Path(args.results_dir) / "substrate" / f"{args.dataset}__{args.model}.parquet"
    if out_path.exists():
        print(f"skipping: {out_path} already exists "
              f"(delete to force re-run)")
        return

    await run_substrate(
        probe,
        model_label=args.model,
        pool=pool,
        n_per_level=args.n_per_level,
        seed=args.seed,
        concurrency=args.concurrency,
        results_dir=args.results_dir,
        save_traces=not args.no_traces,
        dataset=args.dataset,
    )


if __name__ == "__main__":
    asyncio.run(main())
