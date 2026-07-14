from __future__ import annotations

from typing import Any

from mn_sdk.step_runtime import StepContext

import run_blueprint as runtime


def previous_payload(context: StepContext) -> dict[str, Any]:
    return _find_payload(context.message)


def runtime_inputs(context: StepContext) -> tuple[dict[str, Any], dict[str, Any], str]:
    config = runtime.load_config(
        runtime.BLUEPRINT_ID,
        default_config_path=runtime.default_config_path(),
        config=context.config or None,
        run_id=context.run_id or None,
        write_run_store=False,
    )
    adapter_inputs, input_source = runtime.resolve_input_overrides(config)
    previous = previous_payload(context)
    previous_inputs = previous.get("inputs") if isinstance(previous.get("inputs"), dict) else {}
    message_inputs = _find_inputs(context.message)
    inputs = runtime.normalize_inputs(
        {
            **((config.get("inputs") or {}).get("payload") or {}),
            **adapter_inputs,
            **previous_inputs,
            **message_inputs,
        }
    )
    return config, inputs, input_source


def step_result(context: StepContext, payload: dict[str, Any], **extra: Any) -> dict[str, Any]:
    return {
        "run_id": context.run_id,
        "status": "completed",
        "workflow_step_id": context.step_id,
        "workflow_payload": payload,
        **extra,
    }


def _find_payload(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        payload = value.get("workflow_payload")
        if isinstance(payload, dict):
            return payload
        for key in ("stdout", "sandbox", "body", "payload", "data", "message", "content", "input"):
            found = _find_payload(value.get(key))
            if found:
                return found
        for nested in value.values():
            found = _find_payload(nested)
            if found:
                return found
    elif isinstance(value, list):
        for nested in value:
            found = _find_payload(nested)
            if found:
                return found
    elif isinstance(value, str) and value.strip().startswith(("{", "[")):
        import json

        try:
            return _find_payload(json.loads(value))
        except ValueError:
            return {}
    return {}


def _find_inputs(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        interesting = {
            "purchase_type",
            "item_description",
            "budget",
            "currency",
            "input_folder",
            "output_folder",
        }
        if interesting & set(value):
            return dict(value)
        for key in ("kwargs", "payload", "body", "data", "message", "content", "input"):
            found = _find_inputs(value.get(key))
            if found:
                return found
        for nested in value.values():
            found = _find_inputs(nested)
            if found:
                return found
    elif isinstance(value, list):
        for nested in value:
            found = _find_inputs(nested)
            if found:
                return found
    elif isinstance(value, str) and value.strip().startswith(("{", "[")):
        import json

        try:
            return _find_inputs(json.loads(value))
        except ValueError:
            return {}
    return {}
