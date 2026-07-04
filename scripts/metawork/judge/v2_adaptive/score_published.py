"""Score the PUBLISHED corpus with the v2 task-adaptive meta-work judge.

The v2 counterpart of judge/v1_fixed/judge_published.py. Runs the full adaptive
instrument over the published harvest — by default the balanced 1-per-(model,task)
grid — pinning one rubric per task (reused across all models, so cross-model
comparisons share an identical ruler).

CAVEAT: the published flat_text is far lossier for some models than others
(harvest kept ~8x more prose for DeepSeek than GPT-5.5), so cross-model plots
partly reflect harvest fidelity; within-model / within-task views are clean.

Usage:
    # cheap validation over a few cells
    python scripts/metawork/judge/v2_adaptive/score_published.py --limit 3

    # the full balanced grid (9 models x 20 tasks x 1 = 180 trajectories)
    python scripts/metawork/judge/v2_adaptive/score_published.py --tag grid
"""
from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from metawork.judges.v2_adaptive.rubric import DEFAULT_RUBRIC_MODEL_LABEL
from metawork.judges.v2_adaptive.score import DEFAULT_SCORE_MODEL_LABEL
from metawork.published.score_corpus import score_published_corpus


def parse_args():
    ap = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter, description=__doc__)
    ap.add_argument("--size", default="l", help="harvest size to read (default: l)")
    ap.add_argument("--tag", default="grid", help="output tag (default: grid)")
    ap.add_argument("--model", default=None,
                    help="convenience: set BOTH rubric + score model")
    ap.add_argument("--rubric-model", default=None)
    ap.add_argument("--score-model", default=None)
    ap.add_argument("--concurrency", type=int, default=4,
                    help="outer: trajectories scored at once (default: 4)")
    ap.add_argument("--dim-concurrency", type=int, default=8,
                    help="inner: dimension judges per trajectory (default: 8)")
    ap.add_argument("--all", action="store_true",
                    help="score EVERY trajectory, not just 1-per-cell")
    ap.add_argument("--limit", type=int, default=None,
                    help="score only the first N cells (cheap probe)")
    ap.add_argument("--results-dir", default="results")
    ap.add_argument("--force", action="store_true",
                    help="re-score even if the output parquet exists")
    return ap.parse_args()


async def main():
    args = parse_args()
    rubric_model = args.rubric_model or args.model or DEFAULT_RUBRIC_MODEL_LABEL
    score_model = args.score_model or args.model or DEFAULT_SCORE_MODEL_LABEL

    suffix = f"_limit{args.limit}" if args.limit is not None else ""
    out_path = (Path(args.results_dir) / "metawork" / "judged" / "v2_adaptive"
                / f"scored_published_{args.tag}__{score_model}{suffix}.parquet")
    if out_path.exists() and not args.force:
        print(f"skipping: {out_path} already exists (use --force to re-score)")
        return

    await score_published_corpus(
        size=args.size, tag=args.tag,
        rubric_model=rubric_model, score_model=score_model,
        concurrency=args.concurrency, dim_concurrency=args.dim_concurrency,
        results_dir=args.results_dir,
        one_per_cell=not args.all, limit=args.limit,
    )


if __name__ == "__main__":
    asyncio.run(main())
