"""Run the substrate (no-tools) sanity check for one (probe, dataset, model).

Usage:
    python -m scripts.run_substrate --model haiku-4.5 [--n-per-level 7] [--no-traces]
"""
from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from closure.data.omni_math import build_pool
from closure.probes.verify_probe import VerifyProbe
from closure.sweep import run_substrate


def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--probe",       default="verify",
                    choices=["verify"],
                    help="probe whose substrate options to use (default: verify)")
    ap.add_argument("--dataset",     default="omni-math", choices=["omni-math"])
    ap.add_argument("--model",       required=True,
                    help="short label, e.g. 'haiku-4.5', 'opus-4.7'")
    ap.add_argument("--n-per-level", type=int, default=7)
    ap.add_argument("--seed",        type=int, default=0)
    ap.add_argument("--concurrency", type=int, default=32)
    ap.add_argument("--results-dir", default="results")
    ap.add_argument("--no-traces",   action="store_true",
                    help="skip per-trial markdown traces")
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
