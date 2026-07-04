"""Pure helpers for rubric handling: constants, JSON extraction, schema
validation, and importance->weight normalization. No LLM / IO.
"""
from __future__ import annotations

import json
import re

# The fixed 0-10 anchor levels every dimension defines (the non-saturable scale;
# see prompt.md). Consumers (scorer, printers) key off these.
ANCHOR_LEVELS = ("0", "3", "5", "8", "10")

# The five universal spine dimensions, always present, in this order. Derived
# from the definition of meta-work (understand -> decide what/when -> verify ->
# notice divergence -> adapt), so they are comparable across any task.
SPINE_IDS = (
    "orientation_research",
    "decomposition_milestones",
    "verification_strategy",
    "progress_monitoring",
    "adaptation_correction",
)
MAX_EXTRA_DIMENSIONS = 5

# Opening fence of a ```json block; from there we brace-match to find the object
# (a non-greedy regex mis-bounds on nested braces / trailing prose).
_FENCE_RE = re.compile(r"```(?:json)?\s*", re.IGNORECASE)


# ---------- JSON extraction ----------


def _balanced_object(text: str, start: int) -> str | None:
    """Return the JSON object beginning at the first '{' at/after `start`,
    matching braces (string-aware) to its close. None if unbalanced."""
    i = text.find("{", start)
    if i < 0:
        return None
    depth, in_str, esc = 0, False, False
    for j in range(i, len(text)):
        c = text[j]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
        elif c == '"':
            in_str = True
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return text[i : j + 1]
    return None


def extract_json(text: str) -> dict | None:
    """Pull the rubric JSON out of the model's reply.

    Tries the object right after a ```json fence first, then a bare
    brace-matched object anywhere. Brace-matching (not a regex) so nested
    objects and any trailing prose don't mis-bound the capture. Returns None if
    nothing parses (e.g. the reply was truncated mid-object).
    """
    m = _FENCE_RE.search(text)
    starts = ([m.end()] if m else []) + [0]
    for s in starts:
        obj = _balanced_object(text, s)
        if obj:
            try:
                return json.loads(obj)
            except json.JSONDecodeError:
                continue
    return None


# ---------- schema validation ----------


def validate_rubric(rubric: dict) -> list[str]:
    """Return a list of schema problems (empty = well-formed).

    Checks shape only — not judgment quality. Used to flag malformed synth
    output before it feeds Stage B.
    """
    problems: list[str] = []
    if not isinstance(rubric, dict):
        return ["rubric is not a dict"]
    if not isinstance(rubric.get("task_read"), str) or not rubric["task_read"].strip():
        problems.append("missing/empty task_read")
    dims = rubric.get("dimensions")
    if not isinstance(dims, list) or not dims:
        problems.append("missing/empty dimensions")
        return problems

    # Spine coverage: all five spine ids must be present exactly once.
    spine_ids_seen = [
        d.get("id") for d in dims
        if isinstance(d, dict) and d.get("spine") is True
    ]
    for sid in SPINE_IDS:
        if spine_ids_seen.count(sid) != 1:
            problems.append(
                f"spine id {sid!r} appears {spine_ids_seen.count(sid)}x (want 1)")
    n_extra = sum(1 for d in dims
                  if isinstance(d, dict) and d.get("spine") is False)
    if n_extra > MAX_EXTRA_DIMENSIONS:
        problems.append(f"{n_extra} extra dimensions (max {MAX_EXTRA_DIMENSIONS})")

    for idx, d in enumerate(dims):
        tag = f"dim[{idx}]"
        if not isinstance(d, dict):
            problems.append(f"{tag} not a dict")
            continue
        if not d.get("name"):
            problems.append(f"{tag} missing name")
        tl = d.get("target_level")
        if not isinstance(tl, int) or not (0 <= tl <= 10):
            problems.append(f"{tag} target_level not int 0-10 ({tl!r})")
        # Importance is an independent 1-10 score per dimension; we normalize to
        # weights ourselves (no sum-to-1 constraint on the model).
        imp = d.get("importance")
        if not isinstance(imp, (int, float)) or not (1 <= imp <= 10):
            problems.append(f"{tag} importance not in 1-10 ({imp!r})")
        anchors = d.get("anchors")
        if not isinstance(anchors, dict):
            problems.append(f"{tag} missing anchors")
        else:
            missing = [lv for lv in ANCHOR_LEVELS if lv not in anchors]
            if missing:
                problems.append(f"{tag} missing anchor levels {missing}")
    return problems


# ---------- importance -> weights ----------


def normalized_weights(rubric: dict) -> list[float]:
    """Convert each dimension's independent `importance` (1-10) into weights
    that sum to 1.0: weight_i = importance_i / sum(importance). Dimensions with
    a missing/invalid importance are treated as 0. Returns [] if none valid.
    """
    dims = rubric.get("dimensions") or []
    imps = [
        float(d["importance"])
        if isinstance(d, dict) and isinstance(d.get("importance"), (int, float))
        else 0.0
        for d in dims
    ]
    total = sum(imps)
    if total <= 0:
        return [0.0 for _ in imps]
    return [i / total for i in imps]
