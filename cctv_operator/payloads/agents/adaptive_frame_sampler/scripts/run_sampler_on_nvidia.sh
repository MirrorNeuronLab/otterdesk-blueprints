#!/usr/bin/env bash
set -euo pipefail

demo_profile="$(python3 -c 'import json, os; config=json.loads(os.environ.get("MN_BLUEPRINT_CONFIG_JSON", "{}")); source=config.get("video_source", {}); print(source.get("profile", "external") if isinstance(source, dict) else "external")')"
if [[ "${demo_profile}" == "bundled_demo" ]]; then
  # The Web UI service owns the publisher. Wait for concurrent startup without
  # spawning background processes that runtime cleanup would kill after a tick.
  /opt/cctv-demo/start_demo_stream.sh --wait >/dev/null
fi

exec python3 scripts/sample_video.py
