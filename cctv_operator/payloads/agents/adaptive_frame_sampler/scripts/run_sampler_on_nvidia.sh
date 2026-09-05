#!/usr/bin/env bash
set -euo pipefail

demo_profile="$(python3 -c 'import json, os; config=json.loads(os.environ.get("MN_BLUEPRINT_CONFIG_JSON", "{}")); source=config.get("video_source", {}); print(source.get("profile", "external") if isinstance(source, dict) else "external")')"
if [[ "${demo_profile}" == "bundled_demo" ]]; then
  /opt/cctv-demo/start_demo_stream.sh >/dev/null 2>&1
fi

exec python3 scripts/sample_video.py
