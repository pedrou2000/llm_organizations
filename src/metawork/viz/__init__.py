"""Trajectory visualizer for meta-work exploration.

A local web app to browse the Harbor agent trajectories we generate: a gallery
of all trials, and a rich per-trajectory page (stats header + navigable,
searchable, collapsible steps). Full-fidelity and human-facing — the opposite of
the blind judge flattener in `metawork.harbor.source`.

    loader  — discover trials, parse trajectory.json (all steps, real names),
              join outcome scores from the verifier files, detect termination.
    actions — single source of truth for agent-action semantics: the kind
              vocabulary + colors, tool→kind map, per-step summaries. Extend
              here to support a new agent/tool.
    stats   — typed per-trajectory summary (TrajectorySummary) + per-step view
              (StepView): effort/tokens, action histogram, meta-work signals.
    format  — display formatting (the one place raw values become strings).
    server  — FastAPI app (routing only: gallery + detail pages).

Launch: python scripts/metawork/viz.py [--port 8010]
"""
