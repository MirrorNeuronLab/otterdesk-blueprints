#!/usr/bin/env bash
set -euo pipefail

if ! command -v w3m >/dev/null 2>&1; then
  echo "w3m is required in the VC Assistant DockerWorker image" >&2
  exit 2
fi

python3 - <<'PY' >&2
import mn_blueprint_support
from mn_context_engine_sdk import MemoryItem, WorkingMemory
import mn_llm_ocr_skill
import mn_rag_skill
import mn_w3m_browser_skill

assert MemoryItem is not None and WorkingMemory is not None
print("VC Assistant DockerWorker skill and context imports are available")
PY

exec python3 scripts/run_blueprint.py "$@"
