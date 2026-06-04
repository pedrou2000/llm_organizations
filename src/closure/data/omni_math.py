"""Omni-MATH (KbsdJames/Omni-MATH) loader and rule-checkable filter.

Returns a `pool: dict[Level -> list[ex]]` matching the shape the rest of the
codebase expects. `ex` is a normalized dict with: problem, solution, answer,
level, difficulty, type, source.
"""
from __future__ import annotations

import random
from collections import Counter
from typing import Iterable

from datasets import load_dataset
from math_verify import parse, verify

NAME = "omni-math"

LEVELS: list[str] = [f"Level {i}" for i in range(1, 6)]


def to_level(d: float) -> str:
    """Map raw difficulty (float 1.0–9.5) into Level 1..5 buckets."""
    if d < 3.0:
        return "Level 1"
    if d < 4.5:
        return "Level 2"
    if d < 6.0:
        return "Level 3"
    if d < 7.5:
        return "Level 4"
    return "Level 5"


# Heuristic filter for rule-checkable answers. Two cheap signals:
#  (1) text patterns we know require a judge (English glue, function defs).
#  (2) parse(\boxed{answer}) succeeds and self-verifies.
#
# Why \boxed{...}: math_verify.parse has two modes — bare-expression and
# boxed-extraction — and they produce different results on multi-element
# answers. We force boxed-extraction so the parse path matches what the
# model emits as candidate.
_JUDGE_PATTERNS: tuple[str, ...] = (
    r"\text{",     # most "Yes"/"No"/descriptive answers
    "f(x", "f(n", "f(m", "g(x", "g(n",
    "for some", "for all", "for every", "for any",
    "where", "such that",
)


def is_rule_checkable(answer: str) -> bool:
    if not isinstance(answer, str) or not answer.strip():
        return False
    if any(p in answer for p in _JUDGE_PATTERNS):
        return False
    try:
        parsed = parse(f"\\boxed{{{answer}}}")
    except Exception:
        return False
    if not parsed:
        return False
    try:
        return bool(verify(parsed, parsed))
    except Exception:
        return False


def normalize_row(row: dict) -> dict:
    """Adapt an Omni-MATH row to the shape probes expect."""
    domain = row.get("domain") or []
    if isinstance(domain, list):
        type_ = domain[0] if domain else "unknown"
    else:
        type_ = str(domain)
    return {
        "problem":    row["problem"],
        "solution":   row.get("solution", ""),
        "answer":     row["answer"],
        "level":      to_level(float(row["difficulty"])),
        "difficulty": float(row["difficulty"]),
        "type":       type_,
        "source":     row.get("source", ""),
    }


def build_pool(
    *,
    seed: int = 0,
    n_per_level: int = 7,
    levels: Iterable[str] = LEVELS,
    verbose: bool = False,
) -> tuple[dict[str, list[dict]], list[dict]]:
    """Load Omni-MATH, filter to rule-checkable rows, sample N per level.

    Returns (POOL, ALL_PROBLEMS) where POOL maps level -> list[ex] and
    ALL_PROBLEMS is the flat concatenation in level order.
    """
    rng = random.Random(seed)
    data = load_dataset("KbsdJames/Omni-MATH", split="test")
    if verbose:
        print(f"loaded {len(data)} raw problems")

    filtered = [normalize_row(r) for r in data if is_rule_checkable(r["answer"])]
    if verbose:
        pct = 100 * len(filtered) / max(1, len(data))
        print(f"  kept {len(filtered)} / {len(data)} ({pct:.1f}%)")

    if verbose:
        counts = Counter(r["level"] for r in filtered)
        for lvl in levels:
            print(f"  {lvl}: {counts[lvl]} candidates")

    pool: dict[str, list[dict]] = {}
    for lvl in levels:
        candidates = [r for r in filtered if r["level"] == lvl]
        pool[lvl] = rng.sample(candidates, min(n_per_level, len(candidates)))
        if verbose:
            print(f"{lvl}: sampled {len(pool[lvl])}")

    all_problems = [ex for lvl in levels for ex in pool[lvl]]
    if verbose:
        print(f"\ntotal pool: {len(all_problems)} problems")
    return pool, all_problems
