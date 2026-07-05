"""Load v2 meta-work judge results for the visualizer.

The judge writes a stage-mirrored inspection tree per trial under
`results/metawork/judged/v2_adaptive/scores/<job>/<trial_id>/` — the SAME
`job/trial_id` key the viz uses for trajectories, so the join is direct. We read
`score.json` (the aggregate: overall gap/observed + per-dimension verdicts with
target/observed/gap, confidence, cited evidence, reasoning) and shape it for the
templates.

Evidence `steps` are free-form LLM text ("13-16", "4,9,27", "all",
"16-26 (patch lines ...)"). We parse the integer step-ids we can (ranges +
comma lists) to drive inline step tagging, and simply skip what doesn't map to a
clean int rather than fabricate a mapping.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

_V2 = Path("results/metawork/judged/v2_adaptive")
# Harbor-run score trees can live in the canonical scores/ dir (future live runs)
# OR archived under an experiment (e.g. experiments/stress_test/scores/). We
# search all of these by <job>/<trial_id> so the viz finds a judgement wherever
# it was written. First hit wins.
DEFAULT_SCORES_DIR = _V2 / "scores"
_SEARCH_ROOTS = [_V2 / "scores"] + sorted((_V2 / "experiments").glob("*/scores")) \
    if (_V2 / "experiments").exists() else [_V2 / "scores"]

# Pull explicit step-ids out of an evidence `steps` string: bare ints and int
# ranges ("13-16" -> 13,14,15,16). Anything else ("all", "patch lines 611-628")
# is intentionally ignored — we tag only what maps cleanly to a step_id.
_RANGE_RE = re.compile(r"\b(\d+)\s*-\s*(\d+)\b")
_INT_RE = re.compile(r"\b(\d+)\b")
# Guard against absurd ranges from mis-parses (e.g. "patch lines 611-628" once
# the "patch lines" prefix is stripped would over-tag) — cap span length.
_MAX_RANGE_SPAN = 40


def _parse_steps(text: str, max_step: int) -> set[int]:
    """Extract integer step-ids referenced by one evidence string."""
    if not text:
        return set()
    out: set[int] = set()
    consumed = []
    for m in _RANGE_RE.finditer(text):
        a, b = int(m.group(1)), int(m.group(2))
        if a <= b and (b - a) <= _MAX_RANGE_SPAN:
            out.update(range(a, b + 1))
        consumed.append((m.start(), m.end()))
    # bare ints outside any consumed range span
    for m in _INT_RE.finditer(text):
        if any(s <= m.start() < e for s, e in consumed):
            continue
        out.add(int(m.group(1)))
    # keep only ids that actually exist in the trajectory
    return {i for i in out if 1 <= i <= max_step}


@dataclass
class DimView:
    """One rubric dimension's verdict, shaped for display."""

    id: str
    name: str
    spine: bool
    importance: int
    weight: float
    target_level: int | None
    observed_level: int | None
    gap: float | None
    confidence: str | None
    reasoning: str
    evidence: list[dict]           # [{steps, note}, ...] verbatim
    step_ids: set[int] = field(default_factory=set)   # parsed, existing step-ids

    @property
    def gap_class(self) -> str:
        """Color band by gap: near-zero good, moderate warn, large deficit bad."""
        if self.gap is None:
            return ""
        if self.gap >= -1:
            return "good"
        if self.gap >= -3:
            return "mid"
        return "low"

    @property
    def observed_pct(self) -> float:
        return 10 * (self.observed_level or 0)

    @property
    def target_pct(self) -> float:
        return 10 * (self.target_level or 0)


@dataclass
class Judgement:
    """A trial's full meta-work judgement, shaped for the template."""

    overall_gap: float | None
    overall_observed: float | None
    task_specific_gap: float | None
    dimensions: list[DimView]
    task_read: str
    errors: list[str] = field(default_factory=list)
    # step_id -> [dimension names citing it], for inline step tagging
    step_tags: dict[int, list[str]] = field(default_factory=dict)

    @property
    def overall_gap_class(self) -> str:
        if self.overall_gap is None:
            return ""
        if self.overall_gap >= -1:
            return "good"
        if self.overall_gap >= -2.5:
            return "mid"
        return "low"


def _score_path(key: str, scores_dir: Path | str) -> Path:
    """Resolve a trial's score.json by "job/trial_id".

    If `scores_dir` is the default, search every known root (canonical scores/
    + each experiments/*/scores) and return the first that exists. An explicit
    non-default `scores_dir` is used verbatim (tests / custom locations).
    """
    job, _, trial_id = key.partition("/")
    rel = Path(job) / trial_id / "score.json"
    roots = _SEARCH_ROOTS if Path(scores_dir) == DEFAULT_SCORES_DIR else [Path(scores_dir)]
    for root in roots:
        cand = root / rel
        if cand.is_file():
            return cand
    return Path(scores_dir) / rel   # canonical (nonexistent) — caller checks is_file()


def load_judgement(key: str, max_step: int,
                   scores_dir: Path | str = DEFAULT_SCORES_DIR) -> Judgement | None:
    """Load the judgement for one trial by "job/trial_id". None if unscored.

    `max_step` (the trajectory's step count) bounds evidence step-id parsing so
    we never tag a non-existent step.
    """
    p = _score_path(key, scores_dir)
    if not p.is_file():
        return None
    try:
        d = json.loads(p.read_text())
    except Exception:
        return None

    rubric = d.get("rubric") or {}
    dims: list[DimView] = []
    step_tags: dict[int, list[str]] = {}
    for dim in d.get("dimensions", []):
        evidence = dim.get("evidence") or []
        step_ids: set[int] = set()
        for e in evidence:
            step_ids |= _parse_steps(str(e.get("steps", "")), max_step)
        dv = DimView(
            id=dim.get("id"), name=dim.get("name") or dim.get("id"),
            spine=bool(dim.get("spine")), importance=dim.get("importance") or 0,
            weight=dim.get("weight") or 0.0,
            target_level=dim.get("target_level"), observed_level=dim.get("observed_level"),
            gap=dim.get("gap"), confidence=dim.get("confidence"),
            reasoning=dim.get("reasoning") or "", evidence=evidence, step_ids=step_ids,
        )
        dims.append(dv)
        for sid in step_ids:
            step_tags.setdefault(sid, []).append(dv.name)

    # spine first (fixed, comparable), then task-specific extras
    dims.sort(key=lambda x: (not x.spine, x.id))
    return Judgement(
        overall_gap=d.get("overall_gap"),
        overall_observed=d.get("overall_observed"),
        task_specific_gap=d.get("task_specific_gap"),
        dimensions=dims,
        task_read=rubric.get("task_read") or "",
        errors=d.get("errors") or [],
        step_tags=step_tags,
    )


def overall_gap_for(key: str, scores_dir: Path | str = DEFAULT_SCORES_DIR) -> float | None:
    """Cheap read of just overall_gap (for gallery cards). None if unscored."""
    p = _score_path(key, scores_dir)
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text()).get("overall_gap")
    except Exception:
        return None
