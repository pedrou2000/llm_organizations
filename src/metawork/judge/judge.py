"""LLM-as-a-judge for meta-work quality of an agent trajectory.

Mirrors the math `closure.math_judge` pattern: pinned judge model, single-shot
(`max_turns=1`), no tools, prompt loaded from `prompt.md`, structured
output parsed defensively. The judge is BLIND — it receives only the
flattened trajectory text (no model identity, no score).

Output is the rubric block:
    decomposition / horizon / test_strategy / replanning / build_maps  (each 0-2)
    overall_meta_work (1-10)
    pattern (categorical)
    justification (one sentence)
"""
from __future__ import annotations

import re
from pathlib import Path

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    TextBlock,
    query,
)

from common.models import MODELS

DEFAULT_JUDGE_MODEL_LABEL = "haiku-4.5"

_PROMPT_PATH = Path(__file__).with_name("prompt.md")
JUDGE_SYSTEM_PROMPT = _PROMPT_PATH.read_text()

# Giant trajectories (the corpus tail reaches ~770K chars ≈ 190K tokens).
# Macro meta-work lives in the planning prose and the action-type ARC, not in
# every Bash line, so for over-budget trajectories we keep head + tail (where
# decomposition and premature-close respectively show) rather than the middle.
MAX_FLAT_CHARS = 120_000   # ~30K tokens; head+tail split when exceeded


def _fit(flat_text: str, budget: int = MAX_FLAT_CHARS) -> str:
    if len(flat_text) <= budget:
        return flat_text
    head = budget * 2 // 3
    tail = budget - head
    return (flat_text[:head]
            + f"\n\n... [truncated {len(flat_text) - budget} chars] ...\n\n"
            + flat_text[-tail:])


_INT = r"([0-2])"
_FEATURE_RES = {
    "decomposition": re.compile(rf"decomposition:\s*{_INT}", re.I),
    "horizon":       re.compile(rf"horizon:\s*{_INT}", re.I),
    "test_strategy": re.compile(rf"test_strategy:\s*{_INT}", re.I),
    "replanning":    re.compile(rf"replanning:\s*{_INT}", re.I),
    "build_maps":    re.compile(rf"build_maps:\s*{_INT}", re.I),
}
_OVERALL_RE = re.compile(r"overall_meta_work:\s*(\d{1,2})", re.I)
_PATTERN_RE = re.compile(
    r"pattern:\s*(structured|one-shot-quit|thrash|micro-plan-spam|reactive-tdd|mixed)",
    re.I,
)
_JUSTIF_RE = re.compile(r"justification:\s*(.+)", re.I)


def _parse(text: str) -> dict:
    """Parse the rubric output block. Missing fields -> None."""
    out: dict = {}
    for k, rx in _FEATURE_RES.items():
        m = rx.search(text)
        out[k] = int(m.group(1)) if m else None
    m = _OVERALL_RE.search(text)
    out["overall_meta_work"] = int(m.group(1)) if m else None
    m = _PATTERN_RE.search(text)
    out["pattern"] = m.group(1).lower() if m else None
    m = _JUSTIF_RE.search(text)
    out["justification"] = m.group(1).strip()[:300] if m else None
    return out


def _judge_options(judge_model_label: str) -> ClaudeAgentOptions:
    return ClaudeAgentOptions(
        model=MODELS[judge_model_label],
        setting_sources=[],
        strict_mcp_config=True,
        mcp_servers={},
        allowed_tools=[],
        permission_mode="bypassPermissions",
        system_prompt=JUDGE_SYSTEM_PROMPT,
        max_turns=1,
    )


async def judge_trajectory(flat_text: str,
                           judge_model_label: str = DEFAULT_JUDGE_MODEL_LABEL) -> dict:
    """Judge meta-work quality of one (blind) flattened trajectory.

    Returns the parsed rubric dict plus `raw_judge_text`, `cost_usd`, and
    (on failure) `error`. Never raises — a failed call yields a row of Nones
    so the batch harness can record and move on.
    """
    if not isinstance(flat_text, str) or not flat_text.strip():
        return {"error": "empty_trajectory", "cost_usd": 0.0,
                **{k: None for k in _FEATURE_RES},
                "overall_meta_work": None, "pattern": None,
                "justification": None, "raw_judge_text": ""}

    prompt = f"TRAJECTORY TO JUDGE:\n\n{_fit(flat_text)}"
    final_text, cost = "", 0.0
    try:
        async for msg in query(prompt=prompt, options=_judge_options(judge_model_label)):
            if isinstance(msg, AssistantMessage):
                for blk in msg.content:
                    if isinstance(blk, TextBlock):
                        final_text += blk.text
            else:
                tc = getattr(msg, "total_cost_usd", None)
                if tc is not None:
                    cost = tc
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}", "cost_usd": 0.0,
                **{k: None for k in _FEATURE_RES},
                "overall_meta_work": None, "pattern": None,
                "justification": None, "raw_judge_text": ""}

    parsed = _parse(final_text)
    parsed["raw_judge_text"] = final_text.strip()[:1500]
    parsed["cost_usd"] = cost
    parsed["error"] = None if parsed["overall_meta_work"] is not None else "parse_failed"
    return parsed
