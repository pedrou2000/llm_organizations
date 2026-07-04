"""Per-trajectory statistics + per-step rendering for the visualizer.

Computes the header summary (outcome scores, effort/tokens, action histogram,
meta-work signals) and shapes each step into a render-ready dict for the
templates.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from typing import Any

from .loader import Trial, detect_termination

# Tool functions treated as "writing the deliverable" (object-level).
_WRITE_TOOLS = {"apply_patch"}


# ---------- per-step shaping ----------


def first_call(step: dict) -> dict | None:
    tcs = step.get("tool_calls") or []
    return tcs[0] if tcs else None


def _obs_text(step: dict) -> str:
    obs = step.get("observation")
    if not isinstance(obs, dict):
        return ""
    parts = [str(r.get("content", "")) for r in obs.get("results", []) if isinstance(r, dict)]
    return "\n".join(p for p in parts if p)


def _patch_files(patch_input: str) -> list[str]:
    return re.findall(r"\*\*\* (?:Add|Update|Delete) File: (.+)", patch_input or "")


def action_summary(step: dict) -> str:
    """One-line description of what a step did."""
    c = first_call(step)
    if not c:
        return "prose" if (step.get("message") or "").strip() else "(empty)"
    fn = c.get("function_name") or "?"
    a = c.get("arguments") or {}
    if fn == "exec_command":
        return f"exec: {str(a.get('cmd') or a.get('command') or '')[:120]}"
    if fn == "apply_patch":
        files = _patch_files(str(a.get("input", "")))
        return f"patch: {', '.join(files) if files else '?'}"
    if fn == "update_plan":
        return f"update_plan ({len(a.get('plan', []))} items)"
    if fn == "write_stdin":
        return "write_stdin"
    return fn


def step_kind(step: dict) -> str:
    """Coarse category for filtering/coloring: prose | exec | patch | plan | other."""
    c = first_call(step)
    if not c:
        return "prose"
    fn = c.get("function_name") or ""
    return {
        "exec_command": "exec",
        "apply_patch": "patch",
        "update_plan": "plan",
        "write_stdin": "exec",
    }.get(fn, "other")


def _fmt_size(n: int) -> str:
    """Compact char-count label, e.g. 742 -> '742', 12030 -> '12.0K'."""
    return f"{n/1000:.1f}K" if n >= 1000 else str(n)


def shape_step(step: dict) -> dict:
    """Render-ready view of a step for the template (full fidelity kept)."""
    c = first_call(step)
    args = (c.get("arguments") or {}) if c else {}
    message = (step.get("message") or "").strip()
    args_json = json.dumps(args, indent=2) if args else ""
    observation = _obs_text(step)
    # Total content size of the step (message + tool args + observation), so the
    # giant apply_patch steps are easy to spot in the collapsed list.
    size = len(message) + len(args_json) + len(observation)
    return {
        "id": step.get("step_id"),
        "source": step.get("source") or "?",
        "kind": step_kind(step),
        "action": action_summary(step),
        "message": message,
        "tool_name": c.get("function_name") if c else None,
        "args_json": args_json,
        "observation": observation,
        "size": size,
        "size_fmt": _fmt_size(size),
    }


# ---------- trajectory-level summary ----------


def _num(d: dict, key: str) -> Any:
    v = d.get(key)
    return v if isinstance(v, (int, float)) else None


def summarize(trial: Trial) -> dict:
    """The stats header: outcome, effort/tokens, action histogram, meta signals."""
    steps = trial.steps
    fm = trial.trajectory.get("final_metrics", {}) or {}

    # action histogram
    hist: Counter = Counter()
    for s in steps:
        for c in (s.get("tool_calls") or []):
            hist[c.get("function_name") or "?"] += 1

    # meta-work signals
    agent_steps = [s for s in steps if s.get("source") == "agent"]
    prose_steps = sum(1 for s in agent_steps
                      if not (s.get("tool_calls")) and (s.get("message") or "").strip())
    plan_updates = hist.get("update_plan", 0)
    first_write = next(
        (i for i, s in enumerate(steps)
         if any((c.get("function_name") in _WRITE_TOOLS)
                for c in (s.get("tool_calls") or []))),
        None,
    )
    first_write_frac = (first_write / len(steps)) if (first_write is not None and steps) else None

    # meta-layer size (messages + capped action/obs) vs full — the 10% insight
    full_chars = len(json.dumps(trial.trajectory))
    meta_chars = 0
    for s in steps:
        meta_chars += len(s.get("message") or "")
        for c in (s.get("tool_calls") or []):
            meta_chars += min(len(json.dumps(c.get("arguments") or {})), 200)
        meta_chars += min(len(_obs_text(s)), 300)

    # outcome (from verifier files); metrics.partial_score is the FRACTIONAL
    # correctness (reward.json:stage:correctness is binary — see harbor scoring).
    correctness = _num(trial.metrics, "partial_score")
    ux = _num(trial.reward, "stage:ux")
    partial = (0.5 * correctness + 0.5 * ux) if (correctness is not None and ux is not None) else None

    # duration from step timestamps
    ts = [s.get("timestamp") for s in steps if s.get("timestamp")]
    duration = None
    if len(ts) >= 2:
        try:
            from datetime import datetime
            fmt = "%Y-%m-%dT%H:%M:%S.%fZ"
            duration = (datetime.strptime(ts[-1], fmt) - datetime.strptime(ts[0], fmt)).total_seconds()
        except Exception:
            duration = None

    term = detect_termination(trial.trial_dir)

    return {
        "task": trial.task,
        "job": trial.job,
        "trial_id": trial.trial_id,
        "model": trial.agent.get("model_name"),
        "agent": trial.agent.get("name"),
        # how the rollout ended (no explicit submit in SWE-Marathon)
        "term_mode": term["mode"],
        "term_label": term["label"],
        "term_detail": term["detail"],
        # outcome
        "gates_passed": _num(trial.metrics, "gates_passed"),
        "gates_total": _num(trial.metrics, "gates_total"),
        "correctness": correctness,
        "ux": ux,
        "partial": partial,
        # effort
        "n_steps": len(steps),
        "prompt_tokens": _num(fm, "total_prompt_tokens"),
        "completion_tokens": _num(fm, "total_completion_tokens"),
        "cached_tokens": _num(fm, "total_cached_tokens"),
        "duration_sec": duration,
        # action mix
        "action_hist": dict(hist),
        # meta-work signals
        "prose_steps": prose_steps,
        "plan_updates": plan_updates,
        "first_write_step": first_write,
        "first_write_frac": first_write_frac,
        "meta_chars": meta_chars,
        "full_chars": full_chars,
        "meta_frac": (meta_chars / full_chars) if full_chars else None,
    }
