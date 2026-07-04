"""Typed per-trajectory summary + per-step views for the visualizer.

`StepView` shapes one step for rendering; `TrajectorySummary` is the header
(identity / outcome / effort / action mix / meta-work signals / termination).
Both are dataclasses so the template contract is explicit and adding a field is
a single, type-checked place. Action semantics come from `actions`; number
formatting from `format`.
"""
from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from . import actions
from .format import FMT
from .loader import Trial, detect_termination

_TS_FMT = "%Y-%m-%dT%H:%M:%S.%fZ"
_META_ARG_CAP = 200   # chars of tool-args counted toward the "meta layer"
_META_OBS_CAP = 300   # chars of observation counted toward the "meta layer"
_HAY_CAP = 4000       # chars of searchable text kept per step


def _num(d: dict, key: str) -> float | int | None:
    v = d.get(key)
    return v if isinstance(v, (int, float)) else None


# ---------- per-step view ----------


@dataclass
class StepView:
    """One step, shaped for the template (full fidelity kept)."""

    id: Any
    source: str
    kind: str
    action: str
    message: str
    tool_name: str | None
    args_json: str
    observation: str
    size: int

    @property
    def size_fmt(self) -> str:
        return FMT.chars(self.size)

    @property
    def msg_preview(self) -> str:
        return (self.message[:90] + "…") if len(self.message) > 90 else self.message

    @property
    def hay(self) -> str:
        """Lowercased searchable text (message + action + observation)."""
        return f"{self.message} {self.action} {self.observation}".lower()[:_HAY_CAP]


def shape_step(step: dict) -> StepView:
    c = actions.first_call(step)
    args = (c.get("arguments") or {}) if c else {}
    message = (step.get("message") or "").strip()
    args_json = json.dumps(args, indent=2) if args else ""
    observation = actions.observation_text(step)
    return StepView(
        id=step.get("step_id"),
        source=step.get("source") or "?",
        kind=actions.kind_of(step),
        action=actions.summarize_action(step),
        message=message,
        tool_name=(c.get("function_name") if c else None),
        args_json=args_json,
        observation=observation,
        # message + tool args + observation — so the giant apply_patch steps
        # stand out in the collapsed list.
        size=len(message) + len(args_json) + len(observation),
    )


# ---------- trajectory summary ----------


@dataclass
class HistBar:
    """One segment of the action-mix bar."""

    kind: str
    count: int
    color: str
    width: float   # percent of total


@dataclass
class TrajectorySummary:
    # identity
    task: str
    job: str
    trial_id: str
    model: str | None
    agent: str | None
    # termination (how the rollout ended — no explicit submit in SWE-Marathon)
    term_mode: str
    term_label: str
    term_detail: str
    # outcome
    gates_passed: float | int | None
    gates_total: float | int | None
    correctness: float | None
    ux: float | None
    partial: float | None
    # effort
    n_steps: int
    prompt_tokens: float | int | None
    completion_tokens: float | int | None
    cached_tokens: float | int | None
    duration_sec: float | None
    # action mix (raw function_name -> count) + meta-work signals
    action_hist: dict = field(default_factory=dict)
    prose_steps: int = 0
    plan_updates: int = 0
    first_write_step: int | None = None
    first_write_frac: float | None = None
    meta_chars: int = 0
    full_chars: int = 0
    meta_frac: float | None = None

    # ----- derived display views (used by templates directly) -----

    @property
    def hist_bars(self) -> list[HistBar]:
        """Action histogram aggregated by KIND, ready for the stacked bar."""
        by_kind: Counter = Counter()
        for fn, cnt in self.action_hist.items():
            by_kind[actions.TOOL_KIND.get(fn, "other")] += cnt
        total = sum(by_kind.values()) or 1
        return [
            HistBar(k.key, by_kind[k.key], k.color, 100 * by_kind[k.key] / total)
            for k in actions.KINDS if by_kind.get(k.key)
        ]

    @property
    def key(self) -> str:
        return f"{self.job}/{self.trial_id}"


def _duration_sec(steps: list[dict]) -> float | None:
    ts = [s.get("timestamp") for s in steps if s.get("timestamp")]
    if len(ts) < 2:
        return None
    try:
        return (datetime.strptime(ts[-1], _TS_FMT)
                - datetime.strptime(ts[0], _TS_FMT)).total_seconds()
    except (ValueError, TypeError):
        return None


def _meta_chars(steps: list[dict]) -> int:
    """Size of the 'meta-work layer' (messages + capped args/obs) — the signal
    that's a small fraction of the full, code-heavy trajectory."""
    total = 0
    for s in steps:
        total += len(s.get("message") or "")
        for c in (s.get("tool_calls") or []):
            total += min(len(json.dumps(c.get("arguments") or {})), _META_ARG_CAP)
        total += min(len(actions.observation_text(s)), _META_OBS_CAP)
    return total


def summarize(trial: Trial) -> TrajectorySummary:
    steps = trial.steps
    fm = trial.trajectory.get("final_metrics", {}) or {}
    term = detect_termination(trial.trial_dir)

    hist: Counter = Counter()
    for s in steps:
        for c in (s.get("tool_calls") or []):
            hist[c.get("function_name") or "?"] += 1

    prose_steps = sum(
        1 for s in steps
        if s.get("source") == "agent" and not s.get("tool_calls")
        and (s.get("message") or "").strip()
    )
    first_write = next((i for i, s in enumerate(steps) if actions.is_write_step(s)), None)
    first_write_frac = (first_write / len(steps)) if (first_write is not None and steps) else None

    full_chars = len(json.dumps(trial.trajectory))
    meta_chars = _meta_chars(steps)

    # metrics.partial_score is the FRACTIONAL correctness (reward.json's
    # stage:correctness is binary — see the harbor scoring notes).
    correctness = _num(trial.metrics, "partial_score")
    ux = _num(trial.reward, "stage:ux")
    partial = (0.5 * correctness + 0.5 * ux) if (correctness is not None and ux is not None) else None

    return TrajectorySummary(
        task=trial.task, job=trial.job, trial_id=trial.trial_id,
        model=trial.agent.get("model_name"), agent=trial.agent.get("name"),
        term_mode=term["mode"], term_label=term["label"], term_detail=term["detail"],
        gates_passed=_num(trial.metrics, "gates_passed"),
        gates_total=_num(trial.metrics, "gates_total"),
        correctness=correctness, ux=ux, partial=partial,
        n_steps=len(steps),
        prompt_tokens=_num(fm, "total_prompt_tokens"),
        completion_tokens=_num(fm, "total_completion_tokens"),
        cached_tokens=_num(fm, "total_cached_tokens"),
        duration_sec=_duration_sec(steps),
        action_hist=dict(hist),
        prose_steps=prose_steps, plan_updates=hist.get("update_plan", 0),
        first_write_step=first_write, first_write_frac=first_write_frac,
        meta_chars=meta_chars, full_chars=full_chars,
        meta_frac=(meta_chars / full_chars) if full_chars else None,
    )
