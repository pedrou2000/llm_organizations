"""Measure the variance of the v2 task-adaptive meta-work judge.

The judge has TWO stochastic stages that compound, so "judge variance" splits:

  sigma^2_scoring : pin ONE rubric, rescore a trajectory K times     (Stage B noise)
  sigma^2_rubric  : synthesize M rubrics, score under each           (the ruler moving)
  sigma^2_total   : what a user of judge_metawork actually sees       (both compounded)

We run a balanced NESTED design per trajectory (scorings nested within rubrics):
synthesize M rubrics from the task spec, then score the trajectory K times against
each pinned rubric -> M*K scorings/trajectory. Repeated over TRAJECTORIES that span
the observed-meta-work range (a "clean" high-metawork trial and a "messy" low one)
to check whether the noise level itself is stable across trajectory types.

Variance components (per fixed spine dimension AND for the headline scalars) via
the standard one-way random-effects decomposition on observed_level / target_level
/ gap:
  - within-rubric var  = mean over rubrics of Var_k(scoring)          -> sigma^2_scoring
  - between-rubric var  = Var_r(mean_k) - within/K  (unbiased)         -> sigma^2_rubric
  - total var          = Var over all M*K scorings                    -> sigma^2_total

Usage:
    # full run (M=10 rubrics x K=10 scorings x 2 trajectories = 200 scorings)
    python scripts/metawork/judge/v2_adaptive/measure_variance.py

    # cheap validation first
    python scripts/metawork/judge/v2_adaptive/measure_variance.py --rubrics 2 --scorings 2

    # recompute the decomposition from an existing raw parquet, no LLM calls
    python scripts/metawork/judge/v2_adaptive/measure_variance.py --analyze-only
"""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

import pandas as pd

from metawork.judges.v2_adaptive import judge_metawork, synthesize_rubric
from metawork.judges.v2_adaptive.aggregate.types import Rubric

_SPEC = Path("vendor/swe-marathon/tasks/excel-clone/instruction.md")
_OUT = Path("results/metawork/judged/v2_adaptive/variance")

# Two excel-clone trajectories spanning the observed-meta-work range (from the
# par4 stress run): a "clean" high-metawork trial and a "messy" low one. Same
# task => same rubric distribution, so rubric variance is cleanly isolated.
_TRAJECTORIES = {
    "clean__UGtpajG": "results/metawork/trajectories/harbor/par4_5f99aa9_r2/excel-clone__UGtpajG",
    "messy__BzF8Tsg": "results/metawork/trajectories/harbor/e2e_707e0f2_run1/excel-clone__BzF8Tsg",
}

# Headline scalars + the 5 fixed spine dims (comparable across every run).
_SCALARS = ["overall_gap", "overall_observed", "task_specific_gap"]
_SPINE = ["orientation_research", "decomposition_milestones", "verification_strategy",
          "progress_monitoring", "adaptation_correction"]


async def _synthesize_rubrics(m: int, model: str) -> list[dict]:
    """Synthesize M rubrics from the task spec (Stage A only, cheap). Rubric
    synthesis varies the label to break any prompt-identical caching."""
    spec = _SPEC.read_text()
    print(f"[A] synthesizing {m} rubrics from {_SPEC.name} ...")
    results = await asyncio.gather(*[synthesize_rubric(spec, model_label=model)
                                     for _ in range(m)])
    rubrics = [r["rubric"] for r in results if r.get("rubric")]
    print(f"    got {len(rubrics)}/{m} valid rubrics "
          f"(cost ${sum(r.get('cost_usd', 0) for r in results):.2f})")
    return rubrics


async def _score_grid(rubrics: list[dict], k: int, score_model: str,
                      outer_conc: int) -> pd.DataFrame:
    """Score every (trajectory, rubric, scoring-repeat) cell with the pinned
    rubric (Stage B only). Outer concurrency bounded to `outer_conc`."""
    spec = _SPEC.read_text()
    sem = asyncio.Semaphore(outer_conc)
    cells = [(tname, tpath, ri, si)
             for tname, tpath in _TRAJECTORIES.items()
             for ri in range(len(rubrics))
             for si in range(k)]
    print(f"[B] scoring {len(cells)} cells "
          f"({len(_TRAJECTORIES)} traj x {len(rubrics)} rubrics x {k} repeats), "
          f"outer_conc={outer_conc} ...")

    done = 0
    lock = asyncio.Lock()

    async def one(tname, tpath, ri, si):
        nonlocal done
        async with sem:
            score = await judge_metawork(
                tpath, spec,
                rubric=Rubric.from_dict(rubrics[ri]),
                score_model=score_model,
            )
        async with lock:
            done += 1
            print(f"    [{done}/{len(cells)}] {tname} r{ri} s{si}  "
                  f"gap={score.overall_gap:+.2f} obs={score.overall_observed:.2f} "
                  f"err={len(score.errors)}")
        return {"trajectory": tname, "rubric_idx": ri, "scoring_idx": si,
                **score.summary_row()}

    rows = await asyncio.gather(*[one(*c) for c in cells])
    return pd.DataFrame(rows)


def _decompose(df: pd.DataFrame, k: int) -> pd.DataFrame:
    """One-way random-effects variance decomposition per metric, per trajectory.

    For each metric, split total variance into within-rubric (scoring noise) and
    between-rubric (ruler) components. Between = Var(rubric means) - within/K,
    floored at 0 (the standard unbiased ANOVA estimator)."""
    metrics = _SCALARS + [f"{d}__observed" for d in _SPINE] \
                       + [f"{d}__target" for d in _SPINE] \
                       + [f"{d}__gap" for d in _SPINE]
    out = []
    for tname, tdf in df.groupby("trajectory"):
        for metric in metrics:
            if metric not in tdf or tdf[metric].isna().all():
                continue
            col = tdf[["rubric_idx", metric]].dropna()
            grand_sd = col[metric].std(ddof=1)
            per_rubric = col.groupby("rubric_idx")[metric]
            within = per_rubric.var(ddof=1).mean()            # sigma^2_scoring
            between_raw = per_rubric.mean().var(ddof=1)       # Var of rubric means
            between = max(0.0, between_raw - (within / k if k > 1 else 0))
            out.append({
                "trajectory": tname, "metric": metric,
                "mean": col[metric].mean(),
                "total_sd": grand_sd,
                "sd_scoring": within ** 0.5,
                "sd_rubric": between ** 0.5,
                "n": len(col),
            })
    return pd.DataFrame(out)


def _report(dec: pd.DataFrame, accept_sd: float) -> None:
    print(f"\n{'='*90}\nVARIANCE DECOMPOSITION  (acceptance: overall_gap total_sd < {accept_sd})\n{'='*90}")
    for tname, tdf in dec.groupby("trajectory"):
        print(f"\n--- {tname} ---")
        print(f"  {'metric':<34} {'mean':>7} {'sd_tot':>7} {'sd_score':>9} {'sd_rubric':>9}")
        for _, r in tdf.iterrows():
            print(f"  {r['metric']:<34} {r['mean']:>7.2f} {r['total_sd']:>7.3f} "
                  f"{r['sd_scoring']:>9.3f} {r['sd_rubric']:>9.3f}")
    hg = dec[dec["metric"] == "overall_gap"]
    print(f"\n{'='*90}")
    for _, r in hg.iterrows():
        verdict = "PASS" if r["total_sd"] < accept_sd else "FAIL"
        dom = "rubric" if r["sd_rubric"] > r["sd_scoring"] else "scoring"
        print(f"  overall_gap [{r['trajectory']}]: total_sd={r['total_sd']:.3f} "
              f"-> {verdict}   (dominant source: {dom})")


async def main() -> None:
    ap = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter, description=__doc__)
    ap.add_argument("--rubrics", type=int, default=10, help="M rubrics (default 10)")
    ap.add_argument("--scorings", type=int, default=10, help="K repeats/rubric (default 10)")
    ap.add_argument("--score-model", default="opus-4.8")
    ap.add_argument("--rubric-model", default="opus-4.8")
    ap.add_argument("--outer-concurrency", type=int, default=4)
    ap.add_argument("--analyze-only", action="store_true",
                    help="recompute decomposition from the saved raw parquet")
    args = ap.parse_args()

    _OUT.mkdir(parents=True, exist_ok=True)
    raw_path = _OUT / f"variance_raw__M{args.rubrics}_K{args.scorings}.parquet"

    if args.analyze_only:
        df = pd.read_parquet(raw_path)
        print(f"loaded {len(df)} scorings from {raw_path}")
    else:
        rubrics = await _synthesize_rubrics(args.rubrics, args.rubric_model)
        if not rubrics:
            raise SystemExit("no valid rubrics synthesized")
        (_OUT / f"rubrics__M{args.rubrics}.json").write_text(json.dumps(rubrics, indent=2))
        df = await _score_grid(rubrics, args.scorings, args.score_model,
                               args.outer_concurrency)
        df.to_parquet(raw_path)
        print(f"\nsaved {len(df)} scorings -> {raw_path}  "
              f"(cost ${df['cost_usd'].sum():.2f}, errors {int(df['n_errors'].sum())})")

    dec = _decompose(df, args.scorings)
    dec.to_parquet(_OUT / f"variance_decomposition__M{args.rubrics}_K{args.scorings}.parquet")
    _report(dec, accept_sd=0.5)


if __name__ == "__main__":
    asyncio.run(main())
