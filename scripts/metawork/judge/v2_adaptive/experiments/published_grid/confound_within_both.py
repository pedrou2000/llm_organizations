"""The full confound ladder INCLUDING within-(task,model) — the control that
killed the v1 study.

The 1-per-cell grid could not compute the last rung (need >1 trajectory per
(task,model) cell to standardize within it). This reads a multi-per-cell scoring
(produced with --all --models ...) and computes:

  pooled            corr(gap, outcome), no control
  within-task       standardize within each task  (removes DIFFICULTY)
  within-model      standardize within each model (removes CAPABILITY)
  within-both       standardize within each (task,model) cell (removes BOTH)

The within-both rung is the honest test: if the gap↔outcome link is just
"capable models on easy tasks look good", it collapses here — as it did for v1.

Floored / zero-variance cells carry no information for a within-cell correlation
(if outcome never varies in a cell, its residuals are all ~0), so within-both is
computed ONLY over cells with >= `min_n` trajectories AND outcome std > 0; the
number of contributing cells + trajectories is reported so the estimate is
transparent.

Usage:
    python .../confound_within_both.py --tag within4
"""
from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def _exp_dir(results_dir: Path, tag: str) -> Path:
    return (results_dir / "metawork" / "judged" / "v2_adaptive"
            / "experiments" / f"published_{tag}")


def _z(s: pd.Series) -> pd.Series:
    return (s - s.mean()) / s.std() if s.std() > 1e-9 else s * np.nan


def _within(df: pd.DataFrame, groupcols, min_n: int = 1) -> tuple[float, int, int]:
    """Within-group residual correlation of gap vs outcome.

    Standardizes both variables within each group, then correlates the pooled
    residuals. Only groups with >= min_n rows AND outcome variance contribute
    (a group with constant outcome yields NaN residuals and is dropped).
    Returns (r, n_trajectories_used, n_groups_used).
    """
    d = df.copy()
    d["gz"] = d.groupby(groupcols)["gap"].transform(_z)
    d["pz"] = d.groupby(groupcols)["partial"].transform(_z)
    # drop cells below min_n
    sizes = d.groupby(groupcols)["gap"].transform("size")
    d = d[sizes >= min_n]
    s = d.dropna(subset=["gz", "pz"])
    n_groups = s.groupby(groupcols).ngroups if len(s) else 0
    r = s["gz"].corr(s["pz"]) if len(s) > 2 else np.nan
    return r, len(s), n_groups


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tag", default="within4")
    ap.add_argument("--score-model", default="opus-4.8")
    ap.add_argument("--results-dir", default="results")
    ap.add_argument("--min-n", type=int, default=3,
                    help="min trajectories per cell to contribute to within-both")
    args = ap.parse_args()
    results_dir = Path(args.results_dir)
    exp = _exp_dir(results_dir, args.tag)

    df = pd.read_parquet(exp / f"scored_published_{args.tag}__{args.score_model}.parquet")
    df["partial"] = pd.to_numeric(df["partial"], errors="coerce")
    df = df.dropna(subset=["overall_gap", "partial"]).copy()
    df["gap"] = df["overall_gap"].astype(float)

    print(f"loaded {len(df)} scored trajectories  "
          f"({df.model.nunique()} models x {df.task.nunique()} tasks)")
    cells = df.groupby(["model", "task"]).size()
    print(f"cells: {len(cells)}  median traj/cell: {int(cells.median())}  "
          f"range {cells.min()}-{cells.max()}")

    # --- the ladder ---
    pooled = df["gap"].corr(df["partial"])
    wt, nt, gt = _within(df, ["task"])
    wm, nm, gm = _within(df, ["model"])
    wb, nb, gb = _within(df, ["task", "model"], min_n=args.min_n)

    print(f"\n{'='*70}\nCONFOUND LADDER (gap ↔ outcome)\n{'='*70}")
    print(f"  pooled          r = {pooled:+.3f}   (n={len(df)})")
    print(f"  within-task     r = {wt:+.3f}   (n={nt}, {gt} tasks)   [removes difficulty]")
    print(f"  within-model    r = {wm:+.3f}   (n={nm}, {gm} models)  [removes capability]")
    print(f"  within-BOTH     r = {wb:+.3f}   (n={nb}, {gb} cells, min_n={args.min_n})  "
          f"[removes DIFFICULTY + CAPABILITY]")
    print(f"{'='*70}")
    if not np.isnan(wb):
        verdict = ("SURVIVES — effect is within-cell, not a task/model artifact"
                   if wb >= 0.15 else
                   "COLLAPSES — like v1, the effect was mostly task/model confound"
                   if wb < 0.05 else
                   "WEAK — partial survival; interpret cautiously")
        print(f"  VERDICT: within-both r={wb:+.3f} -> {verdict}")

    # --- figure ---
    labels = ["Pooled", "Within-task\n(difficulty)", "Within-model\n(capability)",
              f"Within-BOTH\n(min_n={args.min_n})"]
    vals = [pooled, wt, wm, wb]
    colors = ["#bbb", "#f0ad4e", "#5bc0de", "#2ca02c"]
    fig, ax = plt.subplots(figsize=(8.5, 5))
    bars = ax.bar(labels, vals, color=colors, edgecolor="black", linewidth=0.6)
    for b, v in zip(bars, vals):
        if not np.isnan(v):
            ax.text(b.get_x() + b.get_width()/2, v + 0.01, f"{v:+.2f}",
                    ha="center", va="bottom", fontweight="bold")
    ax.axhline(0, color="black", lw=0.8)
    ax.set_ylabel("corr(meta-work gap, outcome)")
    ax.set_title("Full confound ladder: does the meta-work↔outcome link survive\n"
                 f"controlling for BOTH difficulty and capability?  "
                 f"(within-both: {gb} cells, {nb} trajectories)", fontsize=11)
    fig.tight_layout()
    out = exp / "plots" / "6_confound_within_both.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=150, bbox_inches="tight")
    print(f"\n  saved {out}")


if __name__ == "__main__":
    main()
