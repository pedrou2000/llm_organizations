"""Per-trial markdown trace logging.

Renders a self-contained markdown trace per trial: header (model, prompt, etc.),
problem text, gold answer, the full message stream (model text, thinking,
tool calls, tool results), and the result row.

Failures are non-fatal — bad write never breaks a trial.
"""
from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from typing import Any


# ---------- formatting helpers ----------


def slug(s: str | None, n: int = 32) -> str:
    """Filesystem-safe short slug."""
    s = (s or "").strip()
    s = re.sub(r"[^A-Za-z0-9._-]+", "_", s)
    return s[:n].strip("_") or "x"


def fmt_duration(s: float | int | None) -> str:
    """Human-friendly duration. e.g. 65 -> '1m 5s', 3725 -> '1h 2m 5s'."""
    try:
        s = float(s)
    except (TypeError, ValueError):
        return "?"
    if s != s or s == float("inf") or s == float("-inf"):
        return "∞"
    if s < 0:
        return "-" + fmt_duration(-s)
    s = int(round(s))
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    if h:
        return f"{h}h {m}m {sec}s"
    if m:
        return f"{m}m {sec}s"
    return f"{sec}s"


# Init-message keys we keep when serializing a SystemMessage(init).
# Everything else (slash_commands, agents, skills, plugins, paths, ...) is
# noise for our purposes and just pads every trace by ~50 lines.
_INIT_KEYS_OF_INTEREST = (
    "type", "subtype", "model", "permissionMode",
    "tools", "mcp_servers", "session_id",
)


def _format_block(blk: Any) -> str:
    """Render one assistant/user content block as markdown.

    Duck-typed: the SDK has several block subtypes (TextBlock, ThinkingBlock,
    ToolUseBlock, ToolResultBlock) we don't all import explicitly.
    """
    cls      = type(blk).__name__
    text     = getattr(blk, "text", None)
    thinking = getattr(blk, "thinking", None)
    name     = getattr(blk, "name", None)
    tinput   = getattr(blk, "input", None)
    bid      = getattr(blk, "id", None) or getattr(blk, "tool_use_id", None)
    content  = getattr(blk, "content", None)

    if thinking is not None:
        if not thinking.strip():
            return "**🧠 Thinking:** *(empty)*\n"
        quoted = thinking.replace("\n", "\n> ")
        return f"**🧠 Thinking:**\n\n> {quoted}\n"
    if name is not None and tinput is not None:                 # ToolUseBlock
        try:
            args = json.dumps(tinput, indent=2, default=str)
        except Exception:
            args = repr(tinput)
        return (f"**🔧 Tool call:** `{name}`  *(id={bid})*\n\n"
                f"```json\n{args}\n```\n")
    if content is not None and bid is not None:                 # ToolResultBlock
        if isinstance(content, list):
            parts = []
            for c in content:
                if isinstance(c, dict) and c.get("type") == "text":
                    parts.append(c.get("text", ""))
                else:
                    parts.append(str(c))
            content = "\n".join(parts)
        flag = " ⚠️ ERROR" if getattr(blk, "is_error", False) else ""
        return f"**📦 Tool result:**{flag}  *(id={bid})*\n\n```\n{content}\n```\n"
    if text is not None:                                         # TextBlock
        if not text.strip():
            return "**💬 Text:** *(empty)*\n"
        return f"**💬 Text:**\n\n{text}\n"
    return f"**{cls}:** `{blk!r}`\n"


_RESULT_SKIP = {"answer_text"}                                   # already in conversation
_RESULT_DURATION = {"latency_s"}                                 # render via fmt_duration


def _format_result_value(k: str, v: Any) -> str:
    if k in _RESULT_DURATION:
        return fmt_duration(v)
    if k == "trajectory":
        return f"`{v}`"
    return str(v)


def write_trace(
    path: Path,
    *,
    header: dict[str, Any],
    ex: dict[str, Any],
    messages: list[Any],
    result: dict[str, Any],
) -> None:
    """Write a per-trial markdown trace. Failures are non-fatal."""
    out: list[str] = ["# Trace", ""]
    out.append("## Header")
    for k, v in header.items():
        out.append(f"- **{k}**: {v}")
    out.append("")

    out.append("## Problem")
    out.append(f"- **level**: {ex.get('level')}  |  **difficulty**: {ex.get('difficulty')}")
    out.append(f"- **source**: {ex.get('source','?')}  |  **type**: {ex.get('type','?')}")
    out.append("")
    out.append("### Problem text")
    out.append("")
    out.append(ex.get("problem", ""))
    out.append("")
    out.append("### Gold answer")
    out.append("")
    out.append(f"```\n{ex.get('answer','')}\n```")
    out.append("")

    out.append("## Conversation")
    out.append("")
    for i, msg in enumerate(messages):
        role = type(msg).__name__
        subtype = getattr(msg, "subtype", "")
        suffix = f" ({subtype})" if subtype else ""
        out.append(f"### Message {i}: {role}{suffix}")
        out.append("")
        content = getattr(msg, "content", None)
        if isinstance(content, list):
            for blk in content:
                out.append(_format_block(blk))
        else:
            data = getattr(msg, "data", None)
            if data is not None:
                slim = (
                    {k: data.get(k) for k in _INIT_KEYS_OF_INTEREST if k in data}
                    if subtype == "init" and isinstance(data, dict)
                    else data
                )
                try:
                    rendered = json.dumps(slim, indent=2, default=str)
                except Exception:
                    rendered = repr(slim)
                out.append(f"```json\n{rendered}\n```")
            elif content is not None:
                out.append(f"```\n{content}\n```")
        out.append("")

    out.append("## Result")
    for k, v in result.items():
        if k in _RESULT_SKIP:
            continue
        out.append(f"- **{k}**: {_format_result_value(k, v)}")

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(out))
    except Exception as e:
        print(f"  (trace write failed for {path.name}: {e})")


# ---------- atomic per-trace counter ----------

_TRACE_COUNTER = 0
_TRACE_LOCK = asyncio.Lock()


async def next_trace_idx() -> int:
    """Returns a strictly-increasing integer per call; safe under asyncio."""
    global _TRACE_COUNTER
    async with _TRACE_LOCK:
        _TRACE_COUNTER += 1
        return _TRACE_COUNTER
