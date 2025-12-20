#!/bin/bash
# 03_evaluate.sh - Run lint check and LLM evaluation on answers
# Usage: ./scripts/03_evaluate.sh [model] [input_csv] [--force]
#
# This script:
# 1. Extracts YAML code blocks from answers
# 2. Runs kubeval and kubectl dry-run checks (lint)
# 3. Runs LLM evaluation using the specified model
#
# Results are saved to data/results.csv with columns:
# - lint: Summary like "kubeval:2/3; dryrun:1/3"
# - {model}_Answer_CodeBlocks: Extracted YAML blocks
# - lint_logs: Detailed lint output
# - {model}_Evaluate_{model}_Answer: LLM evaluation result

set -e

MODEL=${1:-"gpt-5.1"}
INPUT_CSV=${2:-"./data/merged_output.csv"}
FORCE=""
OUT_DIR="data"
WORKERS=4

# Check for --force flag
if [[ "$*" == *"--force"* ]]; then
    FORCE="--force"
    echo "⚠️  Force mode enabled - will re-evaluate existing items"
fi

echo "⚖️  Evaluating Answers with model: '$MODEL'..."
echo "   Input CSV: $INPUT_CSV"
echo "   Output directory: $OUT_DIR"
echo "   Workers: $WORKERS"
echo ""

uv run python main.py evaluate \
--model "$MODEL" \
--input-csv "$INPUT_CSV" \
--input-dir "$OUT_DIR" \
--workers "$WORKERS" \
$FORCE

echo ""
echo "✅ Evaluation completed! Check $OUT_DIR/results.csv for:"
echo "   - lint: Lint check summary"
echo "   - lint_logs: Detailed lint output"
echo "   - ${MODEL}_Answer_CodeBlocks: Extracted code blocks"
echo "   - ${MODEL}_Evaluate_${MODEL}_Answer: LLM evaluation"
