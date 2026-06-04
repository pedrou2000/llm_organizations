"""Generic sweep harness: bounded-concurrency runner + per-cell sweep.

Probe-agnostic: takes a probe object satisfying ProbeProtocol and a pool
of problems. Calls `probe.run_trial(ex, condition, model_id)` for every
(condition, problem, trial) combination and writes per-trial parquet rows.
"""
from __future__ import annotations

import asyncio
import time
from pathlib import Path

import pandas as pd

from .data import omni_math as _omni_math   # default dataset
from .models import MODELS
from .probes.base import Condition
from .trace import fmt_duration


# Per-model floor on which level-tier to bother sweeping. Models that
# saturate the lower end of the difficulty axis don't yield closure-bias
# signal there (verify_rate is meaningless when accuracy = 100%).
MIN_LEVEL_FOR_MODEL: dict[str, int] = {
    # Opus tier saturates L1-L2 on Omni-MATH; start at L3.
    "opus-4.5": 3,
    "opus-4.6": 3,
    "opus-4.7": 3,
    "opus-4.8": 3,
    # Sonnet 4.5/4.6 likely also saturate L1-L2; bump if substrate confirms.
    "sonnet-4.5": 3,
    "sonnet-4.6": 3,
    # Sonnet 4 / haiku tiers: keep all 5 levels (gradient is interesting).
}


async def gather_with_progress(
    coros: list,
    *,
    limit: int = 32,
    label: str = "run",
    log_each: bool = False,
    log_fields: tuple[str, ...] = (),
) -> list:
    """Bounded concurrency. Reports progress, ETA, running cost, errors."""
    sem = asyncio.Semaphore(limit)
    total = len(coros)
    done = 0
    cost_sum = 0.0
    err_count = 0
    t0 = time.monotonic()
    results: list = [None] * total

    async def _wrapped(idx, c):
        nonlocal done, cost_sum, err_count
        async with sem:
            err_text = None
            try:
                r = await c
            except Exception as e:
                err_text = f"{type(e).__name__}: {e}"
                r = {"error": err_text, "cost_usd": 0.0}
                err_count += 1
            results[idx] = r
            done += 1
            cost_sum += float(r.get("cost_usd") or 0.0)
            elapsed = time.monotonic() - t0
            rate = done / elapsed if elapsed > 0 else 0.0
            eta = (total - done) / rate if rate > 0 else float("inf")
            line = (
                f"  [{label}] {done:>4}/{total}  "
                f"elapsed {fmt_duration(elapsed):>10s}  "
                f"eta {fmt_duration(eta):>10s}  "
                f"${cost_sum:>5.2f}  "
                f"err={err_count}"
            )
            if err_text:
                line += f"   ERR: {err_text[:160]}"
            elif log_each and log_fields:
                extras = "  ".join(
                    f"{f}={r.get(f)!r}" if not isinstance(r.get(f), float)
                    else f"{f}={r.get(f):.3f}"
                    for f in log_fields if f in r
                )
                line += "   " + extras
            print(line, flush=True)

    await asyncio.gather(*[_wrapped(i, c) for i, c in enumerate(coros)])
    return results


def levels_for_model(model_label: str, levels: list[str]) -> list[str]:
    floor = MIN_LEVEL_FOR_MODEL.get(model_label, 1)
    return [lvl for i, lvl in enumerate(levels, start=1) if i >= floor]


# ---------- substrate ----------


async def run_substrate(
    probe,
    *,
    model_label: str,
    pool: dict[str, list[dict]] | None = None,
    levels: list[str] | None = None,
    n_per_level: int = 7,
    seed: int = 0,
    concurrency: int = 32,
    results_dir: Path | str = "results",
    save_traces: bool = True,
    dataset: str = "omni-math",
) -> pd.DataFrame:
    """Run the no-tools substrate sanity check. Persists to
    `<results_dir>/substrate/<dataset>__<model>.parquet`. Traces (if enabled)
    go under `<results_dir>/traces/<probe>/<dataset>/`.
    """
    if pool is None:
        pool, _ = _omni_math.build_pool(seed=seed, n_per_level=n_per_level)
    if levels is None:
        levels = list(pool.keys())
    all_problems = [ex for lvl in levels for ex in pool[lvl]]

    results_dir = Path(results_dir)
    out_path = results_dir / "substrate" / f"{dataset}__{model_label}.parquet"
    trace_root = results_dir / "traces" / probe.name / dataset if save_traces else None
    if trace_root is not None:
        trace_root.mkdir(parents=True, exist_ok=True)

    model_id = MODELS[model_label]
    coros = [
        probe.substrate_solve(ex, model_id, save_trace_root=trace_root)
        for ex in all_problems
    ]
    print(f"substrate[{probe.name}/{dataset}/{model_label}] launching "
          f"{len(coros)} problems (conc={concurrency})")
    print(f"  saving to {out_path}")

    rows = await gather_with_progress(
        coros,
        limit=concurrency,
        label=f"substrate-{dataset}-{model_label}",
        log_each=False,
        log_fields=("level", "correct", "num_turns"),
    )
    df = pd.DataFrame(rows)
    df["model_label"] = model_label
    df["dataset"] = dataset
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_path)

    err_n = df["error"].notna().sum() if "error" in df.columns else 0
    print(f"\nsubstrate done: {len(df)} rows  errors={err_n}  "
          f"cost=${df.get('cost_usd', pd.Series([0])).sum():.2f}")
    return df


# ---------- sweep ----------


async def run_sweep(
    probe,
    *,
    model_label: str,
    pool: dict[str, list[dict]] | None = None,
    n_per_level: int = 7,
    n_trials: int = 3,
    seed: int = 0,
    concurrency: int = 32,
    conditions: dict[str, Condition] | None = None,
    results_dir: Path | str = "results",
    save_traces: bool = True,
    dataset: str = "omni-math",
) -> pd.DataFrame:
    """Run the full probe sweep across (level, condition, trial) for one model."""
    if pool is None:
        pool, _ = _omni_math.build_pool(seed=seed, n_per_level=n_per_level)
    if conditions is None:
        conditions = probe.conditions
    levels = list(pool.keys())
    active_levels = levels_for_model(model_label, levels)
    skipped = [l for l in levels if l not in active_levels]

    results_dir = Path(results_dir)
    out_path = results_dir / "sweep" / f"{probe.name}__{dataset}__{model_label}.parquet"
    trace_root = results_dir / "traces" / probe.name / dataset if save_traces else None
    if trace_root is not None:
        trace_root.mkdir(parents=True, exist_ok=True)

    model_id = MODELS[model_label]
    coros = [
        probe.run_trial(ex, cond, model_id, save_trace_root=trace_root)
        for lvl in active_levels
        for ex in pool[lvl]
        for cond in conditions.values()
        for _ in range(n_trials)
    ]
    print(f"sweep[{probe.name}/{dataset}/{model_label}] launching "
          f"{len(coros)} trials (conc={concurrency})")
    if skipped:
        print(f"  skipping levels {skipped} for this model "
              f"(MIN_LEVEL_FOR_MODEL[{model_label!r}]={MIN_LEVEL_FOR_MODEL.get(model_label, 1)})")
    print(f"  saving to {out_path}")

    rows = await gather_with_progress(
        coros,
        limit=concurrency,
        label=f"sweep-{dataset}-{model_label}",
        log_each=False,
        log_fields=("level", "condition", "verify_calls", "final_correct",
                    "num_turns", "stop_reason"),
    )
    df = pd.DataFrame(rows)
    df["model_label"] = model_label
    df["dataset"] = dataset
    df["probe"] = probe.name
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_path)

    err_n = df["error"].notna().sum() if "error" in df.columns else 0
    no_submit = df["final_answer"].isna().sum() if "final_answer" in df.columns else 0
    total_latency = df["latency_s"].sum() if "latency_s" in df.columns else 0
    print(f"\nsweep done: {len(df)} rows  errors={err_n}  no_submit={no_submit}  "
          f"cost=${df.get('cost_usd', pd.Series([0])).sum():.2f}  "
          f"sum-of-trial-time={fmt_duration(total_latency)}")
    return df
