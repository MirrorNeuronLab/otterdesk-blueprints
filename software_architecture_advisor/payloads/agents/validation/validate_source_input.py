#!/usr/bin/env python3
"""Validate Architecture Advisor's exactly-one repository source contract."""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys


PAYLOAD_ROOT = Path(__file__).resolve().parents[2]
if str(PAYLOAD_ROOT) not in sys.path:
    sys.path.insert(0, str(PAYLOAD_ROOT))

from domain.source_input import source_input  # noqa: E402


def main() -> int:
    try:
        config = json.loads(os.environ.get("MN_BLUEPRINT_CONFIG_JSON") or "{}")
    except json.JSONDecodeError:
        return fail("config.invalid", "Blueprint configuration must be valid JSON.")
    inputs = config.get("inputs") if isinstance(config.get("inputs"), dict) else {}
    payload = inputs.get("payload") if isinstance(inputs.get("payload"), dict) else {}
    try:
        source_input(payload)
    except (OSError, ValueError) as exc:
        missing = not payload.get("input_folder") and not payload.get("repository_url")
        return fail(
            "config.required" if missing else "config.invalid_source",
            str(exc),
        )
    print("Architecture source input accepted.")
    return 0


def fail(code: str, message: str) -> int:
    path = "inputs.payload.input_folder"
    issue = {
        "code": code,
        "message": message,
        "help": (
            "Provide exactly one source with --set "
            "inputs.payload.input_folder=/path/to/repository or --set "
            "inputs.payload.repository_url=https://github.com/owner/repository."
        ),
        "severity": "error",
        "location": {
            "source": "config",
            "path": path,
            "pointer": "/config/inputs/payload/input_folder",
        },
    }
    print(
        json.dumps(
            {
                "version": 1,
                "schema_version": "validation.report/v1",
                "ok": False,
                "status": "failed",
                "error_count": 1,
                "errors": [message],
                "issues": [issue],
                "results": [],
            },
            sort_keys=True,
        )
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
