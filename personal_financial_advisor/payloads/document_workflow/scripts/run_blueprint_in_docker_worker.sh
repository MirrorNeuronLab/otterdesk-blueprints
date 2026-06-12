#!/usr/bin/env bash
set -euo pipefail

if ! command -v w3m >/dev/null 2>&1; then
  echo "w3m is required in the personal financial advisor DockerWorker image" >&2
  exit 2
fi

python3 - <<'PY' >&2
import mn_llm_ocr_skill
import mn_w3m_browser_skill

print("llm_ocr_skill and w3m_browser_skill imports are available")
PY

exec python3 scripts/run_blueprint.py "$@"
