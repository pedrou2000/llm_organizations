"""Plots for the v2 judge variance experiment (nested rubric-vs-scoring).

Reads variance_decomposition__M<M>_K<K>.parquet (produced by measure_variance.py)
and turns the text-table decomposition into figures. The experiment holds a
trajectory fixed and asks how much the judge's score wobbles, split into:
  sigma_scoring — Stage-B agentic noise (pinned rubric, K rescorings)
  sigma_rubric  — the ruler moving (M fresh rubrics)
  total_sd      — what a caller of judge_metawork sees

  1. decomposition   — per spine-gap: sigma_scoring vs sigma_rubric side by side,
                       per trajectory. The headline: rubric dominates scoring.
  2. target_vs_obs   — sigma on target vs observed: targets have ZERO scoring
                       noise (pin works) but nonzero rubric noise (ruler moves) —
                       the mechanism behind the gap variance.
  3. acceptance      — total_sd per metric vs the 0.5 acceptance bar.

Output: results/metawork/judged/v2_adaptive/experiments/variance/plots/*.png

Usage:
    python scripts/metawork/judge/v2_adaptive/experiments/variance/plot_variance.py --rubrics 10 --scorings 10
"""
from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

_EXP = Path("results/metawork/judged/v2_adaptive/experiments/variance")
_DATA = _EXP / "data"
_PLOTS = _EXP / "plots"
SPINE = ["orientation_research", "decomposition_milestones", "verification_strategy",
         "progress_monitoring", "adaptation_correction"]
ACCEPT_SD = 0.5
C_SCORING = "#4f8ff7"   # Stage-B agentic noise
C_RUBRIC = "#f2a541"    # rubric (ruler) noise


def _save(fig, name: str):
    _PLOTS.mkdir(parents=True, exist_ok=True)
    fig.savefig(_PLOTS / f"{name}.png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  saved {name}.png")


def plot_decomposition(dec: pd.DataFrame):
    """Per spine-gap, sigma_scoring vs sigma_rubric, one subplot per trajectory."""
    trajs = dec["trajectory"].unique()
    fig, axes = plt.subplots(1, len(trajs), figsize=(7 * len(trajs), 5.5), sharey=True)
    axes = np.atleast_1d(axes)
    labels = [d.replace("_", "\n") for d in SPINE]
    y = np.arange(len(SPINE))
    for ax, tname in zip(axes, trajs):
        t = dec[dec.trajectory == tname].set_index("metric")
        sc = [t.loc[f"{d}__gap", "sd_scoring"] for d in SPINE]
        ru = [t.loc[f"{d}__gap", "sd_rubric"] for d in SPINE]
        ax.barh(y - 0.2, sc, height=0.4, color=C_SCORING, label="σ scoring (Stage B)")
        ax.barh(y + 0.2, ru, height=0.4, color=C_RUBRIC, label="σ rubric (ruler)")
        ax.set_yticks(y); ax.set_yticklabels(labels, fontsize=9)
        ax.invert_yaxis()
        ax.set_xlabel("SD of gap (0-10 scale)")
        ax.set_title(tname, fontsize=11)
        ax.legend(fontsize=8, loc="lower right")
    fig.suptitle("Variance decomposition per dimension: the RULER (rubric) wobbles "
                 "more than the READER (scoring)", fontsize=12)
    fig.tight_layout()
    _save(fig, "1_decomposition")


def plot_target_vs_obs(dec: pd.DataFrame):
    """The mechanism: targets carry zero scoring-noise (pin works) but real
    rubric-noise; observed carries scoring-noise. Averaged over spine dims."""
    trajs = dec["trajectory"].unique()
    fig, ax = plt.subplots(figsize=(9, 5))
    x = np.arange(len(trajs)); w = 0.2
    def avg(t, suffix, comp):
        s = dec[dec.trajectory == t].set_index("metric")
        return np.mean([s.loc[f"{d}__{suffix}", comp] for d in SPINE])
    obs_sc = [avg(t, "observed", "sd_scoring") for t in trajs]
    obs_ru = [avg(t, "observed", "sd_rubric") for t in trajs]
    tgt_sc = [avg(t, "target", "sd_scoring") for t in trajs]
    tgt_ru = [avg(t, "target", "sd_rubric") for t in trajs]
    ax.bar(x - 1.5*w, obs_sc, w, color=C_SCORING, label="observed · σ scoring")
    ax.bar(x - 0.5*w, obs_ru, w, color=C_SCORING, alpha=0.5, label="observed · σ rubric")
    ax.bar(x + 0.5*w, tgt_sc, w, color=C_RUBRIC, label="target · σ scoring (≈0: pin works)")
    ax.bar(x + 1.5*w, tgt_ru, w, color=C_RUBRIC, alpha=0.5, label="target · σ rubric")
    ax.set_xticks(x); ax.set_xticklabels(trajs)
    ax.set_ylabel("mean SD over spine dims")
    ax.set_title("Mechanism: TARGET has ~zero scoring-noise (rubric held fixed → pin works)\n"
                 "but real rubric-noise (fresh synthesis moves the bar)", fontsize=11)
    ax.legend(fontsize=8)
    fig.tight_layout()
    _save(fig, "2_target_vs_observed")


def plot_acceptance(dec: pd.DataFrame):
    """total_sd per headline+spine-gap metric vs the acceptance bar."""
    metrics = ["overall_gap"] + [f"{d}__gap" for d in SPINE]
    trajs = dec["trajectory"].unique()
    fig, ax = plt.subplots(figsize=(10, 5.5))
    x = np.arange(len(metrics)); w = 0.8 / len(trajs)
    for i, tname in enumerate(trajs):
        t = dec[dec.trajectory == tname].set_index("metric")
        vals = [t.loc[m, "total_sd"] if m in t.index else np.nan for m in metrics]
        ax.bar(x + i*w - 0.4 + w/2, vals, w, label=tname)
    ax.axhline(ACCEPT_SD, color="red", ls="--", lw=1.2,
               label=f"acceptance bar ({ACCEPT_SD})")
    ax.set_xticks(x)
    ax.set_xticklabels(["overall"] + [d.replace("_", "\n") for d in SPINE], fontsize=8)
    ax.set_ylabel("total SD (run-to-run)")
    ax.set_title("Judge reliability per metric: total run-to-run SD vs the 0.5 bar\n"
                 "(overall_gap ≈0.55 — just over; dominated by rubric, not scoring)",
                 fontsize=11)
    ax.legend(fontsize=8)
    fig.tight_layout()
    _save(fig, "3_acceptance")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rubrics", type=int, default=10)
    ap.add_argument("--scorings", type=int, default=10)
    args = ap.parse_args()
    p = _DATA / f"variance_decomposition__M{args.rubrics}_K{args.scorings}.parquet"
    dec = pd.read_parquet(p)
    print(f"loaded decomposition ({len(dec)} rows, "
          f"{dec['trajectory'].nunique()} trajectories) from {p.name}")
    plot_decomposition(dec)
    plot_target_vs_obs(dec)
    plot_acceptance(dec)
    print("done.")


if __name__ == "__main__":
    main()
