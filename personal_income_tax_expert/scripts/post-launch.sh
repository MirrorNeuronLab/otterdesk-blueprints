#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required to materialize Personal Income Tax Expert outputs." >&2
  exit 0
fi

python3 "${SCRIPT_DIR}/materialize-tax-results.py"
