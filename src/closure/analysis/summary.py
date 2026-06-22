"""Aggregation helpers for sweep + substrate parquets."""
from __future__ import annotations

from pathlib import Path

import pandas as pd


# ---------- loaders ----------


def load_all_sweeps(
    results_dir: Path | str = "results",
    *,
    probe: str | None = None,
    dataset: str | None = None,
) -> pd.DataFrame:
    """Load all sweep parquets matching the optional probe/dataset filters."""
    results_dir = Path(results_dir)
    sweep_dir = results_dir / "closure" / "sweep"
    if not sweep_dir.exists():
        raise FileNotFoundError(f"no sweep dir at {sweep_dir}")

    paths = sorted(sweep_dir.glob("*.parquet"))
    if probe:
        paths = [p for p in paths if p.stem.startswith(f"{probe}__")]
    if dataset:
        paths = [p for p in paths if f"__{dataset}__" in p.stem]
    if not paths:
        raise FileNotFoundError(
            f"no sweep parquet files in {sweep_dir} "
            f"(probe={probe!r}, dataset={dataset!r})"
        )
    return pd.concat([pd.read_parquet(p) for p in paths], ignore_index=True)


def load_all_substrates(
    results_dir: Path | str = "results",
    *,
    dataset: str | None = None,
) -> pd.DataFrame:
    """Load all substrate parquets, optionally filtered by dataset."""
    results_dir = Path(results_dir)
    sub_dir = results_dir / "closure" / "substrate"
    if not sub_dir.exists():
        return pd.DataFrame()

    paths = sorted(sub_dir.glob("*.parquet"))
    if dataset:
        paths = [p for p in paths if p.stem.startswith(f"{dataset}__")]
    frames = [pd.read_parquet(p) for p in paths]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


# ---------- summaries ----------


def cell_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Per-(model, condition, level) aggregates."""
    return (
        df.groupby(["model_label", "condition", "level"])
        .agg(
            verify_rate=("verify_called", "mean"),
            mean_verifies=("verify_calls", "mean"),
            accuracy=("final_correct", "mean"),
            submit_rate=("submit_calls", lambda s: (s > 0).mean()),
            mean_cost=("cost_usd", "mean"),
            n_trials=("final_correct", "size"),
        )
        .reset_index()
    )


def discrimination_slope(
    summary: pd.DataFrame,
    levels: list[str] | None = None,
) -> pd.DataFrame:
    """Per (model, condition): slope of verify_rate as level rises 1->5.
    Positive = more verification on harder problems (good discrimination).
    """
    if levels is None:
        levels = [f"Level {i}" for i in range(1, 6)]
    level_idx = {lvl: i for i, lvl in enumerate(levels, start=1)}
    rows = []
    for (m, c), sub in summary.groupby(["model_label", "condition"]):
        s = sub.set_index("level").reindex(levels)
        x = pd.Series([level_idx[l] for l in s.index], index=s.index, dtype=float)
        y = s["verify_rate"]
        mask = y.notna()
        slope = float("nan")
        if mask.sum() >= 2:
            xc, yc = x[mask], y[mask]
            slope = (
                ((xc - xc.mean()) * (yc - yc.mean())).sum()
                / ((xc - xc.mean()) ** 2).sum()
            )
        rows.append({
            "model_label": m,
            "condition":   c,
            "slope":       slope,
            **{lvl: y.get(lvl) for lvl in levels},
        })
    return pd.DataFrame(rows)
