"""Stage B: the agentic per-dimension meta-work judge.

One judge per rubric dimension. Each is given its dimension's anchors, the task
spec, the sibling dimension names (stay-in-lane), and read-only tools
(Read/Grep/Glob) over a single blind trajectory file. It explores the raw
trajectory freely — no budget pressure beyond a high runaway cap — then emits a
verdict: the observed level (0-10) with cited, step-referenced evidence.

Never raises — a failed/malformed judge yields a Verdict with observed_level
None and an `error`, so the aggregate can record it and move on.
"""
from __future__ import annotations

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    TextBlock,
    query,
)

from common.models import MODELS

from ..aggregate.types import Dimension
from ..rubric.validate import extract_json
from .render import render_prompt

DEFAULT_SCORE_MODEL_LABEL = "opus-4.8"

# A pure runaway backstop — exploration is otherwise unbounded (thoroughness
# over speed). A judge that needs anywhere near this many turns is misbehaving.
MAX_JUDGE_TURNS = 1000

# Read-only exploration surface: the judge inspects the trajectory file, never
# mutates anything. (No Bash — Read/Grep/Glob is enough to skim + search + read.)
_JUDGE_TOOLS = ["Read", "Grep", "Glob"]


def _judge_options(system_prompt: str, cwd: str, model_label: str) -> ClaudeAgentOptions:
    return ClaudeAgentOptions(
        model=MODELS[model_label],
        cwd=cwd,
        setting_sources=[],
        strict_mcp_config=True,
        mcp_servers={},
        allowed_tools=_JUDGE_TOOLS,
        permission_mode="bypassPermissions",
        system_prompt=system_prompt,
        max_turns=MAX_JUDGE_TURNS,
    )


async def _run(system_prompt: str, cwd: str, model_label: str) -> tuple[str, float, int]:
    """Run the agentic judge to completion. Returns (final_text, cost, turns)."""
    final_text, cost, turns = "", 0.0, 0
    kickoff = ("Explore the trajectory file and grade your dimension. "
               "When done, output only your verdict JSON.")
    async for msg in query(prompt=kickoff,
                           options=_judge_options(system_prompt, cwd, model_label)):
        if isinstance(msg, AssistantMessage):
            turns += 1
            for blk in msg.content:
                if isinstance(blk, TextBlock):
                    final_text += blk.text
        else:
            tc = getattr(msg, "total_cost_usd", None)
            if tc is not None:
                cost = tc
    return final_text, cost, turns


async def score_dimension(
    dim: Dimension,
    all_dims: list[Dimension],
    task_spec: str,
    trajectory_file: str,
    model_label: str = DEFAULT_SCORE_MODEL_LABEL,
    max_attempts: int = 2,
    return_prompt: bool = False,
) -> dict:
    """Score one dimension of a trajectory (Stage B).

    `trajectory_file` is the staged, blind trajectory path; the judge's cwd is
    its parent so Read/Grep/Glob see only that file. Retries on API error or
    malformed verdict. Returns a dict (verdict fields + `cost_usd`, `turns_used`,
    `error`, and `_prompt` when `return_prompt`) — a dict so the batch harness's
    cost/logging (which does `.get`) works; the conductor wraps it in a Verdict.
    Never raises.
    """
    from pathlib import Path
    traj = Path(trajectory_file)
    system_prompt = render_prompt(dim, all_dims, task_spec, traj.name)
    cwd = str(traj.parent)

    total_cost, last_err, last_turns = 0.0, "no_attempt", None
    for _ in range(max_attempts):
        try:
            text, cost, turns = await _run(system_prompt, cwd, model_label)
            total_cost += cost
            last_turns = turns
        except Exception as e:
            last_err = f"{type(e).__name__}: {e}"
            continue
        parsed = extract_json(text)
        if parsed is None:
            last_err = "verdict_parse_failed"
            continue
        parsed.setdefault("dimension_id", dim.id)
        parsed["cost_usd"] = total_cost
        parsed["turns_used"] = last_turns
        parsed["error"] = None
        if return_prompt:
            parsed["_prompt"] = system_prompt
        return parsed

    failed = {"dimension_id": dim.id, "observed_level": None, "confidence": None,
              "evidence": [], "reasoning": "", "cost_usd": total_cost,
              "turns_used": last_turns, "error": last_err}
    if return_prompt:
        failed["_prompt"] = system_prompt
    return failed
