"""Shared constants and safe runtime helpers for the architecture advisor."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

BLUEPRINT_ID = "software_architecture_advisor"
BLUEPRINT_NAME = "Software Architecture Advisor"
OUTPUT_TYPE = "software_architecture_advice"
DEFAULT_OUTPUT_FOLDER = "~/Downloads/software_architecture_advisor"
BLOCKED_ACTIONS = [
    "modify_source_code", "execute_project_code", "install_project_dependencies",
    "run_project_tests", "network_egress", "push_to_repository", "deploy_or_release",
]
def json_safe(value: Any) -> Any:
    try:
        json.dumps(value)
        return value
    except (TypeError, ValueError):
        if isinstance(value, dict):
            return {str(key): json_safe(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [json_safe(item) for item in value]
        return str(value)


def expand_output_path(value: str) -> Path:
    runtime_value = os.environ.get("MN_JOB_OUTPUT_DIR")
    return Path(runtime_value or value or DEFAULT_OUTPUT_FOLDER).expanduser()
