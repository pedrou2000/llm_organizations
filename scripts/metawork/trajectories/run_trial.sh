#!/usr/bin/env bash
# Run one SWE-Marathon Harbor trial for the meta-work experiment (Pipeline A).
# Uses Codex's NATIVE amazon-bedrock provider (deep fix): the agent resolves
# the `openai.gpt-5.5` alias natively (correct metadata), auths with the
# Bedrock API key, and talks the Mantle Responses API — no foreign-alias miss.
#
# Wrapped so it can be launched under `sg docker -c` to inherit docker-group
# socket access.
#
# Usage:
#   run_trial.sh JOB_NAME [--task excel-clone] [--model openai/openai.gpt-5.5] [extra harbor flags...]
#     --task   task under vendor/swe-marathon/tasks/ (default: excel-clone)
#     --model  agent model alias passed to `harbor --model` (default: openai/openai.gpt-5.5)
#   Env: HARBOR_AGENT=oracle runs the reference-solution agent (no model) as a
#        pipeline sanity check.
set -euo pipefail

export PATH="$HOME/.local/bin:$PATH"
cd /home/ubuntu/workplace/llm_organizations

JOB_NAME="${1:?usage: run_trial.sh JOB_NAME [--task T] [--model M] [extra flags...]}"
shift || true

# Parameterized task + model (defaults reproduce the GPT-5.5 × excel-clone setup).
TASK="excel-clone"
MODEL="openai/openai.gpt-5.5"
EXTRA=()
while [ $# -gt 0 ]; do
  case "$1" in
    --task)  TASK="$2";  shift 2 ;;
    --model) MODEL="$2"; shift 2 ;;
    *)       EXTRA+=("$1"); shift ;;
  esac
done

TASK_PATH="vendor/swe-marathon/tasks/${TASK}"
[ -d "$TASK_PATH" ] || { echo "run_trial.sh: no such task dir: $TASK_PATH" >&2; exit 2; }

# Agent is overridable so we can run the `oracle` agent (reference solution,
# no model) as a pipeline sanity check. Defaults reproduce the GPT-5.5 setup.
AGENT="${HARBOR_AGENT:-codex}"

# Codex needs --model + the native bedrock provider region; oracle needs
# neither (it just runs the task's solution/solve.sh).
MODEL_ARGS=()
if [ "$AGENT" = "codex" ]; then
  MODEL_ARGS=(--model "$MODEL" --ae CODEX_BEDROCK_REGION=us-east-2)
fi

# SECRET HYGIENE: pass the token as a LITERAL '${VAR}' reference, NOT the
# expanded value. Harbor persists --ae args verbatim into config.json; if the
# shell expands the token first, the live Bedrock key lands in a file (and
# potentially git). Single-quoting keeps it a reference that Harbor expands at
# runtime — config.json then stores '${AWS_BEARER_TOKEN_BEDROCK}', never the key.
# (The ux/CUA Bedrock judge reads this token; codex also uses it to build.)
harbor run \
  -p "$TASK_PATH" \
  --agent "$AGENT" \
  "${MODEL_ARGS[@]}" \
  --ae 'AWS_BEARER_TOKEN_BEDROCK=${AWS_BEARER_TOKEN_BEDROCK}' \
  --jobs-dir results/metawork/trajectories/harbor \
  --job-name "$JOB_NAME" \
  -y "${EXTRA[@]}"
