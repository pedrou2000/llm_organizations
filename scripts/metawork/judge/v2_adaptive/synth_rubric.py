"""Prototype runner for Stage A of the task-adaptive meta-work judge.

Reads a SWE-Marathon task's instruction.md (the spec the agent saw at t=0 —
blind to solution/tests) and runs the rubric synthesizer, printing the rubric
so we can eyeball two things:
  1. proportionality — does a small task get a LEAN rubric, a big one a RICH one?
  2. non-saturability — are the 8/10 anchors genuinely demanding, with headroom?

Usage:
    # a real task (reads vendor/swe-marathon/tasks/<task>/instruction.md)
    python scripts/metawork/judge/v2_adaptive/synth_rubric.py --task excel-clone
    python scripts/metawork/judge/v2_adaptive/synth_rubric.py --task parameter-golf

    # the synthetic trivial task (the proportionality acid-test — should be LEAN)
    python scripts/metawork/judge/v2_adaptive/synth_rubric.py --trivial

    # any file as the spec
    python scripts/metawork/judge/v2_adaptive/synth_rubric.py --spec-file /path/to/spec.md

    # dump the full JSON rubric too
    python scripts/metawork/judge/v2_adaptive/synth_rubric.py --task excel-clone --json
"""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from metawork.judges.v2_adaptive import synthesize_rubric
from metawork.judges.v2_adaptive.rubric import (
    ANCHOR_LEVELS,
    DEFAULT_RUBRIC_MODEL_LABEL,
    normalized_weights,
)

_TASKS_DIR = Path("vendor/swe-marathon/tasks")

# A deliberately trivial task — the SWE-Marathon corpus has no small tasks, so
# this is the only way to test the low end of proportionality: Stage A should
# produce a LEAN rubric (few dimensions, low target_levels) for this.
_TRIVIAL_SPEC = """\
Fix a typo in the project README.

The word "recieve" appears once in README.md and should be "receive".
Change that one word. Do not modify anything else.
"""


def _load_spec(args) -> tuple[str, str]:
    """Return (label, spec_text)."""
    if args.trivial:
        return "trivial-typo-fix", _TRIVIAL_SPEC
    if args.spec_file:
        p = Path(args.spec_file)
        return p.stem, p.read_text()
    p = _TASKS_DIR / args.task / "instruction.md"
    if not p.exists():
        raise SystemExit(f"no instruction.md at {p}")
    return args.task, p.read_text()


def _print_rubric(label: str, result: dict, show_json: bool) -> None:
    print(f"\n{'='*78}\nTASK: {label}   (model={result.get('_model')}, "
          f"cost=${result.get('cost_usd', 0):.3f})\n{'='*78}")
    if result.get("error"):
        print(f"  ERROR: {result['error']}")
    if result.get("validation"):
        print(f"  SCHEMA PROBLEMS: {result['validation']}")
    rubric = result.get("rubric")
    if not rubric:
        print("  (no rubric)\n  raw reply (truncated):")
        print("  " + (result.get("raw_text", "")[:800]).replace("\n", "\n  "))
        return

    print(f"\n  task_read: {rubric.get('task_read')}\n")
    dims = rubric.get("dimensions", [])
    weights = normalized_weights(rubric)
    print(f"  {len(dims)} dimension(s):")
    for d, w in zip(dims, weights):
        print(f"\n  • {d.get('name')}  "
              f"(importance={d.get('importance')}/10 -> weight={w:.2f}, "
              f"target_level={d.get('target_level')}/10)")
        print(f"      {d.get('description')}")
        print(f"      why: {d.get('why_it_matters')}")
        anchors = d.get("anchors", {})
        for lv in ANCHOR_LEVELS:
            if lv in anchors:
                print(f"      [{lv:>2}] {anchors[lv]}")
    if show_json:
        print("\n  --- full JSON ---")
        print(json.dumps(rubric, indent=2))


async def main() -> None:
    ap = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter, description=__doc__
    )
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--task", help="task name under vendor/swe-marathon/tasks/")
    g.add_argument("--trivial", action="store_true",
                   help="run the synthetic trivial task (proportionality acid-test)")
    g.add_argument("--spec-file", help="path to an arbitrary spec file")
    ap.add_argument("--model", default=DEFAULT_RUBRIC_MODEL_LABEL,
                    help=f"rubric synthesizer model (default {DEFAULT_RUBRIC_MODEL_LABEL})")
    ap.add_argument("--json", action="store_true", help="also dump full JSON")
    ap.add_argument("--out-dir", default="results/metawork/judged/v2_adaptive/rubrics",
                    help="where to save the rubric JSON (default: results/metawork/judged/v2_adaptive/rubrics)")
    ap.add_argument("--no-save", action="store_true", help="don't persist the rubric")
    args = ap.parse_args()

    label, spec = _load_spec(args)
    print(f"synthesizing rubric for '{label}' ({len(spec)} chars of spec) "
          f"with {args.model} ...")
    result = await synthesize_rubric(spec, model_label=args.model)
    result["_model"] = args.model
    _print_rubric(label, result, args.json)

    if not args.no_save and result.get("rubric"):
        out_dir = Path(args.out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"rubric__{label}__{args.model}.json"
        out_path.write_text(json.dumps({
            "task": label,
            "model": args.model,
            "cost_usd": result.get("cost_usd"),
            "validation": result.get("validation"),
            "rubric": result["rubric"],
        }, indent=2))
        print(f"\n  saved -> {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
