#!/bin/bash
# 02_answer.sh
# Usage: ./scripts/02_answer.sh [model]

# Default model, can be overridden
MODEL=${1:-"gpt-4o"} # Or similar default
OUT_DIR="data"

echo "🤖 Generatng Answers using model: '$MODEL'..."

# If you have an input CSV you want to process instead of crawled data:
# uv run python main.py answer --model "$MODEL" --input-csv "input.csv" --out-dir "$OUT_DIR"

# Processing crawled directories:
uv run python main.py answer --model "$MODEL" --out-dir "$OUT_DIR" --workers 4
