#!/usr/bin/env bash
# Run one SWE-Marathon Harbor trial for the meta-work experiment.
# Uses Codex's NATIVE amazon-bedrock provider (deep fix): the agent resolves
# the `openai.gpt-5.5` alias natively (correct metadata), auths with the
# Bedrock API key, and talks the Mantle Responses API — no foreign-alias miss.
#
# Wrapped so it can be launched under `sg docker -c` to inherit docker-group
# socket access. Args: JOB_NAME [extra harbor flags...]
set -euo pipefail

export PATH="$HOME/.local/bin:$PATH"
cd /home/ubuntu/workplace/llm_organizations

JOB_NAME="${1:?usage: run_trial.sh JOB_NAME [extra flags...]}"
shift || true

# Agent is overridable so we can run the `oracle` agent (reference solution,
# no model) as a pipeline sanity check. Defaults reproduce the GPT-5.5 setup.
AGENT="${HARBOR_AGENT:-codex}"

# Codex needs --model + the native bedrock provider region; oracle needs
# neither (it just runs the task's solution/solve.sh).
MODEL_ARGS=()
if [ "$AGENT" = "codex" ]; then
  MODEL_ARGS=(--model openai/openai.gpt-5.5 --ae CODEX_BEDROCK_REGION=us-east-2)
fi

# SECRET HYGIENE: pass the token as a LITERAL '${VAR}' reference, NOT the
# expanded value. Harbor persists --ae args verbatim into config.json; if the
# shell expands the token first, the live Bedrock key lands in a file (and
# potentially git). Single-quoting keeps it a reference that Harbor expands at
# runtime — config.json then stores '${AWS_BEARER_TOKEN_BEDROCK}', never the key.
# (The ux/CUA Bedrock judge reads this token; codex also uses it to build.)
harbor run \
  -p vendor/swe-marathon/tasks/excel-clone \
  --agent "$AGENT" \
  "${MODEL_ARGS[@]}" \
  --ae 'AWS_BEARER_TOKEN_BEDROCK=${AWS_BEARER_TOKEN_BEDROCK}' \
  --jobs-dir results/metawork/harbor_jobs \
  --job-name "$JOB_NAME" \
  -y "$@"
