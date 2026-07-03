"""Stage A of the task-adaptive meta-work judge: synthesize a rubric.

Given ONLY a task specification (what the agent saw at t=0 — blind to the
reference solution, tests, or any trajectory), an expert LLM produces a
task-specific rubric: the five fixed spine dimensions (+ up to a few task-unique
extras), each with an `importance` (1-10, normalized to weights afterward), a
`target_level` (the calibration anchor), and a fixed non-saturable 0-10 anchor
scale. See rubric_prompt.md for the full instrument spec.

Mirrors the `v1_fixed.judge` call pattern (pinned model, single-shot, no tools),
but emits standardized JSON (brace-matched out of the reply, not regex-scraped)
and retries on a truncated/malformed reply. Never raises — a persistent failure
yields `{"rubric": None, "error": ...}`.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    TextBlock,
    query,
)

from common.models import MODELS

# The rubric synthesizer is a reasoning-heavy job (design a measuring
# instrument), so default to a strong model. Overridable per call.
DEFAULT_RUBRIC_MODEL_LABEL = "opus-4.8"

_PROMPT_PATH = Path(__file__).with_name("rubric_prompt.md")
RUBRIC_SYSTEM_PROMPT = _PROMPT_PATH.read_text()

# The fixed 0-10 anchor levels every dimension defines (the non-saturable scale;
# see rubric_prompt.md). Public: consumers (scorer, printers) key off these.
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

# How much of the model's raw reply we keep in the result (for debugging a
# malformed rubric). The full reply is only used for parsing, then discarded.
_RAW_TEXT_KEEP = 4000

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


def _extract_json(text: str) -> dict | None:
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


# ---------- LLM synthesis ----------


def _rubric_options(model_label: str) -> ClaudeAgentOptions:
    return ClaudeAgentOptions(
        model=MODELS[model_label],
        setting_sources=[],
        strict_mcp_config=True,
        mcp_servers={},
        allowed_tools=[],
        permission_mode="bypassPermissions",
        system_prompt=RUBRIC_SYSTEM_PROMPT,
        max_turns=1,
    )


async def _one_call(prompt: str, model_label: str) -> tuple[str, float]:
    """One rubric-synth LLM call. Returns (reply_text, cost_usd). Raises on
    API error (the caller decides whether to retry)."""
    final_text, cost = "", 0.0
    async for msg in query(prompt=prompt, options=_rubric_options(model_label)):
        if isinstance(msg, AssistantMessage):
            for blk in msg.content:
                if isinstance(blk, TextBlock):
                    final_text += blk.text
        else:
            tc = getattr(msg, "total_cost_usd", None)
            if tc is not None:
                cost = tc
    return final_text, cost


async def synthesize_rubric(
    task_spec: str,
    model_label: str = DEFAULT_RUBRIC_MODEL_LABEL,
    max_attempts: int = 3,
) -> dict:
    """Synthesize a meta-work rubric from a task specification (Stage A).

    Retries up to `max_attempts` on an API error or a JSON parse failure
    (rubric synthesis is a long structured generation that occasionally comes
    back truncated/malformed). A rubric that parses but has schema problems is
    returned as-is (not retried) so the caller can inspect them. Never raises.

    Returns a dict with:
        rubric        parsed rubric dict, or None on failure
        validation    list of schema problems (empty if clean)
        raw_text      the model's reply (truncated for storage)
        cost_usd      total call cost across attempts
        error         None on success, else a short reason
        attempts      how many LLM calls were made
    """
    if not isinstance(task_spec, str) or not task_spec.strip():
        return {"rubric": None, "validation": ["empty_task_spec"], "raw_text": "",
                "cost_usd": 0.0, "error": "empty_task_spec", "attempts": 0}

    prompt = f"TASK SPECIFICATION:\n\n{task_spec}"
    total_cost = 0.0
    last_error = "no_attempt"
    last_raw = ""
    for attempt in range(1, max_attempts + 1):
        try:
            final_text, cost = await _one_call(prompt, model_label)
            total_cost += cost
        except Exception as e:
            last_error = f"{type(e).__name__}: {e}"
            continue  # transient API error — retry
        last_raw = final_text
        rubric = _extract_json(final_text)
        if rubric is None:
            last_error = "json_parse_failed"
            continue  # malformed/truncated — retry
        problems = validate_rubric(rubric)
        return {
            "rubric": rubric,
            "validation": problems,
            "raw_text": final_text.strip()[:_RAW_TEXT_KEEP],
            "cost_usd": total_cost,
            "error": None if not problems else f"schema_problems: {len(problems)}",
            "attempts": attempt,
        }

    return {"rubric": None, "validation": [last_error], "raw_text": last_raw.strip()[:_RAW_TEXT_KEEP],
            "cost_usd": total_cost, "error": last_error, "attempts": max_attempts}
