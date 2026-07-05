# v2 adaptive judge — experiments

Each subfolder is one self-contained experiment: a `README.md` (what/why/how +
results), its `plots/`, and its data (parquets, per-trajectory `scores/` trees).

| experiment | question | headline |
|---|---|---|
| [variance/](variance/) | How reliable is the judge? (run-to-run noise, decomposed) | overall_gap SD ≈ 0.55; **rubric synthesis** is the dominant noise source (~3× scoring) |
| [published_grid/](published_grid/) | Do agents under-invest in meta-work, across models & tasks? | **96%** of trajectories under-invest (gap<0); universal across 9 models; verification is the worst dimension |
| [stress_test/](stress_test/) | Does the pipeline hold under load? (operational, not analytic) | 4-way parallel + a first e2e run; 0 errors |

The judge produces a **signed gap** = observed − task-appropriate level, on a
0–10 scale: **0 = calibrated, negative = under-investment, positive =
over-investment/ceremony**. Five fixed "spine" dimensions (orientation,
decomposition, verification, progress-monitoring, adaptation) are comparable
across every task; task-specific "extras" roll into `task_specific_gap`.

Scripts live in the mirror path
`scripts/metawork/judge/v2_adaptive/experiments/<name>/`.
