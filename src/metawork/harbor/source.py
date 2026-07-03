"""Adapt our own Harbor trajectories into the meta-work judge's input format.

This is the Source-B sibling of `metawork.published.harvest`. Where that module
pulls the PUBLISHED SWE-Marathon trajectories off the website, this one reads the
trajectories WE generate locally with Harbor (`results/metawork/harbor_jobs/...`) and
renders each into the same blind `flat_text` + metadata row the judge consumes.

It deliberately shares nothing with the published path (no web download, no
JS-bundle parsing, no `harvest_<size>.parquet` schema): the published corpus is
kept only for the observational study, and this path stands alone. The only
durable dependency is the judge itself (`metawork.judges.v1_fixed`), fed downstream by
`judge_job.py`.

Harbor trajectories are ATIF-v1.7:
    {schema_version, session_id, agent, steps:[...], final_metrics}
where each step is
    {step_id, timestamp, source: system|user|agent, message,
     tool_calls:[{tool_call_id, function_name, arguments}], observation, extra}

We flatten ONLY the agent's own steps (its prose + the actions it takes), which
mirrors what the published flattener emits (agent message + action arc) and, as
a bonus, keeps the system prompt / task description — the only places the codex
identity leaks — out of the judged text. A defensive identity scrub runs anyway.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

DEFAULT_JOBS_DIR = Path("results/metawork/harbor_jobs")

# Map ATIF tool function names to the coarse "kind" vocabulary the published
# trajectories use (so trajectory_stats / the judge see familiar action types).
#   exec_command / write_stdin -> Bash      (shell actions)
#   apply_patch                -> Write      (file edits)
# Unknown tools fall through to their raw function name.
_KIND_MAP = {
    "exec_command": "Bash",
    "write_stdin": "Bash",
    "apply_patch": "Write",
}
_WRITE_KINDS = {"Write"}

# Identity fingerprints that would tell the (otherwise blind) judge which agent
# ran. Scrubbed to a neutral token. Matched anywhere, case-insensitively, since
# these appear in tool ids and file paths (e.g. /tmp/codex-home/, $CODEX_HOME),
# not in meaningful prose we'd want to preserve.
_IDENTITY_RE = re.compile(
    r"(codex|openai|gpt-?5\.?5?|gpt|anthropic|claude)",
    re.IGNORECASE,
)


def _scrub_identity(text: str) -> str:
    return _IDENTITY_RE.sub("AGENT", text)


def _kind_for(fn: str) -> str:
    return _KIND_MAP.get(fn, fn or "Tool")


def _title_for(fn: str, args: dict) -> str:
    """A short, readable one-liner describing the action, like the published
    `title` field (e.g. a shell command, or the file(s) a patch touches)."""
    if fn in ("exec_command", "write_stdin"):
        return str(args.get("cmd") or args.get("input") or "").strip()
    if fn == "apply_patch":
        # Pull the file paths out of the patch envelope for a compact title.
        patch = str(args.get("input", ""))
        files = re.findall(r"\*\*\* (?:Add|Update|Delete) File: (.+)", patch)
        return ", ".join(files) if files else "apply_patch"
    # Generic: compact JSON of the args.
    return json.dumps(args)[:200]


def steps_to_rows(steps: list[dict]) -> list[dict]:
    """Convert ATIF agent steps into {step, call, kind, title, detail} rows.

    Only `source == "agent"` steps are kept (the agent's own prose and actions);
    system/user steps (prompt, task, environment) are dropped — both to mirror
    the published flattener and to keep agent-identity text out of the judge.
    A prose-only agent step (a plan / reflection with no tool call) becomes a
    `Note` row carrying its message, so planning narrative survives.
    """
    rows: list[dict] = []
    call = 0
    for s in steps:
        if s.get("source") != "agent":
            continue
        msg = (s.get("message") or "").strip()
        tool_calls = s.get("tool_calls") or []

        if not tool_calls:
            # Prose-only step: a plan, reflection, or status note.
            if msg:
                rows.append({
                    "step": s.get("step_id"),
                    "call": call,
                    "kind": "Note",
                    "title": "(planning / reflection)",
                    "detail": f"Agent message:\n{msg}",
                })
                call += 1
            continue

        for tc in tool_calls:
            fn = tc.get("function_name") or ""
            args = tc.get("arguments") or {}
            # The agent prose (if any) rides on the first tool call of the step,
            # then is consumed so it isn't repeated across multi-call steps.
            detail = f"Agent message:\n{msg}\n" if msg else ""
            msg = ""
            rows.append({
                "step": s.get("step_id"),
                "call": call,
                "kind": _kind_for(fn),
                "title": _title_for(fn, args),
                "detail": detail,
            })
            call += 1
    return rows


def flatten_rows(rows: list[dict], *, max_detail: int = 500,
                 keep_prose: bool = True) -> str:
    """Render rows to blind, readable text — same shape as the published
    flattener: `[step N] Kind: title` plus the agent prose beneath it.

    Re-implemented here (rather than imported from the published path) so this module
    has no dependency on the throwaway published-corpus path.

    `keep_prose` (default True) is the honest, full-fidelity view: it includes
    the agent's reasoning text, which our ATIF trajectories capture. Set False
    for "published-parity" mode — action arc only, no prose, dropping the
    prose-only Note rows — which matches how the published SWE-Marathon harvest
    largely lost GPT-5.5's reasoning (≈60% bare "Executed" stubs). Use parity
    mode ONLY when comparing head-to-head against the published numbers.
    """
    out: list[str] = []
    for r in rows:
        if not keep_prose and r.get("kind") == "Note":
            continue   # prose-only planning row — has no action to show
        title = str(r.get("title", ""))[:120]
        out.append(f"[step {r.get('step')}] {r.get('kind')}: {title}")
        if keep_prose:
            msg = str(r.get("detail", "")).replace("Agent message:", "").strip()
            if msg:
                out.append(f"    {msg[:max_detail]}")
    return _scrub_identity("\n".join(out))


def trajectory_stats(rows: list[dict]) -> dict:
    """Cheap structural stats over the converted rows (no judging)."""
    kinds = Counter(r.get("kind") for r in rows)
    n = len(rows)
    first_write = next((i for i, r in enumerate(rows)
                        if r.get("kind") in _WRITE_KINDS), None)
    return {
        "n_rows": n,
        "n_plan_tool": kinds.get("Note", 0),
        "n_write": sum(kinds.get(k, 0) for k in _WRITE_KINDS),
        "n_bash": kinds.get("Bash", 0),
        "n_submit": 0,  # codex has no explicit submit action
        "first_write_frac": (first_write / n) if (first_write is not None and n) else None,
        "kinds": dict(kinds),
    }


# ---------- metadata (from the trial's verifier/result files) ----------


def _read_json(p: Path) -> dict | None:
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


def _trial_metadata(trial_dir: Path) -> dict:
    """Pull the outcome metadata for one trial from its on-disk artifacts.

    `partial` here is the same 2-stage score used elsewhere
    (0.5*correctness + 0.5*ux); `correctness` is the fractional gate score
    (gates_passed/gates_total), `ux` the CUA-stage reward.

    Subtlety: excel-clone grades correctness in `binary` scoring_mode, so
    `reward.json:stage:correctness` is all-or-nothing (1.0 only if ALL 18 gates
    pass, else 0.0) — for GPT-5.5 it's a constant 0.0 with no signal. The real
    fractional correctness is `metrics.json:partial_score`. We MUST build
    `partial` from that fractional value, NOT from the binary stage reward, or
    the headline 2-stage score collapses to 0.5*ux (~0.12 instead of ~0.32).
    The binary all-gates reward is preserved separately as `reward`.
    """
    reward = _read_json(trial_dir / "verifier" / "reward.json") or {}
    metrics = _read_json(trial_dir / "verifier" / "correctness" / "metrics.json") or {}

    # Fractional gate score (partial_score); fall back to the binary stage
    # reward only if metrics are missing.
    correctness = metrics.get("partial_score", reward.get("stage:correctness"))
    ux = reward.get("stage:ux")
    partial = None
    if correctness is not None and ux is not None:
        partial = 0.5 * float(correctness) + 0.5 * float(ux)

    gates_passed = metrics.get("gates_passed")
    gates_total = metrics.get("gates_total")
    gates = (f"{gates_passed} / {gates_total}"
             if gates_passed is not None and gates_total is not None else None)

    return {
        "reward": reward.get("reward"),
        "partial": partial,
        "correctness": correctness,
        "ux": ux,
        "gates": gates,
    }


# ---------- top-level load ----------


def load_trial(trial_dir: Path | str, *, task: str | None = None,
               keep_prose: bool = True) -> dict | None:
    """Load + flatten one Harbor trial directory into a judge-ready row.

    Returns None if the trial has no agent trajectory (e.g. an errored trial
    that never produced one). The returned row carries the blind `flat_text`
    plus outcome metadata, ready to drop into the judge driver. `keep_prose`
    selects full-fidelity (default) vs published-parity flattening — see
    `flatten_rows`.
    """
    trial_dir = Path(trial_dir)
    traj_path = trial_dir / "agent" / "trajectory.json"
    traj = _read_json(traj_path)
    if not traj or "steps" not in traj:
        return None

    rows = steps_to_rows(traj["steps"])
    flat = flatten_rows(rows, keep_prose=keep_prose)
    stats = trajectory_stats(rows)

    name = trial_dir.name                      # e.g. "excel-clone__pvxsgD4"
    task = task or name.split("__", 1)[0]
    meta = _trial_metadata(trial_dir)

    return {
        "id": name,
        "task": task,
        # Identity is recorded for grouping/analysis but never enters flat_text.
        "model": (traj.get("agent") or {}).get("model_name"),
        **meta,
        "steps": len(traj["steps"]),
        **{k: v for k, v in stats.items() if k != "kinds"},
        "kinds": json.dumps(stats["kinds"]),
        "flat_text": flat,
        "flat_chars": len(flat),
    }


def load_job(job: str, *, jobs_dir: Path | str = DEFAULT_JOBS_DIR,
             task: str | None = None, keep_prose: bool = True) -> list[dict]:
    """Load every trial under one Harbor job into judge-ready rows.

    `job` is the job directory name (e.g. "m1_gpt55_final16"). `task` optionally
    filters to a single task prefix. Trials without a trajectory are skipped.
    `keep_prose` selects full-fidelity (default) vs published-parity flattening.
    """
    job_dir = Path(jobs_dir) / job
    if not job_dir.is_dir():
        raise FileNotFoundError(f"no such Harbor job dir: {job_dir}")

    rows: list[dict] = []
    for trial_dir in sorted(job_dir.iterdir()):
        if not trial_dir.is_dir():
            continue
        if "__" not in trial_dir.name:
            continue   # skip non-trial dirs (config, logs, ...)
        if task and not trial_dir.name.startswith(f"{task}__"):
            continue
        row = load_trial(trial_dir, task=task, keep_prose=keep_prose)
        if row is not None:
            rows.append(row)
    return rows
