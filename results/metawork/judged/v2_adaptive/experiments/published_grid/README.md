# Published grid — do agents under-invest in meta-work?

**Question.** Across many models and tasks, do coding agents systematically
under-invest in meta-work (negative gap)? And does the gap↔outcome link survive
controlling for task difficulty and model capability?

**Design.** The balanced model×task grid from the published SWE-Marathon harvest:
**9 models × 20 tasks × 1 trajectory each = 180 cells**. One rubric is
synthesized **per task** and reused across all 9 models, so every model on a task
is judged against an *identical ruler* — this removes rubric variance (the
dominant noise source, see [variance/](../variance/)) from all cross-model
comparisons.

**⚠️ Fidelity caveat.** The published corpus provides only flattened `flat_text`
(no raw trajectory JSON), and the harvest kept far more agent prose for some
models than others (~8× more for DeepSeek than GPT-5.5). Since the judge audits
*reasoning*, **cross-model** comparisons (plots 1 & 3) partly reflect harvest
fidelity, not just meta-work. **Within-task / within-model** views (plots 4, 5)
are unaffected. The clean fix is to score our *own* full-fidelity trajectories.

## Results (179/180 cells; 1 cell hung on a stuck SDK call and was dropped; $227, 0 errors)

- **Under-investment is near-universal.** Mean overall_gap **−2.78**; **96%** of
  trajectories have gap < 0, **82%** below −1.
- **Holds across all 9 models**, graded by capability (mean gap):
  Opus 4.8 −1.15 · Opus 4.7 −1.66 · DeepSeek −2.32 · GPT-5.5 −2.72 ·
  Gemini 3.5F −2.93 · Gemini 3.1 −3.19 · GLM 5.1 −3.23 · Kimi −3.67 · MiniMax −4.22.
  Stronger models are closer to calibrated but none reaches it.
- **Verification is the worst dimension** (mean gap −3.68), then decomposition
  (−2.81), progress-monitoring (−2.69), adaptation (−2.57), orientation (−2.35).
- **The gap↔outcome link survives controls:** pooled +0.47, within-task +0.47
  (difficulty is *not* the confound), within-model +0.37. (Within-(task,model)
  is undefined here — n=1 per cell.)

## Reproduce

```bash
# score the grid (writes scored_*.parquet + scores/): ~$180, ~1.5h
python scripts/metawork/judge/v2_adaptive/experiments/published_grid/score_published.py --tag grid
# plots (writes plots/)
python scripts/metawork/judge/v2_adaptive/experiments/published_grid/plot_published.py --tag grid
```

## Files
- `scored_published_grid__opus-4.8.parquet` — one row per cell (179): outcome
  metadata + overall/spine/task-specific gaps.
- `scores/<id>/` — per-trajectory inspection trees (rubric, per-dim prompts +
  verdicts with cited evidence).
- `plots/1_confound_ladder.png` — corr(gap, outcome) under nested controls. *[cross-model caveat]*
- `plots/2_gap_vs_partial.png` — scatter, coloured by model.
- `plots/3_model_disposition.png` — per-model gap distribution + under-investment share. *[cross-model caveat]*
- `plots/4_per_task_corr.png` — within-task gap↔outcome correlation.
- `plots/5_dimension_profile.png` — mean gap per spine dimension (where the deficit lives).
