"""Summary plots for the meta-work observational study (SWE-Marathon corpus).

Reads results/metawork/judged/judged_l__sonnet-4.6.parquet (+ the two M replicates
for the reliability panel) and produces the figures that tell the story:

  1. confound_ladder        — the methodological heart: how the meta-work x
                              outcome correlation collapses as you control for
                              task, then model, then both.
  2. metawork_vs_partial    — the scatter, coloured by model, showing the
                              apparent association is a between-model (capability)
                              effect.
  3. model_disposition      — per-model meta-work distribution + thrash share
                              (the real, large between-model finding).
  4. per_task_corr          — within-task correlation per task, sorted; effect
                              biggest on decomposable tasks, ~0 on floored ones.
  5. judge_reliability      — test-retest scatter (rep1 vs rep2), r=0.92.
  6. range_restriction      — within-cell corr vs how much the model varied its
                              meta-work; flat => not range-restriction.

Output: results/metawork/plots/*.png

Usage:
    python scripts/metawork/plot.py
"""
from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

MW = "overall_meta_work"


def _load(results_dir: Path) -> pd.DataFrame:
    df = pd.read_parquet(results_dir / "metawork" / "judged" / "judged_l__sonnet-4.6.parquet")
    df["partial"] = pd.to_numeric(df["partial"], errors="coerce")
    df = df.dropna(subset=[MW, "partial"]).copy()
    df["mw"] = df[MW].astype(float)
    return df


def _save(fig, plots_dir: Path, name: str):
    plots_dir.mkdir(parents=True, exist_ok=True)
    fig.savefig(plots_dir / f"{name}.png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  saved {name}.png")


def _within(df, groupcols):
    """Within-group standardized residual correlation between mw and partial."""
    d = df.copy()
    z = lambda s: (s - s.mean()) / s.std() if s.std() > 1e-9 else np.nan
    d["mz"] = d.groupby(groupcols)["mw"].transform(z)
    d["pz"] = d.groupby(groupcols)["partial"].transform(z)
    s = d.dropna(subset=["mz", "pz"])
    return s["mz"].corr(s["pz"]), len(s)


# ---------- 1. confound ladder ----------

def plot_confound_ladder(df, plots_dir):
    pooled = df["mw"].corr(df["partial"])
    wt, _ = _within(df, ["task"])
    wm, _ = _within(df, ["model"])
    wc, ncell = _within(df, ["task", "model"])

    labels = ["Pooled\n(no control)", "Within-task\n(control difficulty)",
              "Within-model\n(control capability)", "Within (task,model)\n(control both)"]
    vals = [pooled, wt, wm, wc]
    colors = ["#bbb", "#f0ad4e", "#5bc0de", "#2ca02c"]

    fig, ax = plt.subplots(figsize=(8, 4.5))
    bars = ax.bar(labels, vals, color=colors, edgecolor="black", linewidth=0.6)
    for b, v in zip(bars, vals):
        ax.text(b.get_x() + b.get_width() / 2, v + 0.01, f"{v:+.2f}",
                ha="center", va="bottom", fontweight="bold")
    ax.axhline(0, color="black", lw=0.8)
    ax.set_ylabel("corr(meta-work, outcome)")
    ax.set_ylim(-0.05, 0.45)
    ax.set_title("Confound ladder: the apparent meta-work effect is mostly capability\n"
                 f"(n={len(df)} trajectories; within-cell n={ncell})", fontsize=11)
    ax.annotate("looks meaningful…", xy=(1, wt), xytext=(1.1, 0.40),
                fontsize=9, color="#a0712a")
    ax.annotate("…but vanishes when you\nknow the model", xy=(2, wm + 0.005),
                xytext=(2.0, 0.18), fontsize=9, color="#2a7fa0",
                arrowprops=dict(arrowstyle="->", color="#2a7fa0"))
    fig.tight_layout()
    _save(fig, plots_dir, "1_confound_ladder")


# ---------- 2. meta-work vs partial scatter ----------

def plot_scatter(df, plots_dir):
    fig, ax = plt.subplots(figsize=(8, 5.5))
    models = (df.groupby("model")["partial"].median().sort_values(ascending=False).index)
    cmap = plt.cm.viridis(np.linspace(0, 1, len(models)))
    for m, c in zip(models, cmap):
        g = df[df["model"] == m]
        jitter = (np.random.RandomState(0).rand(len(g)) - 0.5) * 0.5
        ax.scatter(g["mw"] + jitter, g["partial"], s=14, alpha=0.45,
                   color=c, label=f"{m} (mw̄={g['mw'].mean():.1f})")
    ax.set_xlabel("judged meta-work (1–9, blind)")
    ax.set_ylabel("task outcome (partial score)")
    ax.set_title("Meta-work vs outcome, coloured by model\n"
                 "the upward trend is between-model (capability), not within-model",
                 fontsize=11)
    ax.legend(fontsize=7, loc="upper left", framealpha=0.9)
    fig.tight_layout()
    _save(fig, plots_dir, "2_metawork_vs_partial")


# ---------- 3. per-model disposition ----------

def plot_model_disposition(df, plots_dir):
    order = df.groupby("model")["mw"].mean().sort_values(ascending=False).index.tolist()
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))

    # left: meta-work distribution (box) per model
    data = [df[df["model"] == m]["mw"].values for m in order]
    axes[0].boxplot(data, vert=False, labels=order, showmeans=True)
    axes[0].set_xlabel("judged meta-work (1–9)")
    axes[0].set_title("Meta-work disposition is per-model and stable", fontsize=11)
    axes[0].invert_yaxis()

    # right: thrash vs structured share per model
    thrash = [(df[df.model == m]["pattern"] == "thrash").mean() for m in order]
    struct = [(df[df.model == m]["pattern"] == "structured").mean() for m in order]
    y = np.arange(len(order))
    axes[1].barh(y - 0.2, thrash, height=0.4, color="#d62728", label="thrash")
    axes[1].barh(y + 0.2, struct, height=0.4, color="#2ca02c", label="structured")
    axes[1].set_yticks(y); axes[1].set_yticklabels(order)
    axes[1].invert_yaxis()
    axes[1].set_xlabel("share of trajectories")
    axes[1].set_title("Weak models thrash; strong models structure", fontsize=11)
    axes[1].legend(fontsize=9)
    fig.tight_layout()
    _save(fig, plots_dir, "3_model_disposition")


# ---------- 4. per-task within-task correlation ----------

def plot_per_task_corr(df, plots_dir):
    rows = []
    for task, t in df.groupby("task"):
        if t["partial"].std() > 1e-9 and t["mw"].std() > 1e-9:
            rows.append((task, t["mw"].corr(t["partial"]), t["partial"].median(), len(t)))
    R = pd.DataFrame(rows, columns=["task", "corr", "median_partial", "n"]).sort_values("corr")
    # colour by whether outcome is "floored" (degenerate)
    colors = ["#d62728" if mp < 0.05 else "#2ca02c" for mp in R["median_partial"]]
    fig, ax = plt.subplots(figsize=(8, 7))
    ax.barh(R["task"], R["corr"], color=colors, edgecolor="black", linewidth=0.4)
    ax.axvline(0, color="black", lw=0.8)
    ax.set_xlabel("within-task corr(meta-work, outcome)")
    ax.set_title("Within-task effect is biggest on decomposable tasks,\n"
                 "≈0 on floored tasks (red = task median outcome < 0.05)", fontsize=11)
    fig.tight_layout()
    _save(fig, plots_dir, "4_per_task_corr")


# ---------- 5. judge reliability ----------

def plot_reliability(results_dir, plots_dir):
    p1 = results_dir / "metawork" / "judged" / "judged_m__sonnet-4.6.parquet"
    p2 = results_dir / "metawork" / "judged" / "judged_mrep2__sonnet-4.6.parquet"
    if not (p1.exists() and p2.exists()):
        print("  (skipping reliability: need both M replicates)")
        return
    r1 = pd.read_parquet(p1)[["id", MW]]
    r2 = pd.read_parquet(p2)[["id", MW]]
    m = r1.merge(r2, on="id", suffixes=("_1", "_2")).dropna()
    a, b = m[f"{MW}_1"].astype(float), m[f"{MW}_2"].astype(float)
    r = a.corr(b)
    fig, ax = plt.subplots(figsize=(5.5, 5.5))
    j = np.random.RandomState(0).rand(len(m), 2) * 0.3 - 0.15
    ax.scatter(a + j[:, 0], b + j[:, 1], s=20, alpha=0.5, color="#1f77b4")
    ax.plot([1, 9], [1, 9], "k--", lw=0.8)
    ax.set_xlabel("meta-work, judge run 1")
    ax.set_ylabel("meta-work, judge run 2")
    ax.set_title(f"Judge test-retest reliability: r={r:.2f}\n"
                 f"(same Sonnet-4.6 judge, n={len(m)}) — scores are not noise",
                 fontsize=11)
    fig.tight_layout()
    _save(fig, plots_dir, "5_judge_reliability")


# ---------- 6. range-restriction test ----------

def plot_range_restriction(df, plots_dir):
    rows = []
    for (t, m), g in df.groupby(["task", "model"]):
        if len(g) >= 5 and g["mw"].std() > 1e-9 and g["partial"].std() > 1e-9:
            rows.append((g["mw"].std(), g["mw"].corr(g["partial"])))
    R = pd.DataFrame(rows, columns=["spread", "corr"])
    fig, ax = plt.subplots(figsize=(7, 5))
    ax.scatter(R["spread"], R["corr"], s=22, alpha=0.5, color="#7f3fbf")
    # binned means
    R["bin"] = pd.qcut(R["spread"], 4, duplicates="drop")
    bm = R.groupby("bin", observed=True).agg(x=("spread", "mean"), y=("corr", "mean"))
    ax.plot(bm["x"], bm["y"], "o-", color="black", lw=2, label="binned mean")
    ax.axhline(0, color="grey", lw=0.6)
    ax.set_xlabel("within-cell meta-work spread (sd, 1–9 scale)")
    ax.set_ylabel("within-cell corr(meta-work, outcome)")
    ax.set_title("Range-restriction check: cells where the model varied\n"
                 "meta-work MORE do NOT show a steeper effect (flat line)\n"
                 "→ the small effect is real, not hidden by narrow range", fontsize=10)
    ax.legend()
    fig.tight_layout()
    _save(fig, plots_dir, "6_range_restriction")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--results-dir", default="results")
    args = ap.parse_args()
    results_dir = Path(args.results_dir)
    plots_dir = results_dir / "metawork" / "plots"

    df = _load(results_dir)
    print(f"loaded {len(df)} judged trajectories -> plotting to {plots_dir}/")
    plot_confound_ladder(df, plots_dir)
    plot_scatter(df, plots_dir)
    plot_model_disposition(df, plots_dir)
    plot_per_task_corr(df, plots_dir)
    plot_reliability(results_dir, plots_dir)
    plot_range_restriction(df, plots_dir)
    print("done.")


if __name__ == "__main__":
    main()
