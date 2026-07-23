"""Shared, domain-specific model review policy and usage accounting."""

from .common import *
from .knowledge import knowledge_context_for_step, load_prompt, render_prompt

def step_model_profile(config: dict[str, Any], step_id: str) -> dict[str, Any]:
    llm = config.get("llm") if isinstance(config.get("llm"), dict) else {}
    agents = llm.get("agents") if isinstance(llm.get("agents"), dict) else {}
    spec = agents.get(step_id) if isinstance(agents.get(step_id), dict) else {}
    config_name = str(spec.get("llm_config") or llm.get("default_config") or "primary")
    configs = llm.get("configs") if isinstance(llm.get("configs"), dict) else {}
    profile = copy.deepcopy(configs.get(config_name) if isinstance(configs.get(config_name), dict) else {})
    if not profile and config_name == "large":
        profile = copy.deepcopy(llm.get("large_model_profile") or {})
    if not profile:
        profile = copy.deepcopy(configs.get("primary") or llm.get("small_model_profile") or {})
    profile.setdefault("model", llm.get("model") or "small")
    profile.setdefault("runtime_model", profile.get("model"))
    return {
        "agent_id": step_id,
        "llm_config": config_name,
        "model": profile.get("model"),
        "runtime_model": profile.get("runtime_model"),
        "require_live": bool(profile.get("require_live", False)),
        "profile": profile,
    }

def listify(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple) or isinstance(value, set):
        return list(value)
    if isinstance(value, str):
        return [value] if value.strip() else []
    return [value]

def normalize_review_response(response: dict[str, Any], fallback: dict[str, Any], source_refs: list[str]) -> dict[str, Any]:
    normalized = copy.deepcopy(fallback)
    if isinstance(response, dict):
        normalized.update(response)
    normalized["summary"] = str(normalized.get("summary") or fallback.get("summary") or "LLM review completed.")
    for field, aliases in {
        "key_findings": ("key_findings", "findings"),
        "review_questions": ("review_questions",),
        "evidence_gaps": ("evidence_gaps",),
        "risk_flags": ("risk_flags", "risks"),
        "next_steps": ("next_steps",),
    }.items():
        response_values = []
        for alias in aliases:
            response_values.extend(listify(response.get(alias)))
        fallback_values = listify(fallback.get(field))
        # Deterministic blockers and source-review tasks cannot be cleared by
        # a polished LLM response that omits them.
        normalized[field] = list(dict.fromkeys([*fallback_values, *response_values]))
    normalized["review_only"] = True
    normalized["source_refs"] = sorted({str(item) for item in listify(normalized.get("source_refs")) + source_refs if str(item)})
    try:
        confidence = float(normalized.get("confidence", fallback.get("confidence", 0.62)))
    except (TypeError, ValueError):
        confidence = float(fallback.get("confidence", 0.62))
    normalized["confidence"] = round(min(1.0, max(0.0, confidence)), 2)
    return normalized

def live_llm_requested(config: dict[str, Any], payload: dict[str, Any] | None = None) -> bool:
    llm = config.get("llm") if isinstance(config.get("llm"), dict) else {}
    if not bool(llm.get("enabled", True)):
        return False
    return not fake_llm_requested(config, payload)

def fake_llm_requested(config: dict[str, Any], payload: dict[str, Any] | None = None) -> bool:
    execution = config.get("execution") if isinstance(config.get("execution"), dict) else {}
    if bool(execution.get("quick_test")) or bool((payload or {}).get("quick_test")):
        return True
    if not payload or not payload.get("quick_test"):
        return fake_llm_mode_enabled(config)
    merged = copy.deepcopy(config)
    merged.setdefault("execution", {})["quick_test"] = True
    return fake_llm_mode_enabled(merged)

def build_llm_client(config: dict[str, Any], payload: dict[str, Any], llm_client: Any | None) -> Any:
    if llm_client is not None:
        return llm_client
    if fake_llm_requested(config, payload):
        return DeterministicLLM()
    if not live_llm_requested(config, payload):
        return None
    if get_actor_llm_client is None:
        raise RuntimeError(
            "Financial Advisor requires the shared live LLM client for normal runs. "
            "Install/enable mn_blueprint_support or run with explicit fake/quick-test mode."
        )
    try:
        client = get_actor_llm_client(config, None)
    except Exception as exc:
        raise RuntimeError(f"Unable to initialize shared live LLM client: {exc}") from exc
    if client is None or isinstance(client, DeterministicLLM):
        raise RuntimeError("Shared live LLM client was unavailable for a normal Financial Advisor run.")
    return client

def actor_review(
    config: dict[str, Any],
    llm: Any,
    step_id: str,
    summary: str,
    context: dict[str, Any],
    *,
    fallback: dict[str, Any] | None = None,
    prompt_details: str = "",
    active_knowledge: dict[str, Any] | None = None,
) -> dict[str, Any]:
    profile = step_model_profile(config, step_id)
    llm_config = config.get("llm") if isinstance(config.get("llm"), dict) else {}
    agents = llm_config.get("agents") if isinstance(llm_config.get("agents"), dict) else {}
    actor_spec = agents.get(step_id) if isinstance(agents.get(step_id), dict) else {}
    role = str(actor_spec.get("role") or step_id.replace("_", " ").title())
    responsibilities = [str(item) for item in actor_spec.get("responsibilities", []) if str(item)]
    default_fallback = {
        "actor_id": step_id,
        "summary": summary,
        "findings": [],
        "risks": [],
        "recommended_next_step": "Review source evidence before downstream use.",
        "confidence": 0.74,
        "llm_config": profile["llm_config"],
        "model": profile["model"],
        "runtime_model": profile["runtime_model"],
    }
    if fallback:
        default_fallback.update(copy.deepcopy(fallback))
    fallback = default_fallback
    if llm is None:
        response = fallback
    else:
        try:
            response = llm.generate_json(
                system_prompt=render_prompt(
                    "actor-review-system.md",
                    actor_id=step_id,
                    role=role,
                    responsibilities="\n".join(f"- {item}" for item in responsibilities) or "- Preserve source-grounded, review-only output.",
                    prompt_details=prompt_details,
                ),
                user_prompt=json.dumps(
                    {
                        "actor_id": step_id,
                        "role": role,
                        "responsibilities": responsibilities,
                        "model_profile": profile,
                        "task": summary,
                        "context": redact_value(context),
                        "knowledge_context": knowledge_context_for_step(active_knowledge, step_id),
                        "output_contract": {
                            "required_fields": [
                                "summary",
                                "key_findings",
                                "review_questions",
                                "evidence_gaps",
                                "risk_flags",
                                "next_steps",
                                "confidence",
                                "review_only",
                                "source_refs",
                            ],
                            "source_ref_rule": "Use only supplied local source_refs or explicitly supplied public source URLs.",
                            "unknown_rule": "If evidence is absent, say unknown or review-required; never infer a financial fact.",
                        },
                        "fallback_shape": fallback,
                    },
                    sort_keys=True,
                    default=str,
                ),
                fallback=fallback,
            )
        except Exception as exc:
            if live_llm_requested(config):
                raise RuntimeError(f"Live LLM review failed for {step_id}: {exc}") from exc
            response = copy.deepcopy(fallback)
            response["llm_error"] = str(exc)
    if not isinstance(response, dict):
        response = copy.deepcopy(fallback)
    response.setdefault("actor_id", step_id)
    response.setdefault("llm_config", profile["llm_config"])
    response.setdefault("model", profile["model"])
    response.setdefault("runtime_model", profile["runtime_model"])
    response.setdefault("generated_at", utc_now_iso())
    return response

def llm_usage(llm: Any) -> dict[str, Any]:
    return {
        "provider": str(getattr(llm, "provider", "none")),
        "model": str(getattr(llm, "model", "none")),
        "calls": int(getattr(llm, "calls", 0) or 0),
        "fallback_calls": int(getattr(llm, "fallback_calls", 0) or 0),
        "input_tokens": int(getattr(llm, "input_tokens", 0) or 0),
        "output_tokens": int(getattr(llm, "output_tokens", 0) or 0),
        "total_tokens": int(getattr(llm, "total_tokens", 0) or 0),
        "estimated_tokens": int(getattr(llm, "estimated_tokens", 0) or 0),
    }

def usage_delta(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    delta = {"provider": after.get("provider", "none"), "model": after.get("model", "none")}
    for key in ("calls", "fallback_calls", "input_tokens", "output_tokens", "total_tokens", "estimated_tokens"):
        delta[key] = max(0, int(after.get(key, 0) or 0) - int(before.get(key, 0) or 0))
    return delta

def accumulate_llm_usage(ctx: dict[str, Any], delta: dict[str, Any]) -> dict[str, Any]:
    usage = ctx["state"].setdefault(
        "llm_usage",
        {
            "provider": delta.get("provider", "none"),
            "model": delta.get("model", "none"),
            "calls": 0,
            "fallback_calls": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "estimated_tokens": 0,
        },
    )
    usage["provider"] = delta.get("provider") or usage.get("provider", "none")
    usage["model"] = delta.get("model") or usage.get("model", "none")
    for key in ("calls", "fallback_calls", "input_tokens", "output_tokens", "total_tokens", "estimated_tokens"):
        usage[key] = int(usage.get(key, 0) or 0) + int(delta.get(key, 0) or 0)
    return usage

def effective_llm_usage(ctx: dict[str, Any]) -> dict[str, Any]:
    usage = copy.deepcopy(
        ctx["state"].get(
            "llm_usage",
            {
                "provider": str(getattr(ctx["llm"], "provider", "none")),
                "model": str(getattr(ctx["llm"], "model", "none")),
                "calls": 0,
                "fallback_calls": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
                "estimated_tokens": 0,
            },
        )
    )
    current_delta = usage_delta(ctx.get("step_llm_usage_before") or llm_usage(ctx["llm"]), llm_usage(ctx["llm"]))
    usage["provider"] = current_delta.get("provider") or usage.get("provider", "none")
    usage["model"] = current_delta.get("model") or usage.get("model", "none")
    for key in ("calls", "fallback_calls", "input_tokens", "output_tokens", "total_tokens", "estimated_tokens"):
        usage[key] = int(usage.get(key, 0) or 0) + int(current_delta.get(key, 0) or 0)
    return usage

def review_artifact(
    ctx: dict[str, Any],
    *,
    step_id: str,
    summary: str,
    context: dict[str, Any],
    source_refs: list[str],
    key_findings: list[str],
    review_questions: list[str],
    evidence_gaps: list[str],
    risk_flags: list[str],
    next_steps: list[str],
) -> dict[str, Any]:
    fallback = {
        "actor_id": step_id,
        "summary": summary,
        "key_findings": key_findings,
        "review_questions": review_questions,
        "evidence_gaps": evidence_gaps,
        "risk_flags": risk_flags,
        "next_steps": next_steps,
        "confidence": 0.68,
        "review_only": True,
        "source_refs": source_refs,
    }
    response = actor_review(
        ctx["config"],
        ctx["llm"],
        step_id,
        summary,
        context,
        fallback=fallback,
        prompt_details=load_prompt(REVIEW_PROMPT_FILES.get(step_id, "review-artifact-fields.md")),
        active_knowledge=ctx.get("active_knowledge"),
    )
    return normalize_review_response(response, fallback, source_refs)
