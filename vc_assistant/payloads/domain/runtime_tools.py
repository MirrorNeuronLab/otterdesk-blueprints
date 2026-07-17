"""Runtime-neutral observability and bounded LLM adapters."""

from __future__ import annotations

from .common import *

def append_event(run_dir: Path, event_type: str, payload: dict[str, Any]) -> None:
    append_event_jsonl(run_dir, event_type, payload, lock=EVENT_LOCK)

def append_resource_record(run_dir: Path | None, event_type: str, payload: dict[str, Any]) -> None:
    if run_dir is None:
        return
    record = {"type": event_type, "timestamp": utc_now_iso(), "payload": observation_payload(**payload)}
    with TRACE_LOCK:
        with (run_dir / "resources.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")

def stable_text_hash(value: Any) -> str:
    return hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()[:16]

def observation_payload(**metadata: Any) -> dict[str, Any]:
    return redact_observation_value({key: value for key, value in metadata.items() if value is not None})

def append_observation_record(run_dir: Path | None, event_type: str, payload: dict[str, Any]) -> None:
    if run_dir is None:
        return
    record = {"type": event_type, "timestamp": utc_now_iso(), "payload": observation_payload(**payload)}
    with TRACE_LOCK:
        with (run_dir / "llm_rag_trace.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
    append_event(run_dir, event_type, record["payload"])

def append_debug_record(run_dir: Path | None, event_type: str, payload: dict[str, Any]) -> None:
    if run_dir is None:
        return
    run_dir.mkdir(parents=True, exist_ok=True)
    record = {"type": event_type, "timestamp": utc_now_iso(), "payload": observation_payload(**payload)}
    with TRACE_LOCK:
        with (run_dir / "debug_trace.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
    append_event(run_dir, event_type, record["payload"])

def append_debug_record_if_enabled(ctx: dict[str, Any], event_type: str, payload: dict[str, Any]) -> None:
    if debug_mode_enabled(ctx.get("config") if isinstance(ctx, dict) else None):
        append_debug_record(ctx.get("run_dir"), event_type, payload)

def write_benchmark_artifacts(run_dir: Path, *, run_id: str, status: str = "running") -> dict[str, Any]:
    return write_shared_benchmark_artifacts(
        run_dir,
        run_id=run_id,
        blueprint_id=BLUEPRINT_ID,
        status=status,
        title=BLUEPRINT_NAME,
    )

def observed_operation(
    run_dir: Path | None,
    *,
    phase: str,
    operation: str,
    heartbeat_seconds: float = DEFAULT_OBSERVABILITY_HEARTBEAT_SECONDS,
    **metadata: Any,
) -> ObservedOperation:
    return shared_observed_operation(
        run_dir,
        phase=phase,
        operation=operation,
        event_writer=append_observation_record,
        heartbeat_seconds=heartbeat_seconds,
        thread_name_prefix="vc-observe",
        **metadata,
    )

def _api_base_kind(api_base: Any) -> str:
    value = str(api_base or "").strip()
    if not value:
        return "unknown"
    parsed = urlparse(value)
    host = parsed.hostname or value
    if "12434" in value or "/engines/" in value:
        return "docker_model_runner"
    if "11434" in value:
        return "ollama"
    if host in {"localhost", "127.0.0.1", "::1"}:
        return "local_openai_compatible"
    return "remote_openai_compatible"

def _llm_usage_event_fields(llm: Any) -> dict[str, Any]:
    usage = getattr(llm, "last_usage", {}) or {}
    if not isinstance(usage, dict):
        usage = {}
    return {
        "input_tokens": int(usage.get("input_tokens") or 0),
        "output_tokens": int(usage.get("output_tokens") or 0),
        "total_tokens": int(usage.get("total_tokens") or 0),
        "usage_estimated": bool(usage.get("estimated")),
        "usage_source": str(usage.get("source") or "unknown"),
        "usage_provider": str(usage.get("provider") or getattr(llm, "provider", "unknown")),
        "usage_model": str(usage.get("model") or getattr(llm, "model", "unknown")),
        "api_base_kind": _api_base_kind(getattr(llm, "api_base", "")),
    }

def _vc_llm_fallback(
    *,
    reason: str,
    fallback: dict[str, Any],
    model: str,
    error: Exception | None = None,
) -> dict[str, Any]:
    response = dict(fallback)
    if reason == "budget_exhausted":
        response["summary"] = response.get("summary") or "Actor review skipped because the VC Assistant action budget was exhausted."
        response["provider"] = "budget_exhausted"
    else:
        response["summary"] = response.get("summary") or "Actor review unavailable; deterministic VC report artifacts were preserved."
        response["provider"] = "actor_review_unavailable"
    response.setdefault("findings", [])
    response.setdefault("risks", [])
    response["model"] = model
    response["budget_status"] = reason
    if error is not None:
        response["error"] = str(error)
    return response

class BudgetedLLM(BudgetedLlmClient):
    def __init__(
        self,
        llm: Any,
        action_budget: ActionBudget,
        *,
        require_live: bool = False,
        limiter: LlmCallLimiter | None = None,
        run_dir: Path | None = None,
        heartbeat_seconds: float = DEFAULT_OBSERVABILITY_HEARTBEAT_SECONDS,
    ) -> None:
        super().__init__(
            llm,
            action_budget,
            require_live=require_live,
            limiter=limiter,
            run_dir=run_dir,
            observation_writer=append_observation_record,
            resource_writer=append_resource_record,
            fallback_builder=_vc_llm_fallback,
            provider_live_check=provider_is_live,
            usage_reader=_llm_usage_event_fields,
            action_type="llm_call",
            tool_name="actor_llm",
            operation="actor_llm.generate_json",
            heartbeat_seconds=heartbeat_seconds,
        )

    def generate_json(self, *, system_prompt: str, user_prompt: str, fallback: dict[str, Any]) -> dict[str, Any]:
        actor_id = str(fallback.get("actor_id") or system_prompt or "actor_review")
        return super().generate_json(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            fallback=fallback,
            stage=actor_id,
            metadata={
                "api_base_kind": _api_base_kind(getattr(self._llm, "api_base", "")),
                "request_status": "scheduled",
                "prompt_hash": stable_text_hash(f"{system_prompt}\n{user_prompt}"),
            },
        )

def quick_test_mode_enabled(config: dict[str, Any]) -> bool:
    payload = (config.get("inputs") or {}).get("payload") if isinstance(config.get("inputs"), dict) else {}
    execution = config.get("execution") if isinstance(config.get("execution"), dict) else {}
    env_value = os.environ.get("MN_QUICK_TEST") or os.environ.get("MN_BLUEPRINT_QUICK_TEST")
    if env_value is not None:
        return str(env_value).strip().lower() in {"1", "true", "yes", "on"}
    return bool((payload or {}).get("quick_test") or execution.get("quick_test"))

def llm_requires_live(config: dict[str, Any]) -> bool:
    llm_config = config.get("llm") if isinstance(config.get("llm"), dict) else {}
    if fake_llm_mode_enabled(config) or quick_test_mode_enabled(config):
        return False
    value = llm_config.get("require_live", False)
    return bool(value) if isinstance(value, bool) else str(value or "").strip().lower() in {"1", "true", "yes", "on"}

def provider_is_live(provider: str) -> bool:
    return str(provider or "").strip().lower() not in {
        "",
        "fallback",
        "fake",
        "mock",
        "actor_review_unavailable",
        "budget_exhausted",
        "unavailable",
        "disabled",
    }

