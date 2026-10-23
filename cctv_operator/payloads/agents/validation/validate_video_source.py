#!/usr/bin/env python3.12
"""Standalone source check using the native monitor's validation policy."""
import json
import os
from pathlib import Path
import sys

def _load_repo_env() -> None:
    for parent in Path(__file__).resolve().parents:
        if (parent / "otterdesk_blueprint_env.py").exists():
            if str(parent) not in sys.path:
                sys.path.insert(0, str(parent))
            from otterdesk_blueprint_env import load_blueprint_env

            load_blueprint_env(__file__)
            return


_load_repo_env()

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from domain.source_validation import SourceValidationError, validate_source


def blueprint_config() -> dict:
    raw_config = os.environ.get("MN_BLUEPRINT_CONFIG_JSON")
    if raw_config:
        try:
            parsed = json.loads(raw_config)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def main() -> int:
    try:
        print(validate_source(blueprint_config()))
        return 0
    except SourceValidationError as error:
        print(json.dumps(error.report, sort_keys=True))
        return error.status


if __name__ == "__main__":
    raise SystemExit(main())
