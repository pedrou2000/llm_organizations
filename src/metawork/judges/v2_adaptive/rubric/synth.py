"""Stage A: synthesize a task-adaptive meta-work rubric.

Given ONLY a task specification (what the agent saw at t=0 — blind to the
reference solution, tests, or any trajectory), an expert LLM produces a
task-specific rubric: the five fixed spine dimensions (+ up to a few task-unique
extras), each with an `importance` (1-10, normalized to weights afterward), a
`target_level` (the calibration anchor), and a fixed non-saturable 0-10 anchor
scale. See prompt.md for the full instrument spec.

Single-shot, no tools; emits standardized JSON (brace-matched out of the reply)
and retries on a truncated/malformed reply. Never raises — a persistent failure
yields `{"rubric": None, "error": ...}`.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    TextBlock,
    query,
)

from common.models import MODELS

from .validate import extract_json, validate_rubric

# Wall-clock ceiling on one rubric-synth call. Like the Stage-B judge, the SDK
# query can hang indefinitely; without this a single stuck synth stalls the
# whole batch's Stage A (rubrics are synthesized in a loop). A synth is a single
# reasoning-heavy shot — ~1 min healthy — so 5 min is a generous stuck threshold.
SYNTH_TIMEOUT_S = 300

# The rubric synthesizer is reasoning-heavy (design a measuring instrument), so
# default to a strong model. Overridable per call.
DEFAULT_RUBRIC_MODEL_LABEL = "opus-4.8"

_PROMPT_PATH = Path(__file__).with_name("prompt.md")
RUBRIC_SYSTEM_PROMPT = _PROMPT_PATH.read_text()

# How much of the raw reply we keep in the result (for debugging a malformed
# rubric); the full reply is only used for parsing, then discarded.
_RAW_TEXT_KEEP = 4000


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
    """One rubric-synth LLM call. Returns (reply_text, cost_usd). Raises on API
    error or if the call stalls past SYNTH_TIMEOUT_S (the caller retries)."""
    async def _consume() -> tuple[str, float]:
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

    return await asyncio.wait_for(_consume(), timeout=SYNTH_TIMEOUT_S)


async def synthesize_rubric(
    task_spec: str,
    model_label: str = DEFAULT_RUBRIC_MODEL_LABEL,
    max_attempts: int = 3,
) -> dict:
    """Synthesize a meta-work rubric from a task specification (Stage A).

    Retries up to `max_attempts` on an API error or a JSON parse failure. A
    rubric that parses but has schema problems is returned as-is (not retried)
    so the caller can inspect them. Never raises.

    Returns: {rubric, validation, raw_text, cost_usd, error, attempts}.
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
        rubric = extract_json(final_text)
        if rubric is None:
            last_error = "json_parse_failed"
            continue  # malformed/truncated — retry
        # A valid-JSON reply that stops before the dimensions array (the model
        # trailing off after a long task_read) is a truncation, not a real
        # rubric — retry rather than return an empty instrument.
        dims = rubric.get("dimensions")
        if not isinstance(dims, list) or not dims:
            last_error = "no_dimensions"
            continue
        problems = validate_rubric(rubric)
        return {
            "rubric": rubric,
            "validation": problems,
            "raw_text": final_text.strip()[:_RAW_TEXT_KEEP],
            "cost_usd": total_cost,
            "error": None if not problems else f"schema_problems: {len(problems)}",
            "attempts": attempt,
        }

    return {"rubric": None, "validation": [last_error],
            "raw_text": last_raw.strip()[:_RAW_TEXT_KEEP],
            "cost_usd": total_cost, "error": last_error, "attempts": max_attempts}
