#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

PYTHON_BIN="${PYTHON_BIN:-python3.11}"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "$PYTHON_BIN is required to materialize Personal Income Tax Expert outputs." >&2
  exit 0
fi

"$PYTHON_BIN" "${SCRIPT_DIR}/materialize-tax-results.py"
