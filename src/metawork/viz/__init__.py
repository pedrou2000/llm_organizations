"""Trajectory visualizer for meta-work exploration.

A local web app to browse the Harbor agent trajectories we generate: a gallery
of all trials, and a rich per-trajectory page (stats header + navigable,
searchable, collapsible steps). Full-fidelity and human-facing — the opposite of
the blind judge flattener in `metawork.harbor.source`.

    loader  — discover trials, parse trajectory.json (all steps, real names),
              join outcome scores from the verifier files.
    stats   — per-trajectory summary: effort/tokens, action histogram,
              meta-work signals, outcome scores.
    server  — FastAPI app (gallery + detail pages).

Launch: python scripts/metawork/viz.py [--port 8010]
"""
