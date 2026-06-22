"""Run the meta-work quality judge over a harvested trajectory corpus.

Judges each (blind) trajectory with the pinned judge model, then joins the
outcome metadata back for analysis. Run harvest_metawork.py first.

Sizes mirror the harvest:  s=20, m=100, l=full(~1300).

Cost ladder: start with --size s (cheap), read the result, then scale.

Usage:
    python scripts/metawork/published/judge.py --size s
    python scripts/metawork/published/judge.py --size m --concurrency 16
    python scripts/metawork/published/judge.py --size l   # full corpus
"""
from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from metawork.judge import DEFAULT_JUDGE_MODEL_LABEL
from metawork.run import judge_corpus


def parse_args():
    ap = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=__doc__,
    )
    ap.add_argument("--size", default="s",
                    help="which harvest_<size>.parquet to judge (s/m/l). Default: s.")
    ap.add_argument("--judge-model", default=DEFAULT_JUDGE_MODEL_LABEL,
                    help="short label of the model that does the judging "
                         "(e.g. 'sonnet-4.6', 'haiku-4.5'). See closure.models.MODELS. "
                         f"Default: {DEFAULT_JUDGE_MODEL_LABEL}.")
    ap.add_argument("--concurrency", type=int, default=16,
                    help="max in-flight judge calls (default: 16)")
    ap.add_argument("--limit", type=int, default=None,
                    help="judge only the first N trajectories (cheap probe)")
    ap.add_argument("--results-dir", default="results")
    ap.add_argument("--force", action="store_true",
                    help="re-judge even if the output parquet exists")
    return ap.parse_args()


async def main():
    args = parse_args()
    lim = f"_limit{args.limit}" if args.limit is not None else ""
    out_path = (Path(args.results_dir) / "metawork" / "judged"
                / f"judged_{args.size}__{args.judge_model}{lim}.parquet")
    if out_path.exists() and not args.force:
        print(f"skipping: {out_path} already exists (use --force to re-judge)")
        return
    await judge_corpus(
        size=args.size,
        judge_model_label=args.judge_model,
        concurrency=args.concurrency,
        results_dir=args.results_dir,
        limit=args.limit,
    )


if __name__ == "__main__":
    asyncio.run(main())
