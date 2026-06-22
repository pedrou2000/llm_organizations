"""Harvest SWE-Marathon agent trajectories from the public website.

The SWE-Marathon site (swe-marathon.vercel.app) ships, as static assets:
  - a JS bundle containing per-trial metadata records
    (model, reward, partial, correctness, ux, gates, tokens, cost, steps)
  - one JSON per trial at /trajectories/<task>-<id>.json, each a list of
    summarized tool-call rows: {step, call, kind, title, detail}

This module pulls both, flattens each trajectory to readable text, and
exposes a stratified sampler (S/M/L) so downstream judging is size-agnostic.

The trajectory text is kept BLIND: it carries no model identity or score.
Metadata (model/partial/...) lives in a separate records table and is only
joined back AFTER judging, so the meta-work judge never sees the outcome.
"""
from __future__ import annotations

import json
import random
import re
import urllib.request
from collections import defaultdict
from pathlib import Path
from typing import Any

SITE = "https://swe-marathon.vercel.app"
BUNDLE_PATH = "/assets/index-Csg-aQzw.js"   # pinned bundle hash (update if site rebuilds)

# Where harvested artifacts live (under the standard results/ root).
DEFAULT_CACHE = Path("results/metawork/trajectories")


# ---------- download helpers ----------


def _fetch(url: str, dest: Path) -> Path:
    """Download `url` to `dest` unless already cached. Returns dest."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    with urllib.request.urlopen(url) as r:
        dest.write_bytes(r.read())
    return dest


def fetch_bundle(cache: Path = DEFAULT_CACHE) -> str:
    """Download and return the site JS bundle text (cached)."""
    p = _fetch(SITE + BUNDLE_PATH, cache / "_bundle.js")
    return p.read_text(errors="replace")


# ---------- metadata records (from the JS bundle) ----------

# Each trial record in the bundle looks like:
#   {id:`slack-clone-217`,trial:`slack-clone-217`,agent:`Claude Code`,
#    model:`Claude Opus 4.7`,reward:0,partial:.6,correctness:.2,ux:1,
#    gates:`1 / 5`,tokens:`14.7M`,cost:`$12.56`,...,steps:147}
_REC_RE = re.compile(r"id:`([a-z0-9-]+-\d+)`(.*?)steps:(\d+)")


def _grab(body: str, key: str, default: Any = None) -> Any:
    m = re.search(rf"{key}:`?([^`,}}]+)`?", body)
    return m.group(1).strip("`") if m else default


def parse_records(bundle: str) -> dict[str, dict]:
    """Extract every trial's metadata record from the bundle.

    Returns {trial_id -> {id, model, reward, partial, correctness, ux,
    gates, tokens, cost, steps, task}}.
    """
    recs: dict[str, dict] = {}
    for m in _REC_RE.finditer(bundle):
        tid, body, steps = m.group(1), m.group(2), int(m.group(3))
        recs[tid] = {
            "id": tid,
            "task": tid.rsplit("-", 1)[0],
            "model": _grab(body, "model"),
            "reward": _grab(body, "reward"),
            "partial": _grab(body, "partial"),
            "correctness": _grab(body, "correctness"),
            "ux": _grab(body, "ux"),
            "gates": _grab(body, "gates"),
            "tokens": _grab(body, "tokens"),
            "cost": _grab(body, "cost"),
            "steps": steps,
        }
    return recs


def list_trajectory_ids(bundle: str) -> list[str]:
    """All trial ids that have a downloadable trajectory JSON, deduped.

    The bundle references both plain ids (`slack-clone-217`) and
    hash-suffixed duplicates (`slack-clone-b0a98beb-...`); we keep the
    plain `<task>-<int>` form only.
    """
    ids = re.findall(r"/trajectories/([a-z0-9-]+-\d+)\.json", bundle)
    plain = [t for t in ids if re.fullmatch(r"[a-z0-9-]+-\d+", t)
             and not re.search(r"-[0-9a-f]{6,}-\d+$", t)]
    return sorted(set(plain))


# ---------- trajectory download + flatten ----------


def fetch_trajectory(tid: str, cache: Path = DEFAULT_CACHE) -> dict:
    """Download one trajectory JSON (cached). Returns the parsed dict."""
    p = _fetch(f"{SITE}/trajectories/{tid}.json", cache / f"{tid}.json")
    return json.loads(p.read_text())


# Scrub scaffold/agent-identity fingerprints that leak the model indirectly
# via temp paths (e.g. /tmp/claude-0/, /root/.gemini/tmp/, /home/.kimi/plans).
# Replace with a neutral token so the judge stays blind to which agent ran.
_IDENTITY_RE = re.compile(
    r"(claude|gemini|kimi|gpt|openai|anthropic|deepseek|minimax|glm|qwen)"
    r"[-_a-z0-9]*",
    re.IGNORECASE,
)
# Only scrub inside path-like / token-like contexts to avoid mangling prose
# such as "the gemini of the idea"; in practice these names only appear in
# tool-id and filesystem-path fragments.
# Match a model name only when it sits inside a path/dotfile fragment
# (preceded by / . - _ or following one), so prose isn't mangled.
_PATHY_IDENTITY_RE = re.compile(
    r"(?<=[/.\-_])(claude|gemini|kimi|gpt|openai|anthropic|deepseek|minimax|glm|qwen)",
    re.IGNORECASE,
)


def _scrub_identity(text: str) -> str:
    return _PATHY_IDENTITY_RE.sub("AGENT", text)


def flatten_rows(rows: list[dict], *, max_detail: int = 500) -> str:
    """Render trajectory rows to blind, readable text.

    Each row becomes:  [step N] Kind: title\n    <agent prose, truncated>
    The agent's natural-language message is the chunk before 'Tool arguments'.
    No model identity or score appears anywhere; scaffold fingerprints in
    temp paths (e.g. /tmp/claude-0/) are scrubbed to a neutral token.
    """
    out: list[str] = []
    for r in rows:
        detail = str(r.get("detail", ""))
        msg = detail.split("Tool arguments")[0]
        msg = msg.replace("Agent message:", "").strip()
        title = str(r.get("title", ""))[:120]
        out.append(f"[step {r.get('step')}] {r.get('kind')}: {title}")
        if msg:
            out.append(f"    {msg[:max_detail]}")
    return _scrub_identity("\n".join(out))


def trajectory_stats(rows: list[dict]) -> dict:
    """Cheap structural stats for inspection (no judging)."""
    from collections import Counter
    kinds = Counter(r.get("kind") for r in rows)
    n = len(rows)
    PLAN = {"TaskCreate", "TaskUpdate", "SetTodoList", "TodoWrite",
            "EnterPlanMode", "ExitPlanMode", "enter_plan_mode",
            "exit_plan_mode", "TaskList"}
    WRITE = {"Write", "Edit", "WriteFile", "StrReplaceFile", "MultiEdit",
             "CreateFile"}
    SUBMIT = {"Submit", "Finish", "Complete"}
    first_write = next((i for i, r in enumerate(rows)
                        if r.get("kind") in WRITE), None)
    return {
        "n_rows": n,
        "n_plan_tool": sum(kinds.get(k, 0) for k in PLAN),
        "n_write": sum(kinds.get(k, 0) for k in WRITE),
        "n_bash": kinds.get("Bash", 0),
        "n_submit": sum(kinds.get(k, 0) for k in SUBMIT),
        "first_write_frac": (first_write / n) if (first_write is not None and n) else None,
        "kinds": dict(kinds),
    }


# ---------- stratified sampling (S / M / L) ----------

SIZES = {"s": 20, "m": 100, "l": None}   # None = full corpus


def stratified_sample(
    ids: list[str],
    records: dict[str, dict],
    *,
    n: int | None,
    seed: int = 0,
) -> list[str]:
    """Pick `n` trial ids spread evenly across (task, model) cells.

    `n=None` returns all ids. Deterministic given seed. Ensures small runs
    are representative rather than all-one-task.
    """
    if n is None or n >= len(ids):
        return list(ids)
    rng = random.Random(seed)
    # bucket by (task, model)
    cells: dict[tuple, list[str]] = defaultdict(list)
    for t in ids:
        rec = records.get(t, {})
        cells[(rec.get("task"), rec.get("model"))].append(t)
    for v in cells.values():
        rng.shuffle(v)
    # round-robin across cells until we have n
    order = sorted(cells.keys(), key=lambda k: (str(k[0]), str(k[1])))
    rng.shuffle(order)
    picked: list[str] = []
    i = 0
    while len(picked) < n and any(cells.values()):
        cell = order[i % len(order)]
        if cells[cell]:
            picked.append(cells[cell].pop())
        i += 1
        if i > len(order) * 1000:   # safety
            break
    return picked[:n]


# ---------- top-level harvest ----------


def harvest(
    *,
    size: str = "s",
    seed: int = 0,
    cache: Path | str = DEFAULT_CACHE,
    tasks: list[str] | None = None,
) -> list[dict]:
    """Download + flatten a stratified sample of trajectories.

    Returns a list of rows, one per trajectory, each with:
      id, task, model(+all metadata), n_rows + structural stats,
      flat_text (the blind trajectory text for judging).
    """
    cache = Path(cache)
    bundle = fetch_bundle(cache)
    records = parse_records(bundle)
    all_ids = list_trajectory_ids(bundle)
    if tasks:
        all_ids = [t for t in all_ids if records.get(t, {}).get("task") in tasks]

    n = SIZES.get(size, None) if isinstance(size, str) else int(size)
    chosen = stratified_sample(all_ids, records, n=n, seed=seed)

    rows: list[dict] = []
    for i, tid in enumerate(chosen, 1):
        try:
            traj = fetch_trajectory(tid, cache)
            flat = flatten_rows(traj["rows"])
            stats = trajectory_stats(traj["rows"])
        except Exception as e:
            rows.append({"id": tid, "error": f"{type(e).__name__}: {e}"})
            continue
        rec = records.get(tid, {})
        rows.append({
            **rec,
            **{k: v for k, v in stats.items() if k != "kinds"},
            "kinds": json.dumps(stats["kinds"]),
            "flat_text": flat,
            "flat_chars": len(flat),
        })
        if i % 25 == 0:
            print(f"  harvested {i}/{len(chosen)}", flush=True)
    return rows
