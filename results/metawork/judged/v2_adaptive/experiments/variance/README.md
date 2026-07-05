# Variance experiment — how reliable is the v2 judge?

**Question.** The judge has two stochastic stages that compound: Stage A
synthesizes a task rubric, Stage B agentically scores the trajectory against it.
If we hand the judge the *same* trajectory repeatedly, how much does the score
wobble — and which stage causes it?

**Design (nested random-effects).** Hold a trajectory fixed. Synthesize
**M = 10** rubrics; score the trajectory **K = 10** times against each *pinned*
rubric → 100 scorings/trajectory. Repeat on **2 trajectories** spanning the
meta-work range (a "clean" high-metawork excel-clone trial, `UGtpajG`; a "messy"
low one, `BzF8Tsg`) → **200 scorings total**. Both are excel-clone, so the
rubric distribution is identical and rubric variance is cleanly isolated.

Variance is decomposed per metric (one-way random-effects estimator):
- **σ_scoring** = within-rubric SD across the K rescorings — pure Stage-B agentic noise.
- **σ_rubric** = between-rubric SD of the per-rubric means — the *ruler* moving.
- **σ_total** = SD across all M·K — what a caller of `judge_metawork` actually sees.

Acceptance bar (set up front): overall_gap SD **< 0.5** → a ±1.0 gap difference
between two agents is real signal, not noise.

## Results (M=10, K=10, 200 scorings, $292, 0 errors)

| metric | σ_total | σ_scoring | σ_rubric |
|---|---|---|---|
| overall_gap (clean) | 0.54 | 0.20 | **0.52** |
| overall_gap (messy) | 0.58 | 0.17 | **0.58** |

- **The ruler wobbles ~3× more than the reader.** Stage-B scoring is tight
  (σ ≈ 0.17–0.20); the instability is Stage-A rubric synthesis picking a slightly
  different bar each run. So `overall_gap` sits at SD ≈ 0.55 — just over the bar.
- **The pin works (mechanism check).** With a rubric pinned, `target_level` has
  *zero* within-rubric variance (see plot 2) — all scoring noise lives in
  `observed_level`. Fresh synthesis moves targets by SD ≈ 0.3–0.5, which is what
  injects noise into every gap.

## Interpretation

Fine per-trajectory rankings within ~1 gap point are inside the noise band; the
directional finding (gaps of −1 to −4.7, i.e. under-investment) is far outside
it and safe. The cheap hardening — **pin one rubric per task** — removes σ_rubric
entirely (that's exactly what the published_grid experiment does for its
cross-model comparisons), dropping the headline SD to ~0.20.

## Reproduce

```bash
# score (writes data/): ~$292, ~1.7h
python scripts/metawork/judge/v2_adaptive/experiments/variance/measure_variance.py --rubrics 10 --scorings 10
# recompute decomposition from the saved raw parquet, no LLM calls
python scripts/metawork/judge/v2_adaptive/experiments/variance/measure_variance.py --analyze-only
# plots (writes plots/)
python scripts/metawork/judge/v2_adaptive/experiments/variance/plot_variance.py --rubrics 10 --scorings 10
```

## Files
- `data/variance_raw__M10_K10.parquet` — every scoring (200 rows).
- `data/variance_decomposition__M10_K10.parquet` — the σ split per metric.
- `data/rubrics__M10.json` — the 10 synthesized rubrics.
- `plots/1_decomposition.png` — σ_scoring vs σ_rubric per dimension.
- `plots/2_target_vs_observed.png` — the pin mechanism (target σ_scoring ≈ 0).
- `plots/3_acceptance.png` — total SD per metric vs the 0.5 bar.
- (`__M2_K2` files are a cheap validation run — ignore for results.)
