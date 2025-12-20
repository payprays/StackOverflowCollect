#!/bin/bash
# 01_crawl.sh - Crawl Stack Overflow questions
# Usage: ./scripts/01_crawl.sh [tag] [limit]
#
# This script fetches questions from Stack Overflow for a given tag.
# Results are saved to data/ directory and data/results.csv

set -e

TAG=${1:-"kubernetes"}
LIMIT=${2:-10}
OUT_DIR="data"

echo "🚀 Starting Crawl for tag: '$TAG', limit: $LIMIT..."
echo "   Output directory: $OUT_DIR"
echo ""

uv run python main.py crawl \
--tag "$TAG" \
--limit "$LIMIT" \
--out-dir "$OUT_DIR"

echo ""
echo "✅ Crawl completed! Check $OUT_DIR/results.csv for data."
