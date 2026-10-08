#!/usr/bin/env bash
set -euo pipefail

demo_profile="$(python3 -c 'import json, os; config=json.loads(os.environ.get("MN_BLUEPRINT_CONFIG_JSON", "{}")); source=config.get("video_source", {}); print(source.get("profile", "external") if isinstance(source, dict) else "external")')"
if [[ "${demo_profile}" == "bundled_demo" ]]; then
  demo_file="$(python3 -c 'import json, os; print(json.loads(os.environ["MN_BLUEPRINT_CONFIG_JSON"])["video_source"]["demo_file"])')"
  # The publisher inherits this long-running service's process group. Runtime
  # cancellation stops it with the UI, rather than after each sampling tick.
  /opt/cctv-demo/start_demo_stream.sh "${demo_file}" >/dev/null
fi

exec python3 services/cctv_web_ui.py
