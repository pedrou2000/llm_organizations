"""Explore the harvested SWE-Marathon corpus (pre-judging).

Structural / metadata exploration only — no LLM judging yet. Answers:
  - Is effort (rows/tokens/bash) decoupled from outcome (partial)?
  - How do models rank on outcome vs effort?
  - Does the 'thrash' signature (high effort, zero score) show up, in whom?

Usage:
    python scripts/metawork/published/explore.py [--size l]
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd


def to_num(s, scale: float = 1.0):
    """Parse '14.7M' / '894K' / '$12.56' style strings to float."""
    if not isinstance(s, str):
        return np.nan
    s = s.replace("$", "").replace(",", "").strip()
    mult = 1.0
    if s.endswith("K"):
        mult, s = 1e3, s[:-1]
    elif s.endswith("M"):
        mult, s = 1e6, s[:-1]
    elif s.endswith("B"):
        mult, s = 1e9, s[:-1]
    try:
        return float(s) * mult / scale
    except ValueError:
        return np.nan


def load(path: Path) -> pd.DataFrame:
    df = pd.read_parquet(path)
    for c in ("partial", "correctness", "ux"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["tokens_M"] = df["tokens"].apply(lambda s: to_num(s, 1e6))
    df["cost_usd"] = df["cost"].apply(to_num)
    df["wr_ratio"] = df["n_write"] / (df["n_bash"] + df["n_write"] + 1)
    return df


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--size", default="l")
    ap.add_argument("--results-dir", default="results")
    args = ap.parse_args()

    path = Path(args.results_dir) / "metawork" / f"harvest_{args.size}.parquet"
    df = load(path)

    print(f"=== {len(df)} trajectories | {df['task'].nunique()} tasks | "
          f"{df['model'].nunique()} models ===\n")

    print("reward (binary):", df["reward"].value_counts().to_dict())
    print(f"partial: mean={df['partial'].mean():.3f} median={df['partial'].median():.3f} "
          f"| ==0: {(df['partial']==0).mean():.1%} | >0.9: {(df['partial']>0.9).mean():.1%}\n")

    print("--- per-model (sorted by median partial) ---")
    g = (df.groupby("model")
           .agg(n=("id", "size"), med_partial=("partial", "median"),
                mean_partial=("partial", "mean"), med_rows=("n_rows", "median"),
                med_tokM=("tokens_M", "median"), med_cost=("cost_usd", "median"))
           .sort_values("med_partial", ascending=False))
    print(g.round(2).to_string(), "\n")

    sub = df.dropna(subset=["partial", "tokens_M", "n_rows"])
    print("--- EFFORT vs OUTCOME (blind effort should NOT predict score) ---")
    print(f"  corr(partial, n_rows)   = {sub['partial'].corr(sub['n_rows']):+.3f}")
    print(f"  corr(partial, tokens_M) = {sub['partial'].corr(sub['tokens_M']):+.3f}")
    print(f"  corr(partial, n_bash)   = {sub['partial'].corr(sub['n_bash']):+.3f}")
    q = sub["tokens_M"].quantile([.25, .75]).to_dict()
    hi = sub[sub["tokens_M"] >= q[.75]]
    thrash = hi[hi["partial"] == 0]
    print(f"  high-effort & zero-score (thrash): {len(thrash)}/{len(hi)} "
          f"({len(thrash)/len(hi):.0%} of high-effort runs)")
    print(f"    by model: {thrash['model'].value_counts().to_dict()}\n")

    print("--- per-task: median partial + best model ---")
    for task, t in df.groupby("task"):
        best = t.loc[t["partial"].idxmax()]
        print(f"  {task:26s} med={t['partial'].median():.2f} "
              f"max={t['partial'].max():.2f} ({best['model']})")


if __name__ == "__main__":
    main()
