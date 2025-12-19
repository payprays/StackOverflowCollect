#!/bin/bash
# 03_evaluate.sh
# Usage: ./scripts/03_evaluate.sh [eval_model]

EVAL_MODEL=${1:-"gpt-4o"}
ANSWER_MODEL="gpt-4o-mini" # The model that generated the answers
OUT_DIR="data"

echo "⚖️  Evaluating Answers (Model: $ANSWER_MODEL) using Judge: $EVAL_MODEL..."

uv run python main.py evaluate --model "$EVAL_MODEL" --out-dir "$OUT_DIR"
