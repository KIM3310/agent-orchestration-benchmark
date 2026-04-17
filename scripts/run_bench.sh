#!/usr/bin/env bash
# Convenience wrapper around ``python -m scripts.run_bench``.
#
# Usage:
#   ./scripts/run_bench.sh                    # all frameworks, mock LLM
#   ./scripts/run_bench.sh --use-live         # real LLM APIs (needs OPENAI_API_KEY)
#   FRAMEWORKS=langgraph ./scripts/run_bench.sh
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$(dirname "${HERE}")"

FRAMEWORKS=${FRAMEWORKS:-all}
OUTPUT=${OUTPUT:-results/latest.json}

exec python -m scripts.run_bench \
    --frameworks "${FRAMEWORKS}" \
    --output "${OUTPUT}" \
    "$@"
