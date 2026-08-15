#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CONDITION="${1:-}"
if [[ -z "$CONDITION" ]]; then
  echo "usage: scripts/run_condition.sh {evolution|skill-only} [run_exp.py arguments]" >&2
  exit 2
fi
shift

case "$CONDITION" in
  skill-only)
    DEFAULT_AGENT="claude-code-skill-only"
    DEFAULT_MODEL="anthropic/claude-opus-4-6"
    DEFAULT_MAX_PARALLEL="10"
    DEFAULT_TIMEOUT="7200"
    DEFAULT_TIMEOUT_MULTIPLIER="1"
    ;;
  evolution)
    DEFAULT_AGENT="terminus-2-evolution"
    DEFAULT_MODEL="anthropic/claude-opus-4-6"
    DEFAULT_MAX_PARALLEL="4"
    DEFAULT_TIMEOUT="7200"
    DEFAULT_TIMEOUT_MULTIPLIER="5"
    ;;
  *)
    echo "unknown condition: $CONDITION" >&2
    exit 2
    ;;
esac

RUN_ID="${RUN_ID:-$(date -u +%Y%m%dT%H%M%SZ)-$CONDITION}"
if [[ ! "$RUN_ID" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]]; then
  echo "invalid RUN_ID: use only letters, numbers, '.', '_' and '-'" >&2
  exit 2
fi

WORKSPACE_ROOT="${WORKSPACE_ROOT:-$ROOT/workspaces}"
TASKS_DIR="${TASKS_DIR:-$WORKSPACE_ROOT/$RUN_ID/$CONDITION}"
if [[ ! -d "$TASKS_DIR" ]]; then
  echo "workspace tasks not found: $TASKS_DIR" >&2
  echo "prepare this run first:" >&2
  echo "  export RUN_ID=$RUN_ID" >&2
  echo "  uv run python scripts/prepare_tasks.py --condition $CONDITION" >&2
  exit 3
fi

OUTPUT_DIR="${OUTPUT_DIR:-$ROOT/outputs/$RUN_ID}"
AGENT="${AGENT:-$DEFAULT_AGENT}"
MODEL="${MODEL:-$DEFAULT_MODEL}"
MAX_PARALLEL="${MAX_PARALLEL:-$DEFAULT_MAX_PARALLEL}"
TIMEOUT="${TIMEOUT:-$DEFAULT_TIMEOUT}"
TIMEOUT_MULTIPLIER="${TIMEOUT_MULTIPLIER:-$DEFAULT_TIMEOUT_MULTIPLIER}"
if [[ ! "$MAX_PARALLEL" =~ ^[1-9][0-9]*$ ]]; then
  echo "invalid MAX_PARALLEL: expected a positive integer" >&2
  exit 2
fi
mkdir -p "$OUTPUT_DIR"
export COEVOSKILLS_OUTPUT_DIR="$OUTPUT_DIR"
export PYTHONUNBUFFERED=1

COMMON=(
  uv run python "$ROOT/run_exp.py"
  --tasks-dir "$TASKS_DIR"
  --tasks all
  --model "$MODEL"
  --agent "$AGENT"
  --max-parallel "$MAX_PARALLEL"
  --timeout "$TIMEOUT"
  --timeout-multiplier "$TIMEOUT_MULTIPLIER"
  --new-run
  --single-trial-only
  --force-build
)

if [[ "$CONDITION" == "evolution" ]]; then
  EVOLUTION_MODE="${EVOLUTION_MODE:-fresh}"
  case "$EVOLUTION_MODE" in
    fresh)
      EVOLUTION_MODE_ARGS=(--fresh-evolution)
      ;;
    continue)
      EVOLUTION_MODE_ARGS=(--continue-evolution)
      ;;
    *)
      echo "invalid EVOLUTION_MODE: expected 'fresh' or 'continue'" >&2
      exit 2
      ;;
  esac
  "${COMMON[@]}" \
    "${EVOLUTION_MODE_ARGS[@]}" \
    --max-iterations "${MAX_GT_ITERATIONS:-5}" \
    --gt-oracle-model "${GT_ORACLE_MODEL:-$MODEL}" \
    --gt-oracle-agent "${GT_ORACLE_AGENT:-claude-code-skill-only}" \
    --independent-verifier-model "${VERIFIER_MODEL:-$MODEL}" \
    "$@" 2>&1 | tee "$OUTPUT_DIR/run.log"
else
  "${COMMON[@]}" "$@" 2>&1 | tee "$OUTPUT_DIR/run.log"
fi
