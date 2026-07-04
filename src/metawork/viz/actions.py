"""The single source of truth for agent-action semantics.

Everything the visualizer knows about "what tools an agent uses and how to
render them" lives here — the coarse *kind* of a step (for coloring/filtering),
its display color, and a one-line summary of what a step did. Adding support for
a new agent or tool is a one-place edit: extend `KINDS` and/or `TOOL_KIND`.

This keeps the tool vocabulary from leaking (as it previously did) into stats,
the server, and the templates. Colors are defined once here and injected into
the page CSS, so Python and CSS never drift.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Kind:
    """A coarse action category — how a step is colored/filtered."""

    key: str      # machine key, used in CSS classes + filter chips
    label: str    # human label
    color: str    # hex; the ONE definition, injected into template CSS


# The kind vocabulary, in display order. `other` is the catch-all so a novel
# tool is always rendered (never dropped), just uncategorized.
KINDS: tuple[Kind, ...] = (
    Kind("prose", "prose", "#8b93a3"),
    Kind("exec", "exec", "#4f8ff7"),
    Kind("patch", "patch", "#f2a541"),
    Kind("plan", "plan", "#4fd1a5"),
    Kind("other", "other", "#c98bdb"),
)
KIND_BY_KEY: dict[str, Kind] = {k.key: k for k in KINDS}

# Tool function_name -> kind key. Extend for new agents/tools.
TOOL_KIND: dict[str, str] = {
    "exec_command": "exec",
    "write_stdin": "exec",
    "apply_patch": "patch",
    "update_plan": "plan",
}

# Tools that write the deliverable (object-level) — used for the "first write"
# meta-work signal (how long the agent oriented before producing artifacts).
WRITE_TOOLS: frozenset[str] = frozenset({"apply_patch"})


def first_call(step: dict) -> dict | None:
    """The step's first tool call, or None for a prose-only step."""
    tcs = step.get("tool_calls") or []
    return tcs[0] if tcs else None


def kind_of(step: dict) -> str:
    """Coarse kind key: prose | exec | patch | plan | other."""
    c = first_call(step)
    if not c:
        return "prose"
    return TOOL_KIND.get(c.get("function_name") or "", "other")


def is_write_step(step: dict) -> bool:
    """True if the step writes the deliverable (any WRITE_TOOLS call)."""
    return any((c.get("function_name") in WRITE_TOOLS)
               for c in (step.get("tool_calls") or []))


_PATCH_FILES_RE = re.compile(r"\*\*\* (?:Add|Update|Delete) File: (.+)")


def summarize_action(step: dict, *, cmd_cap: int = 120) -> str:
    """One-line description of what a step did (tool-aware, extensible)."""
    c = first_call(step)
    if not c:
        return "prose" if (step.get("message") or "").strip() else "(empty)"
    fn = c.get("function_name") or "?"
    a = c.get("arguments") or {}
    if fn == "exec_command":
        return f"exec: {str(a.get('cmd') or a.get('command') or '')[:cmd_cap]}"
    if fn == "apply_patch":
        files = _PATCH_FILES_RE.findall(str(a.get("input", "")))
        return f"patch: {', '.join(files) if files else '?'}"
    if fn == "update_plan":
        return f"update_plan ({len(a.get('plan', []))} items)"
    if fn == "write_stdin":
        return "write_stdin"
    return fn


def observation_text(step: dict) -> str:
    """Flatten a step's observation results to plain text."""
    obs = step.get("observation")
    if not isinstance(obs, dict):
        return ""
    parts = [str(r.get("content", "")) for r in obs.get("results", [])
             if isinstance(r, dict)]
    return "\n".join(p for p in parts if p)


def css_vars() -> str:
    """`--k-<kind>: <color>;` declarations — the one place kind colors are set,
    injected into the page so template CSS references them without duplicating
    hex values."""
    return "".join(f"--k-{k.key}:{k.color};" for k in KINDS)
