"""Harvest SWE-Marathon trajectories for meta-work analysis.

Downloads a stratified sample of agent trajectories from the public
SWE-Marathon site, flattens each to blind text, computes cheap structural
stats, and writes one parquet you can inspect BEFORE spending anything on
LLM judging.

Sizes (stratified across task x model):
    s  -> 20 trajectories   (smoke / cost check)
    m  -> 100 trajectories  (first real distribution)
    l  -> full corpus (~1300)

Output: results/metawork/harvest/harvest_<size>.parquet
  columns: id, task, model, reward, partial, correctness, ux, gates,
           tokens, cost, steps, n_rows, n_plan_tool, n_write, n_bash,
           n_submit, first_write_frac, kinds(json), flat_text, flat_chars

Usage:
    python scripts/metawork/published/harvest.py --size s
    python scripts/metawork/published/harvest.py --size m --tasks excel-clone slack-clone
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from metawork.published import SIZES, harvest


def parse_args():
    ap = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=__doc__,
    )
    ap.add_argument("--size", default="s", choices=list(SIZES.keys()),
                    help="s=20, m=100, l=full (~1300). Stratified across "
                         "task x model. Default: s.")
    ap.add_argument("--seed", type=int, default=0,
                    help="sampling seed (default: 0)")
    ap.add_argument("--tasks", nargs="*", default=None,
                    help="restrict to these task names (default: all 20)")
    ap.add_argument("--results-dir", default="results",
                    help="root dir for outputs (default: 'results')")
    ap.add_argument("--force", action="store_true",
                    help="re-harvest even if the output parquet exists")
    return ap.parse_args()


def main():
    args = parse_args()
    out_path = Path(args.results_dir) / "metawork" / "harvest" / f"harvest_{args.size}.parquet"
    if out_path.exists() and not args.force:
        print(f"skipping: {out_path} already exists (use --force to re-harvest)")
        return

    cache = Path(args.results_dir) / "metawork" / "trajectories"
    print(f"harvesting size={args.size} (seed={args.seed}) -> {out_path}")
    rows = harvest(size=args.size, seed=args.seed, cache=cache, tasks=args.tasks)

    df = pd.DataFrame(rows)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_path)

    err = df["error"].notna().sum() if "error" in df.columns else 0
    ok = df[df.get("flat_text").notna()] if "flat_text" in df.columns else df
    print(f"\nharvested {len(df)} trajectories  errors={err}")
    if len(ok):
        print(f"  tasks:  {ok['task'].nunique()}   models: {ok['model'].nunique()}")
        print(f"  rows/traj: min={ok['n_rows'].min()} "
              f"median={int(ok['n_rows'].median())} max={ok['n_rows'].max()}")
        print(f"  flat_chars: median={int(ok['flat_chars'].median())} "
              f"max={ok['flat_chars'].max()}")
        print(f"  partial present: {ok['partial'].notna().sum()}/{len(ok)}")


if __name__ == "__main__":
    main()
