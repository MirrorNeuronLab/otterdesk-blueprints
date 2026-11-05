#!/usr/bin/env bash
set -euo pipefail

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
if ! command -v python3 >/dev/null 2>&1; then
  printf 'Error: Python 3.9 or newer is required. Install Python and try again.\n' >&2
  exit 1
fi
exec python3 "$script_dir/create_blueprint.py" "$@"
