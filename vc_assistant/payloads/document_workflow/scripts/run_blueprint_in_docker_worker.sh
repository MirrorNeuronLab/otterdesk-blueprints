#!/usr/bin/env bash
set -euo pipefail

GAR_INDEX_URL="https://us-central1-python.pkg.dev/mirrorneuron-public-packages/agent-skills/simple/"
GAR_EXTRA_INDEX_URL="https://pypi.org/simple"
SHARED_SKILL_SPECS=(
  "evidence_engine_skill:mirrorneuron-evidence-engine-skill"
  "actor_review_skill:mirrorneuron-actor-review-skill"
  "client_report_skill:mirrorneuron-client-report-skill"
  "document_reading_skill:mirrorneuron-document-reading-skill"
  "public_research_orchestrator_skill:mirrorneuron-public-research-orchestrator-skill"
  "scoring_framework_skill:mirrorneuron-scoring-framework-skill"
)

if ! command -v w3m >/dev/null 2>&1; then
  echo "w3m is required in the VC Assistant DockerWorker image" >&2
  exit 2
fi

is_dev_env() {
  case "${MN_ENV:-${OTTERDESK_ENV:-}}" in
    dev|development|local)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

find_workspace_root() {
  local candidates=()
  if [ -n "${MN_WORKSPACE_ROOT:-}" ]; then
    candidates+=("$MN_WORKSPACE_ROOT")
  fi
  if [ -n "${MN_BLUEPRINT_LOCAL:-}" ]; then
    candidates+=("$MN_BLUEPRINT_LOCAL")
    candidates+=("$(dirname "$MN_BLUEPRINT_LOCAL")")
  fi

  local candidate
  for candidate in "${candidates[@]}" /workspace /mn/workspace /Users/*/Projects/mirror-neuron-set; do
    if [ -d "$candidate/mn-skills" ]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done
  return 1
}

find_staged_skill_root() {
  local candidate
  for candidate in "${MN_BUNDLE_ROOT:-}/.mn-local-skills" "${MN_WORKDIR:-}/.mn-local-skills" /mn/job/.mn-local-skills; do
    if [ -d "$candidate" ]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done
  return 1
}

add_staged_skill_paths() {
  local staged_root="$1"
  local spec folder path missing=0
  for spec in "${SHARED_SKILL_SPECS[@]}"; do
    folder="${spec%%:*}"
    path="$staged_root/$folder/src"
    if [ -d "$path" ]; then
      export PYTHONPATH="$path${PYTHONPATH:+:$PYTHONPATH}"
    else
      echo "Missing staged shared skill source: $path" >&2
      missing=1
    fi
  done

  if [ "$missing" -ne 0 ]; then
    exit 2
  fi

  echo "VC Assistant DockerWorker using staged local mn-skills from $staged_root" >&2
}

add_dev_skill_paths() {
  local workspace_root
  if ! workspace_root="$(find_workspace_root)"; then
    echo "MN_ENV=dev requires a mounted mirror-neuron-set workspace containing mn-skills." >&2
    echo "Set MN_WORKSPACE_ROOT=/Users/homer/Projects/mirror-neuron-set before starting the runtime." >&2
    exit 2
  fi

  local spec folder path missing=0
  for spec in "${SHARED_SKILL_SPECS[@]}"; do
    folder="${spec%%:*}"
    path="$workspace_root/mn-skills/$folder/src"
    if [ -d "$path" ]; then
      export PYTHONPATH="$path${PYTHONPATH:+:$PYTHONPATH}"
    else
      echo "Missing local shared skill source: $path" >&2
      missing=1
    fi
  done

  if [ "$missing" -ne 0 ]; then
    exit 2
  fi

  echo "VC Assistant DockerWorker using local mn-skills from $workspace_root" >&2
}

install_prod_skills() {
  local packages=()
  local spec
  for spec in "${SHARED_SKILL_SPECS[@]}"; do
    packages+=("${spec##*:}")
  done

  python3 -m pip install -q --break-system-packages --no-cache-dir \
    --index-url "$GAR_INDEX_URL" \
    --extra-index-url "$GAR_EXTRA_INDEX_URL" \
    "${packages[@]}"
}

staged_skill_root=""
if staged_skill_root="$(find_staged_skill_root)"; then
  add_staged_skill_paths "$staged_skill_root"
elif is_dev_env; then
  add_dev_skill_paths
else
  install_prod_skills
fi

python3 - <<'PY' >&2
import mn_blueprint_support
from mn_context_engine_sdk import MemoryItem, WorkingMemory
import mn_actor_review_skill
import mn_client_report_skill
import mn_document_reading_skill
import mn_evidence_engine_skill
import mn_llm_ocr_skill
import mn_public_research_orchestrator_skill
import mn_rag_skill
import mn_scoring_framework_skill
import mn_w3m_browser_skill

assert MemoryItem is not None and WorkingMemory is not None
print("VC Assistant DockerWorker skill and context imports are available")
PY

exec python3 scripts/run_blueprint.py "$@"
