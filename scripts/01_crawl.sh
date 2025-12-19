#!/bin/bash
# 01_crawl.sh
# Usage: ./scripts/01_crawl.sh [tag] [limit]

TAG=${1:-"kubernetes"}
LIMIT=${2:-10}
OUT_DIR="data"

echo "🚀 Starting Crawl for tag: '$TAG', limit: $LIMIT..."
uv run python main.py crawl --tag "$TAG" --limit "$LIMIT" --out-dir "$OUT_DIR"
