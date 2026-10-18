"""Check litigation model prerequisites without sending case evidence."""
import json
import os
import time
from dataclasses import replace
from pathlib import Path

from mn_sdk.blueprint_support import durable_json_decision
from mn_sdk.context_session import ContextPolicy
from mn_sdk.llm import LLMClient

from .app.planning import object_schema, validate


def check(context, client=None):
    settings = context["config"].get("model_preflight", {})
    if not settings.get("enabled", True):
        return
    root = Path(context["run_dir"])
    path = root / "case/model_preflight.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    current = client if client is not None else LLMClient.from_env(strict=True)
    if isinstance(current, LLMClient):
        current = replace(current, timeout_seconds=min(current.timeout_seconds, settings.get("timeout_seconds", 10)))
    scope = {"job_id": context.get("job_id") or os.environ.get("MN_JOB_ID"),
             "run_id": os.environ.get("MN_WORKFLOW_RUN_ID") or context.get("run_id") or os.environ.get("MN_RUN_ID")}
    started = time.monotonic()
    receipt = {"model": str(getattr(current, "model", "injected")),
               "case_evidence_sent": False, "status": "checking", "fallback_model": None}
    try:
        durable_json_decision(root / "case/model_preflight_decision.json",
            system="This is a service readiness check. Return the requested JSON, without explanation.",
            request={"task": "Return ready=true. No case evidence is supplied."},
            schema=object_schema({"ready": {"const": True}}), validator=validate,
            context_root=root / "case/preflight-context", context_scope=scope,
            principal="litigation-preflight", stage="model_readiness",
            policy=ContextPolicy(**context["config"]["context_memory"]["policy"]),
            max_tokens=context["config"]["context_memory"]["policy"]["output_tokens"],
            client=current, memory_recall=False)
    except (RuntimeError, ValueError, OSError) as error:
        receipt.update(status="unavailable", error_type=type(error).__name__,
                       action="Selected model must support verified context admission and structured output. Check its integration; no replacement model was used.")
        receipt["elapsed_seconds"] = round(time.monotonic() - started, 3)
        path.write_text(json.dumps(receipt, indent=2))
        raise ValueError("Litigation model preflight failed before case analysis. See case/model_preflight.json; no fallback model was used.") from error
    receipt.update(status="ready", elapsed_seconds=round(time.monotonic() - started, 3))
    path.write_text(json.dumps(receipt, indent=2))
