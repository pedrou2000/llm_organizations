# Stress test — pipeline validation (operational, not analytic)

**Purpose.** Not a research finding — these are the runs that validated the
end-to-end pipeline (generate → v2 score) under load, before the real
experiments. Kept for provenance and because two of the trajectories here are
the fixed inputs used by the [variance/](../variance/) experiment.

## What's here

- **`scored_e2e_707e0f2_run1__opus-4.8.parquet`** — the first full end-to-end run
  (`run_and_judge.sh`): generate one excel-clone trajectory with GPT-5.5, then
  score it. Validated the composed A→B pipeline (gap −3.38, 0 errors).
- **`scored_par4_5f99aa9_r{1..4}__opus-4.8.parquet`** — 4 concurrent
  `run_and_judge` jobs launched together to stress the harness (24 peak
  concurrent opus dimension-judges). **All 4 completed, 0 errors, no
  rate-limiting** — the pipeline holds at 4-way parallelism.
- **`scores/<job>/<trial>/`** — the inspection trees for all 5 trajectories.
  These are the trees the trajectory visualizer reads (`viz.judgement` searches
  `scores/` and every `experiments/*/scores/`), so the harbor trajectories still
  show their meta-work judgements in the app after this reorg.

## Note

These are single trajectories per job (harbor default), so there's no aggregate
plot — the analytic findings live in [published_grid/](../published_grid/) and
[variance/](../variance/). The par4 gaps span −1.44 to −2.52, but those are 4
*different* trajectories, so that spread mixes generation and judge variance
(which the variance experiment disentangles on fixed inputs).
