# llm-organizations

Research code for studying **meta-work bias** in LLM coding agents: the tendency
to under-invest in planning, decomposition, and self-verification on long-horizon
tasks, and whether a content-free "meta-work nudge" can correct it.

The repo holds **two research lines**, kept structurally separate:

- **`metawork/`** — the SWE-Marathon meta-work experiment (the current focus, milestones M1–M6). Runs GPT-5.5 on SWE-Marathon tasks via a local [Harbor](https://github.com/RishiDesai/harbor) harness, then scores each trajectory's *planning quality* with a blind LLM judge.
- **`closure/`** — the math compulsion-to-closure probe. Sweeps models on Omni-MATH / MATH under verify/forced/neutral/anti conditions to measure self-verification behaviour.

Both share generic infrastructure in **`common/`**.

## Layout

```
src/
├── common/      shared infra: models (Bedrock IDs), trace logging, concurrency runner
├── closure/     math probe: math_judge, sweep, data/, probes/, analysis/
└── metawork/    SWE-Marathon experiment, split by trajectory source:
    ├── judge/       the durable blind judge (+ prompt.md) — both sources feed it
    ├── harbor/      Source B: our own Harbor runs (source.py, judge_job.py) — M4+
    └── published/   Source A: published-website corpus (harvest.py, judge_corpus.py)

scripts/
├── closure/     run_substrate.py, run_sweep.py, analyze.py
└── metawork/    run_trial.sh, judge_trajectories.py, plot.py
    └── published/   harvest.py, explore.py, judge.py  (published-website corpus)

results/
├── closure/     sweep/, substrate/, traces/ (gitignored), plots/
└── metawork/    judged/, harvest/, logs/, plots/,
                 trajectories/ + harbor_jobs/ (both gitignored — large)

vendor/           upstream clones of harbor + swe-marathon (gitignored, ~8 GB)
vendor-patches/   our diffs against them + apply instructions
papers/           reference papers (SWE-Marathon etc.)
notebooks/        exploratory notebooks
```

## Setup

Requires Python ≥ 3.12 and [`uv`](https://docs.astral.sh/uv/). Docker is needed
only to *run* Harbor trials (not to judge existing ones).

```bash
# 1. Python env + this package (editable)
uv sync

# 2. Bedrock auth (all model calls route through Bedrock — agent under test,
#    CUA verifier, and the meta-work judge)
export AWS_BEARER_TOKEN_BEDROCK=...      # mantle bearer token
export CLAUDE_CODE_USE_BEDROCK=1
export AWS_REGION=us-east-1
```

### Harbor harness (only for generating new metawork trajectories)

Harbor and the SWE-Marathon tasks are vendored under `vendor/` (gitignored).
Clone them at the pinned commits and apply our patches:

```bash
# clone the two upstreams into vendor/, then:
cd vendor/swe-marathon && git checkout 41f118a && git apply ../../vendor-patches/swe-marathon__cua-bedrock-route.patch && cd ../..
cd vendor/harbor       && git checkout 578713b && git apply ../../vendor-patches/harbor__codex-bedrock-provider.patch && git apply ../../vendor-patches/harbor__cua-stage-app-boot.patch && cd ../..

# install harbor editable WITH the CUA-stage judge deps (see vendor-patches/README.md for why)
uv tool install --editable ./vendor/harbor --force --with anthropic --with boto3
```

See [`vendor-patches/README.md`](vendor-patches/README.md) for what each patch fixes
and the exact upstream commit pins.

## Running

### Metawork (current line)

```bash
# Generate a Harbor trial (GPT-5.5 × excel-clone). Needs Docker + the harness above.
# Wrap in `sg docker -c "..."` if your shell predates docker-group membership.
scripts/metawork/trajectories/run_trial.sh my_job_name

# Score our own trajectories with the blind meta-work judge (Source B — durable path)
python scripts/metawork/judge/v1_fixed/judge_harbor.py --job my_job_name --judge-model opus-4.8
#   --task excel-clone     filter to one task
#   --parity               published-parity flattening (drop prose) for head-to-head
#   --limit N              cheap probe over first N trajectories (writes a _limitN parquet)

# Plots for the observational study
python scripts/metawork/judge/v1_fixed/plot.py
```

The judge is **blind** (sees only the flattened trajectory text, never the model
identity or outcome) and outcome metadata is joined back *after* judging, so the
meta-work score can't be contaminated by the result. Output:
`results/metawork/judged/`.

### Closure (math probe)

```bash
python scripts/closure/run_substrate.py --model haiku-4.5 --dataset omni-math   # no-tools sanity check
python scripts/closure/run_sweep.py     --model opus-4.8  --dataset omni-math   # full probe sweep
python scripts/closure/analyze.py        --dataset omni-math                    # summaries + plots
```

## Reproducing M1–M3

- **M1/M2** — stand up Harbor and reproduce the published GPT-5.5 × excel-clone
  `partial` score (`0.5·correctness + 0.5·ux`). The six fixes that make the local
  Bedrock route match the published numbers are captured in `vendor-patches/`.
- **M3** — score our own trajectories with the meta-work judge; under a matched
  judge and matched flattening, ours lands on the published number.

> **Scoring gotchas** (easy to misread the raw files): `correctness` is the
> *fractional* `partial_score` (gates passed / 18), **not** the binary
> `stage:correctness` in `reward.json` (always 0 for GPT-5.5). And the `keep_prose`
> flattening toggle shifts the meta-work score by ~1.2 points — full-fidelity is
> the honest view of our runs; parity is only for head-to-head vs published.
