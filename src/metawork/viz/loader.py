"""Discover and load Harbor trials for the visualizer — full fidelity.

Unlike `metawork.harbor.source` (which flattens BLINDLY for judging — drops
system/user steps, scrubs agent identity, coarsens tool names), this loads the
trajectory verbatim for a human to read: every step, real tool names, and the
outcome scores joined from the trial's verifier files.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_JOBS_DIR = Path("results/metawork/trajectories/harbor")


def _read_json(p: Path) -> dict | None:
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


@dataclass
class Trial:
    """One agent trajectory + its trial metadata, loaded full-fidelity."""

    job: str                       # e.g. "m1_gpt55_final16"
    trial_id: str                  # e.g. "excel-clone__B8czzhL"
    task: str                      # e.g. "excel-clone"
    trial_dir: Path
    trajectory: dict = field(default_factory=dict)   # raw ATIF trajectory.json
    reward: dict = field(default_factory=dict)        # verifier/reward.json
    metrics: dict = field(default_factory=dict)       # verifier/correctness/metrics.json

    @property
    def key(self) -> str:
        return f"{self.job}/{self.trial_id}"

    @property
    def steps(self) -> list[dict]:
        return self.trajectory.get("steps", [])

    @property
    def agent(self) -> dict:
        a = self.trajectory.get("agent")
        return a if isinstance(a, dict) else {}


def _task_of(trial_id: str) -> str:
    # trial dirs are "<task>__<hash>"; task may itself contain no "__".
    return trial_id.split("__", 1)[0]


# Exception TYPES (harbor's ExceptionInfo.exception_type) grouped into a coarse
# termination `mode`. Authoritative source: result.json:exception_info, which
# harbor writes via ExceptionInfo.from_exception() for ANY error that ends a
# trial — so new failure kinds get their real class name automatically. Anything
# unmapped falls back to mode="error" with the raw type shown, never silently
# "clean". Extend this map as new exception types are observed.
_EXC_TYPE_MODE = {
    "ApiRateLimitError": ("rate_limit", "cut off · rate-limit",
                          "API rate-limit truncated the run (infra, not agent)"),
    "TimeoutError": ("timeout", "timeout",
                     "harness stopped the agent at the wall-clock limit"),
    "AgentTimeoutError": ("timeout", "timeout",
                          "harness stopped the agent at the wall-clock limit"),
}


def detect_termination(trial_dir: Path) -> dict:
    """How the rollout ENDED — there is no explicit 'submit' in SWE-Marathon
    (scoring is on the final container state), so we read harbor's authoritative
    `result.json:exception_info`:

      clean   — no exception_info; the agent ended the rollout itself.
      <mapped>— a known exception type -> rate_limit / timeout / ...
      error   — an exception we don't have a bucket for yet (its type is shown).

    Returns {"mode", "label", "detail", "exc_type"}. A non-clean ending means the
    trajectory is TRUNCATED (infra/harness, not the agent's choice) — the
    meta-work judge should not read the abrupt stop as premature termination.

    Robust to new failures by construction: it keys off the typed exception harbor
    records, not on log string-matching. Unknown types surface as `error` with the
    real class name rather than being mislabeled clean.
    """
    result = _read_json(trial_dir / "result.json") or {}
    ei = result.get("exception_info")
    if not ei:
        return {"mode": "clean", "label": "clean", "exc_type": None,
                "detail": "agent ended the rollout itself (no harness exception)"}
    exc_type = ei.get("exception_type") or "UnknownError"
    if exc_type in _EXC_TYPE_MODE:
        mode, label, detail = _EXC_TYPE_MODE[exc_type]
    else:
        mode, label, detail = "error", exc_type, f"trial ended on {exc_type}"
    return {"mode": mode, "label": label, "exc_type": exc_type, "detail": detail}


def load_trial(trial_dir: Path, job: str) -> Trial | None:
    """Load one trial dir. Returns None if it has no agent trajectory."""
    traj = _read_json(trial_dir / "agent" / "trajectory.json")
    if not traj:
        return None
    return Trial(
        job=job,
        trial_id=trial_dir.name,
        task=_task_of(trial_dir.name),
        trial_dir=trial_dir,
        trajectory=traj,
        reward=_read_json(trial_dir / "verifier" / "reward.json") or {},
        metrics=_read_json(trial_dir / "verifier" / "correctness" / "metrics.json") or {},
    )


def discover_trials(jobs_dir: Path | str = DEFAULT_JOBS_DIR) -> list[Trial]:
    """Find every trial (dir with agent/trajectory.json) under jobs_dir."""
    jobs_dir = Path(jobs_dir)
    trials: list[Trial] = []
    if not jobs_dir.exists():
        return trials
    for job_dir in sorted(p for p in jobs_dir.iterdir() if p.is_dir()):
        for trial_dir in sorted(p for p in job_dir.iterdir() if p.is_dir()):
            t = load_trial(trial_dir, job=job_dir.name)
            if t is not None:
                trials.append(t)
    return trials


def load_by_key(key: str, jobs_dir: Path | str = DEFAULT_JOBS_DIR) -> Trial | None:
    """Load a single trial by its "job/trial_id" key."""
    job, _, trial_id = key.partition("/")
    trial_dir = Path(jobs_dir) / job / trial_id
    return load_trial(trial_dir, job=job) if trial_dir.is_dir() else None
