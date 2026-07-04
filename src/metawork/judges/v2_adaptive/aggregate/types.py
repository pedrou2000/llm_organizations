"""Shared data shapes for the task-adaptive meta-work judge (v2).

These dataclasses are the contract between the three stages:
    rubric/   produces a Rubric (Stage A)
    score/    produces a Verdict per dimension (Stage B)
    aggregate/ combines Rubric + Verdicts into a MetaworkScore

Kept in the leaf package (no LLM, no IO) so every other module can depend on it
without cycles. All types carry `from_dict` / `to_dict` so they round-trip
through the JSON the LLM stages emit and the parquet/JSON we persist.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

# ---------- rubric (Stage A output) ----------


@dataclass
class Dimension:
    """One meta-work dimension of a task rubric: what to score, how important it
    is here, the appropriate level for this task, and the 0-10 anchor scale."""
    id: str
    name: str
    description: str
    why_it_matters: str
    importance: int          # 1-10, independent per dimension (normalized later)
    target_level: int        # 0-10, the calibration anchor (NOT shown to the scorer)
    anchors: dict[str, str]  # {"0":..., "3":..., "5":..., "8":..., "10":...}
    spine: bool              # True = one of the five universal faculties

    @classmethod
    def from_dict(cls, d: dict) -> "Dimension":
        return cls(
            id=d["id"],
            name=d.get("name", ""),
            description=d.get("description", ""),
            why_it_matters=d.get("why_it_matters", ""),
            importance=int(d["importance"]),
            target_level=int(d["target_level"]),
            anchors={str(k): str(v) for k, v in (d.get("anchors") or {}).items()},
            spine=bool(d.get("spine", False)),
        )


@dataclass
class Rubric:
    """A task-specific meta-work rubric (Stage A output)."""
    task_read: str
    dimensions: list[Dimension]

    @classmethod
    def from_dict(cls, d: dict) -> "Rubric":
        return cls(
            task_read=d.get("task_read", ""),
            dimensions=[Dimension.from_dict(x) for x in d.get("dimensions", [])],
        )

    def to_dict(self) -> dict:
        return {"task_read": self.task_read,
                "dimensions": [asdict(x) for x in self.dimensions]}

    @property
    def spine(self) -> list[Dimension]:
        return [x for x in self.dimensions if x.spine]

    @property
    def extras(self) -> list[Dimension]:
        return [x for x in self.dimensions if not x.spine]


# ---------- verdict (Stage B output, per dimension) ----------


@dataclass
class Verdict:
    """One dimension-judge's assessment of a trajectory."""
    dimension_id: str
    observed_level: int | None            # 0-10, or None if the judge failed
    confidence: str | None                # low | medium | high
    evidence: list[dict[str, str]]        # [{"steps": "...", "note": "..."}]
    reasoning: str
    cost_usd: float = 0.0
    turns_used: int | None = None
    error: str | None = None

    @classmethod
    def from_dict(cls, d: dict) -> "Verdict":
        lvl = d.get("observed_level")
        return cls(
            dimension_id=d.get("dimension_id", ""),
            observed_level=int(lvl) if isinstance(lvl, (int, float)) else None,
            confidence=d.get("confidence"),
            evidence=list(d.get("evidence") or []),
            reasoning=str(d.get("reasoning", "")),
            cost_usd=float(d.get("cost_usd", 0.0)),
            turns_used=d.get("turns_used"),
            error=d.get("error"),
        )


# ---------- score (aggregate output, per trajectory) ----------


@dataclass
class DimensionScore:
    """A dimension's rubric target + observed verdict + the resulting gap."""
    id: str
    name: str
    spine: bool
    importance: int
    weight: float                 # normalized importance across all dimensions
    target_level: int
    observed_level: int | None
    gap: float | None             # observed - target (None if not scored)
    confidence: str | None
    evidence: list[dict[str, str]]
    reasoning: str


@dataclass
class MetaworkScore:
    """The full result of judging one trajectory (the package's public return).

    Headline signed measure is `overall_gap`; `overall_observed` is the absolute
    view. `spine_gaps` are individually comparable across tasks;
    `task_specific_gap` rolls the extras into one comparable category.
    """
    overall_gap: float | None
    overall_observed: float | None
    task_specific_gap: float | None            # importance-weighted avg of extras' gaps
    spine_gaps: dict[str, float | None]        # {spine_id: gap}
    dimensions: list[DimensionScore]
    rubric: Rubric                             # the rubric used (reproducibility)
    cost_usd: float = 0.0
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["rubric"] = self.rubric.to_dict()
        return d

    def summary_row(self) -> dict[str, Any]:
        """Flat one-row view for a parquet table: scalars + per-dimension gaps."""
        row: dict[str, Any] = {
            "overall_gap": self.overall_gap,
            "overall_observed": self.overall_observed,
            "task_specific_gap": self.task_specific_gap,
            "cost_usd": self.cost_usd,
            "n_errors": len(self.errors),
        }
        for ds in self.dimensions:
            prefix = ds.id if ds.spine else f"extra__{ds.id}"
            row[f"{prefix}__observed"] = ds.observed_level
            row[f"{prefix}__target"] = ds.target_level
            row[f"{prefix}__gap"] = ds.gap
        return row
