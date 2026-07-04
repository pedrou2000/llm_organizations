"""Blind staging: expose the raw trajectory to a judge without leaking the
agent's identity or the trial's grading artifacts.

Per design we give the judge the RAW trajectory.json verbatim (no curation, no
truncation — the bitter lesson). We only:
  1. isolate it — write a copy into its own temp dir, so Read/Grep/Glob can't
     wander into sibling files (verifier/reward.json, solution/, ...);
  2. scrub identity — replace model/agent fingerprints with "AGENT", so the
     judge is blind to WHICH model it is grading (load-bearing for the M4
     cross-model comparison).
Nothing else about the file is altered.
"""
from __future__ import annotations

import re
import tempfile
from pathlib import Path

# Identity fingerprints that would tell the (otherwise blind) judge which agent
# ran. Matched case-insensitively; these appear in the ATIF `agent`/`model_name`
# fields and in tool ids / paths (e.g. /tmp/codex-home, $CODEX_HOME).
_IDENTITY_RE = re.compile(
    r"(codex|openai|gpt-?5\.?5?|gpt|anthropic|claude)",
    re.IGNORECASE,
)


def _find_trajectory_json(path: Path) -> Path:
    """Resolve a trial dir OR a direct file to the trajectory.json to stage."""
    if path.is_file():
        return path
    candidate = path / "agent" / "trajectory.json"
    if candidate.is_file():
        return candidate
    raise FileNotFoundError(f"no trajectory.json found at {path}")


def stage_blind_trajectory(
    trajectory_path: Path | str,
    dest_dir: Path | str | None = None,
) -> Path:
    """Copy the trajectory into an isolated dir with identity scrubbed.

    Returns the path to the staged blind file. If `dest_dir` is given the file
    is written there (created if needed); otherwise a fresh temp dir is used.
    """
    src = _find_trajectory_json(Path(trajectory_path))
    raw = src.read_text()
    blind = _IDENTITY_RE.sub("AGENT", raw)

    if dest_dir is None:
        dest_dir = Path(tempfile.mkdtemp(prefix="mw_traj_"))
    else:
        dest_dir = Path(dest_dir)
        dest_dir.mkdir(parents=True, exist_ok=True)

    out = dest_dir / "trajectory.json"
    out.write_text(blind)
    return out
