"""Plot helpers for verify-probe sweep results."""
from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


COND_ORDER = ["forced", "neutral", "anti"]
COND_COLORS = {"forced": "#888", "neutral": "#1f77b4", "anti": "#2ca02c"}
DEFAULT_LEVELS = [f"Level {i}" for i in range(1, 6)]


def _save(fig, plots_dir: Path, name: str) -> None:
    plots_dir.mkdir(parents=True, exist_ok=True)
    fig.savefig(plots_dir / f"{name}.png", dpi=150, bbox_inches="tight")
    print(f"  saved {plots_dir}/{name}.png")


def plot_verify_by_level(
    summary: pd.DataFrame,
    *,
    levels: list[str] = DEFAULT_LEVELS,
    plots_dir: Path | None = None,
    save_as: str | None = "verify_by_level",
) -> None:
    models = sorted(summary["model_label"].unique())
    fig, axes = plt.subplots(1, len(models), figsize=(4.5 * len(models), 4), sharey=True)
    if len(models) == 1:
        axes = [axes]
    for ax, m in zip(axes, models):
        for c in COND_ORDER:
            sub = (summary.query("model_label == @m and condition == @c")
                          .set_index("level").reindex(levels))
            ax.plot(levels, sub["verify_rate"], marker="o",
                    label=c, color=COND_COLORS[c])
        ax.set_ylim(-0.05, 1.05)
        ax.set_xticks(levels)
        ax.set_xticklabels([l.replace("Level ", "L") for l in levels])
        ax.set_title(m)
        ax.set_ylabel("P(verify_called)")
        ax.grid(True, alpha=0.3)
        ax.legend(loc="best")
    fig.suptitle("Verify-rate by problem level — flat = closure bias")
    fig.tight_layout()
    if plots_dir is not None and save_as:
        _save(fig, Path(plots_dir), save_as)
    plt.show()


def plot_verify_vs_passrate(
    summary: pd.DataFrame,
    substrate: pd.DataFrame,
    *,
    plots_dir: Path | None = None,
    save_as: str | None = "verify_vs_passrate",
) -> None:
    if substrate.empty:
        print("no substrate parquet — run substrate sweep first")
        return
    pass_rate = (
        substrate.groupby(["model_label", "level"])["correct"].mean()
        .rename("pass_rate").reset_index()
    )
    merged = summary.merge(pass_rate, on=["model_label", "level"], how="left")

    models = sorted(merged["model_label"].unique())
    fig, axes = plt.subplots(1, len(models), figsize=(4.5 * len(models), 4), sharey=True)
    if len(models) == 1:
        axes = [axes]
    for ax, m in zip(axes, models):
        for c in COND_ORDER:
            sub = merged.query("model_label == @m and condition == @c").sort_values("pass_rate")
            ax.plot(sub["pass_rate"], sub["verify_rate"], marker="o",
                    label=c, color=COND_COLORS[c])
        ax.set_xlim(-0.05, 1.05)
        ax.set_ylim(-0.05, 1.05)
        ax.invert_xaxis()
        ax.set_xlabel("substrate pass rate (←  harder)")
        ax.set_ylabel("P(verify_called)")
        ax.set_title(m)
        ax.grid(True, alpha=0.3)
        ax.legend(loc="best")
    fig.suptitle("Verify-rate as function of how hard the problem is")
    fig.tight_layout()
    if plots_dir is not None and save_as:
        _save(fig, Path(plots_dir), save_as)
    plt.show()


def plot_accuracy_by_level(
    summary: pd.DataFrame,
    *,
    levels: list[str] = DEFAULT_LEVELS,
    plots_dir: Path | None = None,
    save_as: str | None = "accuracy_by_level",
) -> None:
    models = sorted(summary["model_label"].unique())
    fig, axes = plt.subplots(1, len(models), figsize=(4.5 * len(models), 4), sharey=True)
    if len(models) == 1:
        axes = [axes]
    for ax, m in zip(axes, models):
        for c in COND_ORDER:
            sub = (summary.query("model_label == @m and condition == @c")
                          .set_index("level").reindex(levels))
            ax.plot(levels, sub["accuracy"], marker="o",
                    label=c, color=COND_COLORS[c])
        ax.set_ylim(-0.05, 1.05)
        ax.set_xticks(levels)
        ax.set_xticklabels([l.replace("Level ", "L") for l in levels])
        ax.set_title(m)
        ax.set_ylabel("accuracy")
        ax.grid(True, alpha=0.3)
        ax.legend(loc="best")
    fig.suptitle("Final-answer accuracy by level")
    fig.tight_layout()
    if plots_dir is not None and save_as:
        _save(fig, Path(plots_dir), save_as)
    plt.show()
