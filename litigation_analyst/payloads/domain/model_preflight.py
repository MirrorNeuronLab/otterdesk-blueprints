"""Check litigation model prerequisites without sending case evidence."""
import json
import math
import os
import time
from dataclasses import replace
from pathlib import Path

from jsonschema import ValidationError
from mn_sdk.blueprint_support import durable_json_decision
from mn_sdk.context_session import ContextPolicy
from mn_sdk.llm import LLMClient

from .app.planning import object_schema, validate


def _timed_out(error):
    seen = set()
    while isinstance(error, BaseException) and id(error) not in seen:
        seen.add(id(error))
        if isinstance(error, TimeoutError):
            return True
        error = error.__cause__ or error.__context__ or getattr(error, "reason", None)
    return False


def check(context, client=None):
    settings = context.config.get("model_preflight", {})
    if not settings.get("enabled", True):
        return
    root = Path(context.store.run_dir)
    path = root / "case/model_preflight.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    current = client if client is not None else LLMClient.from_env(strict=True)
    timeout = settings.get("timeout_seconds")
    if timeout is not None:
        if type(timeout) not in (int, float) or not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("model_preflight.timeout_seconds must be a positive finite number")
        if isinstance(current, LLMClient):
            current = replace(current, timeout_seconds=min(current.timeout_seconds, timeout))
    scope = {"job_id": context.job_id or os.environ.get("MN_JOB_ID"),
             "run_id": os.environ.get("MN_WORKFLOW_RUN_ID") or context.run_id or os.environ.get("MN_RUN_ID")}
    started = time.monotonic()
    receipt = {"model": str(getattr(current, "model", "injected")),
               "case_evidence_sent": False, "status": "checking", "fallback_model": None}
    if isinstance(current, LLMClient):
        receipt["request_timeout_seconds"] = current.timeout_seconds
    try:
        durable_json_decision(root / "case/model_preflight_decision.json",
            system="This is a service readiness check. Return the requested JSON, without explanation.",
            request={"task": "Return ready=true. No case evidence is supplied."},
            schema=object_schema({"ready": {"const": True}}), validator=validate,
            context_root=root / "case/preflight-context", context_scope=scope,
            principal="litigation-preflight", stage="model_readiness",
            policy=ContextPolicy(**context.config["context_memory"]["policy"]),
            max_tokens=context.config["context_memory"]["policy"]["output_tokens"],
            client=current, memory_recall=False)
    except (RuntimeError, ValueError, OSError, ValidationError) as error:
        timed_out = _timed_out(error)
        reason = "request_timeout" if timed_out else "model_check_failed"
        action = (
            "Selected model request timed out. Check model availability and the configured request timeout; no replacement model was used."
            if timed_out else
            "Selected model readiness check failed. Check its availability, context admission and structured output; no replacement model was used."
        )
        receipt.update(status="unavailable", error_type=type(error).__name__,
                       reason=reason, action=action)
        receipt["elapsed_seconds"] = round(time.monotonic() - started, 3)
        path.write_text(json.dumps(receipt, indent=2))
        summary = "Selected model request timed out." if timed_out else "Selected model readiness check failed."
        raise ValueError(f"Litigation model preflight failed before case analysis. {summary} See case/model_preflight.json; no fallback model was used.") from error
    receipt.update(status="ready", elapsed_seconds=round(time.monotonic() - started, 3))
    path.write_text(json.dumps(receipt, indent=2))
