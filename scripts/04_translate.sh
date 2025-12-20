#!/bin/bash
# 04_translate.sh - Translate Q&A and answers to Chinese
# Usage: ./scripts/04_translate.sh [input_csv]
#
# This script translates:
# - Question & Answer pairs (QA_Translated column)
# - Model-generated answers ({model}_Answer_Translated column)

set -e

INPUT_CSV=${1:-"./data/merged_output.csv"}
OUT_DIR="data"

echo "🌐 Translating content to Chinese..."
echo "   Input CSV: $INPUT_CSV"
echo "   Output directory: $OUT_DIR"
echo ""

uv run python main.py translate \
--input-csv "$INPUT_CSV" \
--out-dir "$OUT_DIR"

echo ""
echo "✅ Translation completed! Check $OUT_DIR/results.csv for:"
echo "   - QA_Translated: Translated Q&A"
echo "   - {model}_Answer_Translated: Translated model answers"
