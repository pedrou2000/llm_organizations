#!/usr/bin/env bash
# Full meta-work pipeline, end to end: GENERATE a Harbor trajectory (Pipeline A)
# then SCORE it with the v2 task-adaptive meta-work judge (Pipeline B).
#
#   (model, task) --run_trial.sh--> trajectory --score_trajectories.py--> MetaworkScore
#
# This is the capstone that composes the two halves; each can still be run alone
# (trajectories/run_trial.sh, judge/v2_adaptive/score_trajectories.py).
#
# Usage:
#   run_and_judge.sh JOB_NAME [--task excel-clone] [--model openai/openai.gpt-5.5]
#                             [--score-model opus-4.8] [--rubric-model opus-4.8]
#                             [--limit N]
#
# Generation needs Docker; wrap the whole call in `sg docker -c "..."` if your
# shell predates docker-group membership. Scoring needs the Bedrock judge creds
# (AWS_BEARER_TOKEN_BEDROCK), same as the standalone scorer.
set -euo pipefail

export PATH="$HOME/.local/bin:$PATH"
cd /home/ubuntu/workplace/llm_organizations

JOB_NAME="${1:?usage: run_and_judge.sh JOB_NAME [--task T] [--model M] [--score-model M] [--rubric-model M] [--limit N]}"
shift || true

TASK="excel-clone"
MODEL="openai/openai.gpt-5.5"
SCORE_ARGS=()
while [ $# -gt 0 ]; do
  case "$1" in
    --task)         TASK="$2"; SCORE_ARGS+=(--task "$2"); shift 2 ;;
    --model)        MODEL="$2"; shift 2 ;;
    --score-model)  SCORE_ARGS+=(--score-model "$2"); shift 2 ;;
    --rubric-model) SCORE_ARGS+=(--rubric-model "$2"); shift 2 ;;
    --limit)        SCORE_ARGS+=(--limit "$2"); shift 2 ;;
    *)              SCORE_ARGS+=("$1"); shift ;;
  esac
done

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "==============================================================================="
echo "[A] GENERATE  job=$JOB_NAME  task=$TASK  model=$MODEL"
echo "==============================================================================="
bash "$HERE/trajectories/run_trial.sh" "$JOB_NAME" --task "$TASK" --model "$MODEL"

echo
echo "==============================================================================="
echo "[B] SCORE     job=$JOB_NAME  (v2 task-adaptive meta-work judge)"
echo "==============================================================================="
python "$HERE/judge/v2_adaptive/score_trajectories.py" --job "$JOB_NAME" "${SCORE_ARGS[@]}"

echo
echo "done: $JOB_NAME  ->  results/metawork/judged/v2_adaptive/scored_${JOB_NAME}__*.parquet"
