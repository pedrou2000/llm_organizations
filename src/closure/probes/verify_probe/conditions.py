"""Conditions and prompts for the verify probe."""
from __future__ import annotations

from claude_agent_sdk import ClaudeAgentOptions

from ..base import Condition

PROMPT_BASE = (
    "You are a math problem solver. Solve the problem the user gives you, "
    "then call the `submit` tool with your final answer (e.g., '42', '3/7'). "
    "You must call `submit` exactly once, after which the trial ends."
)

PROMPT_NEUTRAL = PROMPT_BASE + " " + (
    "You also have a `verify` tool available. It performs a second-pass "
    "review of your candidate answer and returns whether your reasoning "
    "checks out. You may use it if you find it useful."
)

PROMPT_ANTI_BIAS = PROMPT_BASE + " " + (
    "You also have a `verify` tool available — a second-pass review of your "
    "candidate answer. ALWAYS call `verify` on your candidate answer before "
    "calling `submit`. If verify reports a discrepancy, revise your work and "
    "call verify again until it confirms; only then submit."
)

PROMPT_FORCED_BIAS = PROMPT_BASE + " " + (
    "You must solve directly and submit immediately. Do not second-guess. "
    "Trust your first-pass reasoning."
)


# Substrate sanity-check prompt and base options. The substrate path runs
# with no MCP tools at all to measure raw model accuracy by level.
SUBSTRATE_PROMPT = (
    "You are a math problem solver. Solve the problem step by step. "
    "Put your final answer inside \\boxed{...}."
)

DISALLOWED_BUILTINS = [
    "Bash", "Read", "Write", "Edit", "Glob", "Grep", "WebFetch", "WebSearch",
    "NotebookEdit", "Skill", "Task", "TaskCreate", "TaskGet", "TaskList",
    "TaskOutput", "TaskStop", "TaskUpdate", "AskUserQuestion",
    "ScheduleWakeup", "CronCreate", "CronDelete", "CronList",
    "EnterPlanMode", "ExitPlanMode", "EnterWorktree", "ExitWorktree",
    "ToolSearch",
]

SUBSTRATE_OPTIONS_BASE: dict = dict(
    setting_sources=[],
    strict_mcp_config=True,
    mcp_servers={},
    allowed_tools=[],
    disallowed_tools=DISALLOWED_BUILTINS,
    permission_mode="bypassPermissions",
    system_prompt=SUBSTRATE_PROMPT,
    max_turns=2,
)


CONDITIONS: dict[str, Condition] = {
    "forced":  Condition(
        code="forced",
        system_prompt=PROMPT_FORCED_BIAS,
        allowed_tools=["mcp__probe__submit"],
    ),
    "neutral": Condition(
        code="neutral",
        system_prompt=PROMPT_NEUTRAL,
        allowed_tools=["mcp__probe__verify", "mcp__probe__submit"],
    ),
    "anti":    Condition(
        code="anti",
        system_prompt=PROMPT_ANTI_BIAS,
        allowed_tools=["mcp__probe__verify", "mcp__probe__submit"],
    ),
}


def options_for(condition: Condition, model_id: str, mcp_server) -> ClaudeAgentOptions:
    """Build per-trial ClaudeAgentOptions wiring this condition's prompt + tools.

    `mcp_server` is the verify-probe MCP server (verify_tool + submit_tool).
    """
    return ClaudeAgentOptions(
        model=model_id,
        setting_sources=[],
        strict_mcp_config=True,
        mcp_servers={"probe": mcp_server},
        allowed_tools=condition.allowed_tools,
        disallowed_tools=DISALLOWED_BUILTINS,
        permission_mode="bypassPermissions",
        system_prompt=condition.system_prompt,
        max_turns=10,
    )
