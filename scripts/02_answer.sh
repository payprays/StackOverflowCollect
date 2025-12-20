#!/bin/bash
# 02_answer.sh - Generate LLM answers for questions
# Usage: ./scripts/02_answer.sh [model] [input_csv]
#
# This script generates model answers for crawled or CSV-provided questions.
# Answers are saved to data/{model}_answer.md files and data/results.csv

set -e

MODEL=${1:-"gpt-5.1"}
INPUT_CSV=${2:-""}
OUT_DIR="data"
WORKERS=4

echo "🤖 Generating Answers using model: '$MODEL'..."
echo "   Output directory: $OUT_DIR"
echo "   Workers: $WORKERS"

if [ -n "$INPUT_CSV" ]; then
    echo "   Input CSV: $INPUT_CSV"
    uv run python main.py answer \
    --model "$MODEL" \
    --input-csv "$INPUT_CSV" \
    --out-dir "$OUT_DIR" \
    --workers "$WORKERS"
else
    echo "   Processing crawled data in: $OUT_DIR"
    uv run python main.py answer \
    --model "$MODEL" \
    --out-dir "$OUT_DIR" \
    --workers "$WORKERS"
fi

echo ""
echo "✅ Answer generation completed! Check $OUT_DIR/results.csv"
