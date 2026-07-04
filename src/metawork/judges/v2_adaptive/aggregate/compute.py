"""Pure aggregation: Rubric + per-dimension Verdicts -> MetaworkScore.

No LLM, no IO. The measure:
  - per-dimension signed gap = observed_level - target_level
  - weights = importance normalized across all dimensions (sum to 1)
  - overall_gap / overall_observed = importance-weighted averages over all dims
  - task_specific_gap = importance-weighted average over the EXTRA dims only
  - spine_gaps = each spine dimension's gap, reported individually (comparable
    across tasks)
Dimensions the scorer failed on (observed_level is None) are dropped from the
weighted averages and their weight mass is renormalized over the scored dims.
"""
from __future__ import annotations

from .types import DimensionScore, MetaworkScore, Rubric, Verdict


def _weighted_avg(pairs: list[tuple[float, float]]) -> float | None:
    """pairs of (value, weight); None if no weight."""
    tot_w = sum(w for _, w in pairs)
    if tot_w <= 0:
        return None
    return sum(v * w for v, w in pairs) / tot_w


def aggregate_scores(rubric: Rubric, verdicts: list[Verdict]) -> MetaworkScore:
    by_id = {v.dimension_id: v for v in verdicts}
    total_importance = sum(d.importance for d in rubric.dimensions) or 1

    dim_scores: list[DimensionScore] = []
    errors: list[str] = []
    total_cost = 0.0

    for dim in rubric.dimensions:
        v = by_id.get(dim.id)
        weight = dim.importance / total_importance
        observed = v.observed_level if v else None
        gap = (observed - dim.target_level) if observed is not None else None
        if v is not None:
            total_cost += v.cost_usd
            if v.error:
                errors.append(f"{dim.id}: {v.error}")
        else:
            errors.append(f"{dim.id}: no verdict")
        dim_scores.append(DimensionScore(
            id=dim.id, name=dim.name, spine=dim.spine,
            importance=dim.importance, weight=weight,
            target_level=dim.target_level, observed_level=observed, gap=gap,
            confidence=(v.confidence if v else None),
            evidence=(v.evidence if v else []),
            reasoning=(v.reasoning if v else ""),
        ))

    # Weighted scalars over the SCORED dimensions (importance as weight).
    scored = [ds for ds in dim_scores if ds.observed_level is not None]
    overall_gap = _weighted_avg([(ds.gap, ds.importance) for ds in scored])          # type: ignore[arg-type]
    overall_observed = _weighted_avg([(ds.observed_level, ds.importance) for ds in scored])  # type: ignore[arg-type]

    extras_scored = [ds for ds in scored if not ds.spine]
    task_specific_gap = _weighted_avg([(ds.gap, ds.importance) for ds in extras_scored])  # type: ignore[arg-type]

    spine_gaps = {ds.id: ds.gap for ds in dim_scores if ds.spine}

    return MetaworkScore(
        overall_gap=overall_gap,
        overall_observed=overall_observed,
        task_specific_gap=task_specific_gap,
        spine_gaps=spine_gaps,
        dimensions=dim_scores,
        rubric=rubric,
        cost_usd=total_cost,
        errors=errors,
    )
