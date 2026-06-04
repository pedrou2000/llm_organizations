"""Trial runners for the verify probe: substrate (no tools) and full sweep
(with verify+submit MCP tools). Both write per-trial markdown traces.
"""
from __future__ import annotations

import time
from collections import Counter
from pathlib import Path
from typing import Any

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    SystemMessage,
    TextBlock,
    ToolUseBlock,
    query,
)

from ...judge import JUDGE_MODEL_LABEL, judge_correct
from ...models import MODELS, label_for_id
from ...trace import next_trace_idx, slug, write_trace
from ..base import Condition
from .conditions import (
    CONDITIONS,
    SUBSTRATE_OPTIONS_BASE,
    SUBSTRATE_PROMPT,
    options_for,
)
from .tools import PROBE_SERVER, TrialContext, reset_trial_ctx, set_trial_ctx


# ---------- substrate (no tools) ----------


async def substrate_solve(
    ex: dict,
    model_id: str,
    *,
    save_trace_root: Path | None = None,
) -> dict:
    """Single-shot solve, no tools. Returns dict with answer/correct/cost.
    If `save_trace_root` is given, writes a markdown trace to
    `<save_trace_root>/substrate/<model>/...md`.
    """
    options = ClaudeAgentOptions(model=model_id, **SUBSTRATE_OPTIONS_BASE)
    final_text, cost, n_turns = "", 0.0, 0
    messages: list = []
    t0 = time.monotonic()
    async for msg in query(prompt=ex["problem"], options=options):
        messages.append(msg)
        if isinstance(msg, AssistantMessage):
            for blk in msg.content:
                if isinstance(blk, TextBlock):
                    final_text += blk.text
        elif isinstance(msg, ResultMessage):
            cost = msg.total_cost_usd or 0.0
            n_turns = msg.num_turns
    latency = time.monotonic() - t0

    correct = await judge_correct(ex["answer"], final_text)
    result = {
        "type":        ex["type"],
        "level":       ex["level"],
        "difficulty":  ex["difficulty"],
        "answer_text": final_text,
        "correct":     correct,
        "cost_usd":    cost,
        "num_turns":   n_turns,
        "latency_s":   latency,
    }

    if save_trace_root is not None:
        idx = await next_trace_idx()
        m_label = label_for_id(model_id) or slug(model_id, 16)
        fname = (
            f"{idx:05d}__{result['level'].replace(' ', '')}"
            f"__{slug(ex.get('source', ''), 16)}"
            f"__correct-{int(result['correct'])}.md"
        )
        path = Path(save_trace_root) / "substrate" / m_label / fname
        write_trace(
            path,
            header={
                "phase":          "substrate",
                "model":          m_label,
                "model_id":       model_id,
                "system_prompt":  SUBSTRATE_PROMPT,
                "judge":          JUDGE_MODEL_LABEL,
            },
            ex=ex, messages=messages, result=result,
        )
    return result


# ---------- sweep trial runner ----------


async def run_trial(
    ex: dict,
    condition: Condition,
    model_id: str,
    *,
    save_trace_root: Path | None = None,
    audit_first_init: bool = False,
) -> dict[str, Any]:
    """One (condition, problem, model) trial. Streams the message events,
    counts tool calls, runs final-correctness via the LLM judge.
    """
    ctx = TrialContext(ex=ex)
    token = set_trial_ctx(ctx)
    options = options_for(condition, model_id, mcp_server=PROBE_SERVER)

    tool_call_counts: Counter[str] = Counter()
    tool_trajectory: list[str] = []
    init_tools: list[str] = []
    cost, n_turns, stop_reason = 0.0, 0, None
    error_msg: str | None = None
    messages: list = []
    t0 = time.monotonic()

    try:
        async for msg in query(prompt=ex["problem"], options=options):
            messages.append(msg)
            if isinstance(msg, SystemMessage) and msg.subtype == "init":
                init_tools = list(msg.data.get("tools", []))
                if audit_first_init:
                    print("init tools:", init_tools)
                    print("init mcp:",   msg.data.get("mcp_servers"))
            elif isinstance(msg, AssistantMessage):
                for blk in msg.content:
                    if isinstance(blk, ToolUseBlock):
                        tool_call_counts[blk.name] += 1
                        tool_trajectory.append(blk.name)
            elif isinstance(msg, ResultMessage):
                cost = msg.total_cost_usd or 0.0
                n_turns = msg.num_turns
                stop_reason = msg.stop_reason
    except Exception as e:
        error_msg = f"{type(e).__name__}: {e}"
    finally:
        reset_trial_ctx(token)

    final_answer = ctx.submitted[-1] if ctx.submitted else None
    final_correct = (
        await judge_correct(ex["answer"], final_answer)
        if final_answer is not None else False
    )

    row = {
        "type":          ex["type"],
        "level":         ex["level"],
        "difficulty":    ex.get("difficulty"),
        "condition":     condition.code,
        "model":         model_id,
        "verify_calls":  tool_call_counts.get("mcp__probe__verify", 0),
        "submit_calls":  tool_call_counts.get("mcp__probe__submit", 0),
        "verify_called": tool_call_counts.get("mcp__probe__verify", 0) > 0,
        "final_answer":  final_answer,
        "final_correct": final_correct,
        "trajectory":    "|".join(tool_trajectory),
        "cost_usd":      cost,
        "latency_s":     time.monotonic() - t0,
        "num_turns":     n_turns,
        "stop_reason":   stop_reason,
        "error":         error_msg,
        "init_tools":    "|".join(init_tools),
    }

    if save_trace_root is not None:
        idx = await next_trace_idx()
        m_label = label_for_id(model_id) or slug(model_id, 16)
        fname = (
            f"{idx:05d}__{row['level'].replace(' ', '')}"
            f"__{condition.code}"
            f"__{slug(ex.get('source', ''), 16)}"
            f"__correct-{int(row['final_correct'])}"
            f"__verify-{int(row['verify_called'])}.md"
        )
        path = Path(save_trace_root) / "sweep" / m_label / condition.code / fname
        write_trace(
            path,
            header={
                "phase":          "sweep",
                "model":          m_label,
                "model_id":       model_id,
                "condition":      condition.code,
                "system_prompt":  condition.system_prompt,
                "allowed_tools":  condition.allowed_tools,
                "judge":          JUDGE_MODEL_LABEL,
            },
            ex=ex, messages=messages, result=row,
        )
    return row


# ---------- probe object ----------


class VerifyProbe:
    """Bundle of verify-probe pieces, satisfies ProbeProtocol."""

    name = "verify"
    conditions: dict[str, Condition] = CONDITIONS

    @property
    def mcp_server(self):
        return PROBE_SERVER

    async def run_trial(self, ex, condition, model_id, **kw):
        return await run_trial(ex, condition, model_id, **kw)

    async def substrate_solve(self, ex, model_id, **kw):
        return await substrate_solve(ex, model_id, **kw)
