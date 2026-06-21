"""Batch meta-work judging over a harvested trajectory corpus.

Reuses the generic `closure.sweep.gather_with_progress` harness (bounded
concurrency + progress/ETA/cost). Judges each trajectory BLIND, then joins
the metadata (model / partial / correctness / gates) back AFTER judging so
the meta-work score can never be contaminated by the outcome.

Output: results/metawork/judged_<size>__<judge_model>.parquet
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from ..sweep import gather_with_progress
from .judge import DEFAULT_JUDGE_MODEL_LABEL, judge_trajectory

# Columns from the harvest table we keep alongside the judge's scores.
_META_COLS = [
    "id", "task", "model", "reward", "partial", "correctness", "ux",
    "gates", "tokens", "cost", "steps", "n_rows", "n_plan_tool",
    "n_write", "n_bash", "n_submit", "first_write_frac", "flat_chars",
]


async def judge_corpus(
    *,
    size: str = "s",
    judge_model_label: str = DEFAULT_JUDGE_MODEL_LABEL,
    concurrency: int = 16,
    results_dir: Path | str = "results",
    limit: int | None = None,
) -> pd.DataFrame:
    """Judge every trajectory in harvest_<size>.parquet.

    `limit` optionally caps how many rows to judge (handy for a first cheap
    pass). Persists to judged_<size>__<judge_model>.parquet.
    """
    results_dir = Path(results_dir)
    harvest_path = results_dir / "metawork" / f"harvest_{size}.parquet"
    harvest = pd.read_parquet(harvest_path)
    if limit is not None:
        harvest = harvest.head(limit).copy()

    # Judge blind: pass ONLY flat_text. Metadata joined back afterward.
    flats = harvest["flat_text"].tolist()
    print(f"judging {len(flats)} trajectories (size={size}, "
          f"judge={judge_model_label}, conc={concurrency})")

    verdicts = await gather_with_progress(
        [judge_trajectory(ft, judge_model_label) for ft in flats],
        limit=concurrency,
        label=f"metawork-judge-{size}",
        log_each=False,
        log_fields=("overall_meta_work", "pattern"),
    )

    vdf = pd.DataFrame(verdicts).reset_index(drop=True)
    meta = harvest[[c for c in _META_COLS if c in harvest.columns]].reset_index(drop=True)
    out = pd.concat([meta, vdf], axis=1)
    out["judge_model"] = judge_model_label

    out_path = results_dir / "metawork" / f"judged_{size}__{judge_model_label}.parquet"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(out_path)

    err = out["error"].notna().sum() if "error" in out.columns else 0
    parsed = out["overall_meta_work"].notna().sum()
    print(f"\njudged {len(out)} trajectories  parsed_ok={parsed}  errors/parse_fail={err}")
    print(f"  cost=${out['cost_usd'].sum():.2f}  -> {out_path}")
    return out
