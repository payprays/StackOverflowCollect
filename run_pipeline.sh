#!/usr/bin/env bash
# run_pipeline.sh - 快速运行 answer → evaluate 完整流程
#
# 用法:
#   ./run_pipeline.sh                    # 使用默认模型 gpt-5.1
#   ./run_pipeline.sh gpt-4o             # 指定模型
#   ./run_pipeline.sh gpt-5.1 20         # 指定模型和数量限制
#   ./run_pipeline.sh gpt-5.1 20 8       # 指定模型、数量和并发数

set -e

MODEL="${1:-gpt-5.1}"
LIMIT="${2:-91}"
WORKERS="${3:-8}"
DATA_DIR="yaml_blocks"
BASE_URL="https://api.openai.com/"

echo "==================================="
echo "🚀 Pipeline: ${MODEL}"
echo "   Data: ${DATA_DIR}"
echo "   Limit: ${LIMIT}"
echo "   Workers: ${WORKERS}"
echo "==================================="

# Step 1: Generate Answers
echo ""
echo "📝 Step 1: Generating Answers..."
uv run python main.py answer \
--out-dir "${DATA_DIR}" \
--model "${MODEL}" \
--base-url "${BASE_URL}" \
--workers "${WORKERS}" \
--limit "${LIMIT}" \
--force

# Step 2: Evaluate Answers
echo ""
echo "🔍 Step 2: Evaluating Answers..."
uv run python main.py evaluate \
--input-dir "${DATA_DIR}" \
--model "${MODEL}" \
--base-url "${BASE_URL}" \
--workers "${WORKERS}" \
--limit "${LIMIT}" \
--force

echo ""
echo "==================================="
echo "✅ Pipeline Complete!"
echo "   Results: ${DATA_DIR}/results.csv"
echo "==================================="
