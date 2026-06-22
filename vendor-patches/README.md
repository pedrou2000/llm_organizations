# Patches to vendored repos

`vendor/harbor/` and `vendor/swe-marathon/` are upstream clones (their own
git, gitignored from this repo). We made small local edits to stand up the
GPT-5.5 × excel-clone meta-work experiment. Those edits are captured here as
`git apply`-able diffs so a fresh checkout can reconstruct the working setup
without vendoring 287 MB of upstream code.

## How to apply

```bash
# from repo root, after cloning the two upstream repos into vendor/
cd vendor/swe-marathon && git checkout 41f118a && git apply ../../vendor-patches/swe-marathon__cua-bedrock-route.patch && cd ../..
cd vendor/harbor       && git checkout 578713b && git apply ../../vendor-patches/harbor__codex-bedrock-provider.patch && git apply ../../vendor-patches/harbor__cua-stage-app-boot.patch && cd ../..
# then reinstall harbor editable WITH the CUA-stage judge deps:
uv tool install --editable ./vendor/harbor --force --with anthropic --with boto3
```

### Why `--with anthropic --with boto3`
The excel-clone `ux` stage is a CUA verifier. Its Computer1 vision agent talks
to Claude via the `anthropic` SDK (`AnthropicBedrock`), and its per-criterion
LLM judge routes `bedrock/...` through `litellm -> boto3`. Neither package is a
declared harbor dependency, so a vanilla `uv tool install` leaves the tool venv
without them — the vision agent fails to import `anthropic`, and (less obvious)
the judge fails every criterion with `litellm.APIConnectionError: No module
named 'boto3'`, zeroing the `ux` stage even when the app and CUA run fine. Both
must be injected into the tool venv with `--with`.

## The patches

### `harbor__codex-bedrock-provider.patch`
Applies to `RishiDesai/harbor` @ `578713b`. Despite the name, this patch now
carries TWO independent harbor edits (both needed for the GPT-5.5 × excel-clone
2-stage trial):

**(1) `src/harbor/agents/installed/codex.py` — native amazon-bedrock provider.**
When `CODEX_BEDROCK_REGION` is set, the Codex agent writes Codex's built-in
**`amazon-bedrock`** provider block to `config.toml` instead of the generic
`OPENAI_BASE_URL` hack. This resolves the `openai.gpt-5.5` alias natively
(correct metadata / 1.05M context window), auths with the
`AWS_BEARER_TOKEN_BEDROCK` Bedrock API key, and talks the Mantle Responses API
directly — eliminating the cost-null, "metadata not found", WebSocket-405, and
model-404 errors that the foreign-alias lookup miss produced. The generic
`OPENAI_BASE_URL` path is preserved as a fallback.

**(2) `src/harbor/agents/computer_1/providers/anthropic.py` — Bedrock CUA image
trim.** The CUA (ux stage) appends one screenshot per turn and never trims, so
by ~turn 100 the request carries ~100 images (~155–170K tokens / ~2MB). The
DIRECT Anthropic API (what published runs used) tolerates this; our BEDROCK
substitution rejects it with an opaque `503 "Bedrock is unable to process your
request."` at the identical turn every run (verified by probe: OK at 100 images,
503 at 110 — below the nominal 200K window). Fix: `BEDROCK_IMAGE_WINDOW = 12` +
`_trim_image_history()` keep only the last 12 image-turns at send time (older
images → a text placeholder), **bedrock route only** — direct-API path and
`self._messages` (trajectory) untouched. Validated: oracle ux went from a
turn-101 crash (ux=0) to a full-rubric **ux=1.0**, with the two cross-screenshot
criteria (`error_feedback`, `realism`) still passing → no grade regression. If a
future task needs more than 12 back-to-back comparison shots, raise the window.

### `harbor__cua-stage-app-boot.patch`
Applies to `RishiDesai/harbor` @ `578713b`, file
`src/harbor/verifier/multi_stage.py`.

**harbor-vs-oddish parity fix: boot the agent's app before the CUA stage.**
In SHARED verifier mode (excel-clone's default), the `correctness` shell stage's
`tests/test.sh` boots `/app/start.sh` under its own PID and `kill`s it on its
EXIT trap. With a foreground `exec uvicorn` start.sh (what GPT-5.5 — and most
published agents — ship), uvicorn inherits that PID and dies when correctness
exits. harbor's `MultiStageVerifier` never re-boots the app and `CuaVerifier`
only navigates to `start_url`, so the CUA hit a dead `:8000` →
`ERR_CONNECTION_REFUSED` → **ux=0** on every foreground-server trial. The
published numbers came from `oddish run --env modal`, which evidently boots the
app for the CUA stage; this patch mirrors that for local harbor.

`MultiStageVerifier._run_one_stage` now calls `_ensure_app_booted_for_cua()`
before any CUA stage: if the SPA root (`cua.start_url`) isn't already answering,
it launches `/app/start.sh` in its own session (`setsid …  < /dev/null &` —
survives the verifier's process group) and polls the root URL up to 120s. It's
idempotent (skips the boot when the app is already up, e.g. a `setsid`-detached
start.sh) and best-effort (a boot failure is logged, never blocks the stage —
the CUA still runs). Polls the SPA root, not a task-specific health path, so it
stays generic across the CUA-task family (excel-clone, s3-clone, slack-clone).
Runner-side only — touches no task content.

Validated 2026-06-21 (controlled before/after on the same local harbor):
- **GPT-5.5 ×3, foreground `exec uvicorn` start.sh** (0 detach markers, boot
  fired — `ux-server.log` written): **ux 0 → {0.515, 0.485, 0.338}**, no
  `ERR_CONNECTION_REFUSED` hits, squarely in the published GPT-5.5 band
  (0.04–0.59, mean ~0.30). Prior unpatched batch: 8/8 trials ux=0.0.
- **oracle, `setsid` start.sh** (idempotent skip path, app already serving):
  **ux=1.0**, unchanged → no regression.

### `swe-marathon__cua-bedrock-route.patch`
Applies to `abundant-ai/swe-marathon` @ `41f118a`. Touches the `task.toml` of
**all four CUA-stage tasks**: `excel-clone`, `s3-clone`, `slack-clone`,
`mastodon-clone`.

For each, routes the CUA/UX verifier's Claude vision model + LLM judge through
Bedrock (`model = "bedrock/us.anthropic.claude-opus-4-7"`) instead of the direct
Anthropic API (`anthropic/claude-opus-4-7`), and swaps the `[verifiers.env]`
declaration from `ANTHROPIC_API_KEY` to the Bedrock vars
(`AWS_BEARER_TOKEN_BEDROCK`, `AWS_REGION=us-east-2`). We have no raw
`ANTHROPIC_API_KEY`; Computer1 routes `bedrock/` via its `AnthropicBedrock`
client, which auths with the bearer token. Same underlying model (Opus 4.7),
just the Bedrock route. `[verifiers.env]` must declare ONLY host-present vars —
harbor's `resolve_env_vars` throws on a missing one, so leaving
`ANTHROPIC_API_KEY` declared crashed the ux stage at config-resolution time.

(Supersedes the old excel-clone-only `swe-marathon__excel-clone-cua-model.patch`,
now removed — the excel-clone hunk here is byte-identical to it.)

**NOT converted — `post-train-ifeval`.** It also reads `ANTHROPIC_API_KEY` for a
Claude reward-hacking judge, but that judge uses the `claude_agent_sdk` (Claude
Code SDK), not Computer1's `AnthropicBedrock` — its `judge.py` even comments that
"the previous Bedrock path shipped an invalid [model id]". A Bedrock route there
needs SDK-level env wiring (`CLAUDE_CODE_USE_BEDROCK=1` + a valid inference
profile), not a one-line task.toml edit, and the task needs Tinker LoRA
fine-tuning infra we don't have locally — so it's left on the Anthropic route and
is not runnable here regardless.

## Upstream pins
- swe-marathon: `41f118a963f77a1bce63cec0d0f99d05d8a0604f`
- harbor:       `578713b40aa1ea6e8fabdc7f4c7a5e20204e3b55`
