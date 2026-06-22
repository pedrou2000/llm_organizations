"""Shared, experiment-agnostic infrastructure.

Used by both research lines (the `closure` math compulsion-to-closure probe and
the `metawork` SWE-Marathon experiment):
    models       — Bedrock model IDs + label<->id lookup
    trace        — per-trial markdown trace logging + duration formatting
    concurrency  — bounded-concurrency async runner with progress/cost reporting
"""
