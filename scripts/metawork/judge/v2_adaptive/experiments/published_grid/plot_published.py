"""Plots for the v2 task-adaptive meta-work judge over the published corpus.

The v2 analogue of judge/v1_fixed/plot.py. The headline metric is the SIGNED
GAP (observed − task-appropriate level), not v1's absolute `overall_meta_work`:
a gap near 0 is well-calibrated, negative is under-investment, positive is
over-investment/ceremony. So plots read against 0, and "more negative = worse".

  1. confound_ladder     — corr(meta-work gap, outcome) pooled → within-task →
                           within-model → within-both. [CROSS-MODEL: see caveat]
  2. gap_vs_partial      — scatter of overall_gap vs outcome, coloured by model.
  3. model_disposition   — per-model gap distribution + under-investment share
                           (gap < −1). [CROSS-MODEL: see caveat]
  4. per_task_corr       — within-task corr(gap, outcome), sorted.
  5. dimension_profile   — mean gap per spine dimension (where the deficit lives).
  6. range_restriction   — within-cell corr vs within-cell gap spread.

CAVEAT (printed on cross-model figures): the published flat_text is far lossier
for some models than others, so cross-model plots (1, 3) partly reflect harvest
fidelity, not just meta-work. Within-model plots (4, 6) are unaffected.

Output: results/metawork/judged/v2_adaptive/experiments/published_grid/plots/*.png

Usage:
    python scripts/metawork/judge/v2_adaptive/experiments/published_grid/plot_published.py --tag grid
"""
from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

GAP = "overall_gap"
SPINE = ["orientation_research", "decomposition_milestones", "verification_strategy",
         "progress_monitoring", "adaptation_correction"]
_CAVEAT = "cross-model: published flat_text fidelity varies by model — treat with care"


def _exp_dir(results_dir: Path, tag: str) -> Path:
    return (results_dir / "metawork" / "judged" / "v2_adaptive"
            / "experiments" / f"published_{tag}")


def _load(results_dir: Path, tag: str, score_model: str) -> pd.DataFrame:
    p = _exp_dir(results_dir, tag) / f"scored_published_{tag}__{score_model}.parquet"
    df = pd.read_parquet(p)
    df["partial"] = pd.to_numeric(df["partial"], errors="coerce")
    df = df.dropna(subset=[GAP, "partial"]).copy()
    df["gap"] = df[GAP].astype(float)
    return df


def _save(fig, plots_dir: Path, name: str):
    plots_dir.mkdir(parents=True, exist_ok=True)
    fig.savefig(plots_dir / f"{name}.png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  saved {name}.png")


def _within(df, groupcols):
    """Within-group standardized residual correlation between gap and partial."""
    d = df.copy()
    z = lambda s: (s - s.mean()) / s.std() if s.std() > 1e-9 else np.nan
    d["gz"] = d.groupby(groupcols)["gap"].transform(z)
    d["pz"] = d.groupby(groupcols)["partial"].transform(z)
    s = d.dropna(subset=["gz", "pz"])
    return (s["gz"].corr(s["pz"]) if len(s) > 2 else np.nan), len(s)


def plot_confound_ladder(df, plots_dir):
    pooled = df["gap"].corr(df["partial"])
    wt, _ = _within(df, ["task"])
    wm, _ = _within(df, ["model"])
    wc, ncell = _within(df, ["task", "model"])
    labels = ["Pooled", "Within-task", "Within-model", "Within (task,model)"]
    vals = [pooled, wt, wm, wc]
    colors = ["#bbb", "#f0ad4e", "#5bc0de", "#2ca02c"]
    fig, ax = plt.subplots(figsize=(8, 4.8))
    bars = ax.bar(labels, vals, color=colors, edgecolor="black", linewidth=0.6)
    for b, v in zip(bars, vals):
        if not np.isnan(v):
            ax.text(b.get_x() + b.get_width() / 2, v + (0.01 if v >= 0 else -0.03),
                    f"{v:+.2f}", ha="center", va="bottom" if v >= 0 else "top",
                    fontweight="bold")
    ax.axhline(0, color="black", lw=0.8)
    ax.set_ylabel("corr(meta-work gap, outcome)")
    ax.set_title("Confound ladder: does the gap↔outcome link survive controls?\n"
                 f"(n={len(df)}; within-cell n={ncell})  ·  {_CAVEAT}", fontsize=10)
    fig.tight_layout()
    _save(fig, plots_dir, "1_confound_ladder")


def plot_scatter(df, plots_dir):
    fig, ax = plt.subplots(figsize=(8, 5.5))
    models = df.groupby("model")["partial"].median().sort_values(ascending=False).index
    cmap = plt.cm.viridis(np.linspace(0, 1, len(models)))
    for m, c in zip(models, cmap):
        g = df[df["model"] == m]
        ax.scatter(g["gap"], g["partial"], s=26, alpha=0.6, color=c,
                   label=f"{m} (gap̄={g['gap'].mean():+.1f})")
    ax.axvline(0, color="grey", lw=0.8, ls="--")
    ax.set_xlabel("meta-work gap (observed − task-appropriate; 0 = calibrated)")
    ax.set_ylabel("task outcome (partial score)")
    ax.set_title("Meta-work gap vs outcome, coloured by model", fontsize=11)
    ax.legend(fontsize=7, loc="best", framealpha=0.9)
    fig.tight_layout()
    _save(fig, plots_dir, "2_gap_vs_partial")


def plot_model_disposition(df, plots_dir):
    order = df.groupby("model")["gap"].mean().sort_values().index.tolist()
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    data = [df[df["model"] == m]["gap"].values for m in order]
    axes[0].boxplot(data, vert=False, tick_labels=order, showmeans=True)
    axes[0].axvline(0, color="grey", lw=0.8, ls="--")
    axes[0].set_xlabel("meta-work gap (0 = calibrated, − = under-invests)")
    axes[0].set_title("Gap disposition per model", fontsize=11)
    axes[0].invert_yaxis()
    under = [(df[df.model == m]["gap"] < -1).mean() for m in order]
    y = np.arange(len(order))
    axes[1].barh(y, under, color="#d62728")
    axes[1].set_yticks(y); axes[1].set_yticklabels(order); axes[1].invert_yaxis()
    axes[1].set_xlabel("share of trajectories with gap < −1")
    axes[1].set_title("Under-investment share per model", fontsize=11)
    fig.suptitle(_CAVEAT, fontsize=8, y=1.0)
    fig.tight_layout()
    _save(fig, plots_dir, "3_model_disposition")


def plot_per_task_corr(df, plots_dir):
    rows = []
    for task, t in df.groupby("task"):
        if t["partial"].std() > 1e-9 and t["gap"].std() > 1e-9:
            rows.append((task, t["gap"].corr(t["partial"]), t["partial"].median(), len(t)))
    R = pd.DataFrame(rows, columns=["task", "corr", "median_partial", "n"]).sort_values("corr")
    colors = ["#d62728" if mp < 0.05 else "#2ca02c" for mp in R["median_partial"]]
    fig, ax = plt.subplots(figsize=(8, 7))
    ax.barh(R["task"], R["corr"], color=colors, edgecolor="black", linewidth=0.4)
    ax.axvline(0, color="black", lw=0.8)
    ax.set_xlabel("within-task corr(meta-work gap, outcome)")
    ax.set_title("Within-task gap↔outcome correlation (red = task median outcome < 0.05)",
                 fontsize=11)
    fig.tight_layout()
    _save(fig, plots_dir, "4_per_task_corr")


def plot_dimension_profile(df, plots_dir):
    gaps = [f"{d}__gap" for d in SPINE if f"{d}__gap" in df.columns]
    means = [df[g].mean() for g in gaps]
    errs = [df[g].std() / np.sqrt(df[g].notna().sum()) for g in gaps]
    names = [d.replace("_", "\n") for d in SPINE if f"{d}__gap" in df.columns]
    fig, ax = plt.subplots(figsize=(9, 5))
    colors = ["#d62728" if m < -2 else ("#f0ad4e" if m < -1 else "#2ca02c") for m in means]
    ax.bar(names, means, yerr=errs, color=colors, edgecolor="black",
           linewidth=0.6, capsize=4)
    ax.axhline(0, color="black", lw=0.8)
    ax.axhline(-1, color="grey", lw=0.6, ls=":")
    ax.set_ylabel("mean gap (observed − target)")
    ax.set_title("Where the meta-work deficit lives: mean gap per spine dimension\n"
                 f"(n={len(df)}; more negative = larger under-investment)", fontsize=11)
    fig.tight_layout()
    _save(fig, plots_dir, "5_dimension_profile")


def plot_range_restriction(df, plots_dir):
    rows = []
    for (t, m), g in df.groupby(["task", "model"]):
        if len(g) >= 5 and g["gap"].std() > 1e-9 and g["partial"].std() > 1e-9:
            rows.append((g["gap"].std(), g["gap"].corr(g["partial"])))
    if len(rows) < 4:
        print("  (skipping range_restriction: need multi-trajectory cells; "
              "the 1-per-cell grid has none)")
        return
    R = pd.DataFrame(rows, columns=["spread", "corr"])
    fig, ax = plt.subplots(figsize=(7, 5))
    ax.scatter(R["spread"], R["corr"], s=22, alpha=0.5, color="#7f3fbf")
    ax.axhline(0, color="grey", lw=0.6)
    ax.set_xlabel("within-cell gap spread (sd)")
    ax.set_ylabel("within-cell corr(gap, outcome)")
    ax.set_title("Range-restriction check", fontsize=11)
    fig.tight_layout()
    _save(fig, plots_dir, "6_range_restriction")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tag", default="grid")
    ap.add_argument("--score-model", default="opus-4.8")
    ap.add_argument("--results-dir", default="results")
    args = ap.parse_args()
    results_dir = Path(args.results_dir)
    plots_dir = _exp_dir(results_dir, args.tag) / "plots"

    df = _load(results_dir, args.tag, args.score_model)
    print(f"loaded {len(df)} v2-judged trajectories "
          f"({df['model'].nunique()} models x {df['task'].nunique()} tasks) "
          f"-> plotting to {plots_dir}/")
    plot_confound_ladder(df, plots_dir)
    plot_scatter(df, plots_dir)
    plot_model_disposition(df, plots_dir)
    plot_per_task_corr(df, plots_dir)
    plot_dimension_profile(df, plots_dir)
    plot_range_restriction(df, plots_dir)
    print("done.")


if __name__ == "__main__":
    main()
