"""Evidence reconciliation, model review, and safety audit policy."""

from __future__ import annotations

from .common import *
from .knowledge import legal_knowledge_context_for_actor, load_legal_knowledge, prepare_legal_rag
from .runtime_services import fake_llm_requested
from .state import load_state, save_state

def issue_register(
    records: list[dict[str, Any]],
    invoice_packet: dict[str, Any],
    clause_packet: dict[str, Any],
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for item in invoice_packet.get("missing_fields") or []:
        issues.append(
            {
                "area": "invoice_bill_extraction",
                "severity": "medium",
                "source": item.get("source"),
                "issue": f"Missing payable fields: {', '.join(item.get('fields') or [])}",
                "review_owner": "human_ap_or_legal_reviewer",
            }
        )
    for missing in clause_packet.get("playbook_comparison", {}).get("missing_required_clause_types") or []:
        issues.append(
            {
                "area": "contract_clause_review",
                "severity": "high",
                "source": "contract packet",
                "issue": f"Required clause type not found: {missing}",
                "review_owner": "attorney",
            }
        )
    for record in records:
        if record.get("ocr_required"):
            issues.append(
                {
                    "area": "document_intake",
                    "severity": "medium",
                    "source": record.get("filename"),
                    "issue": "OCR is required before relying on this source.",
                    "review_owner": "document_reviewer",
                }
            )
    return issues

def effective_llm_config_name(
    config: dict[str, Any],
    actor_id: str,
    runtime_selection: dict[str, Any] | None = None,
) -> str:
    llm = config.get("llm") if isinstance(config.get("llm"), dict) else {}
    agents = llm.get("agents") if isinstance(llm.get("agents"), dict) else {}
    agent = agents.get(actor_id) if isinstance(agents.get(actor_id), dict) else {}
    profile_name = str(agent.get("llm_config") or llm.get("default_config") or "primary")

    # Heavy actors are authored with the medium/Nemotron profile, but a local
    # Mac may only advertise the small Gemma runtime. In that case the heavy
    # profile's strict JSON contract is not compatible with the selected model;
    # use the existing small-model contract instead of forcing strict parsing.
    if profile_name == "large" and str((runtime_selection or {}).get("selected_model") or "").lower() == "small":
        return "primary"
    return profile_name

def model_profiles_used(
    config: dict[str, Any],
    runtime_selection: dict[str, Any] | None = None,
) -> dict[str, dict[str, str]]:
    agents = (config.get("llm") or {}).get("agents") or {}
    configs = (config.get("llm") or {}).get("configs") or {}
    result = {}
    for step in AGENT_IDS:
        llm_config = effective_llm_config_name(config, step, runtime_selection)
        model = str((configs.get(llm_config) or {}).get("model") or (config.get("llm") or {}).get("model") or "unknown")
        result[step] = {"llm_config": llm_config, "model": model}
    return result

def llm_profile_config(
    config: dict[str, Any],
    actor_id: str,
    runtime_selection: dict[str, Any] | None = None,
) -> dict[str, Any]:
    llm = config.get("llm") if isinstance(config.get("llm"), dict) else {}
    profile_name = effective_llm_config_name(config, actor_id, runtime_selection)
    profiles = llm.get("configs") if isinstance(llm.get("configs"), dict) else {}
    profile = profiles.get(profile_name)
    return profile if isinstance(profile, dict) else {}

def configured_llm_review_agents(config: dict[str, Any]) -> list[str]:
    """Return only actors that need live reasoning after deterministic intake.

    Folder watching and document reading are deterministic stages in this
    blueprint. Calling the LLM again for those stages duplicated work and
    made a normal run exceed the declared runtime and token budgets.
    """
    llm = config.get("llm") if isinstance(config.get("llm"), dict) else {}
    configured = llm.get("review_agents")
    if isinstance(configured, list) and configured:
        candidates = [str(item) for item in configured if str(item)]
    else:
        candidates = list(DEFAULT_LLM_REVIEW_AGENTS)
    agents = llm.get("agents") if isinstance(llm.get("agents"), dict) else {}
    return [actor_id for actor_id in candidates if actor_id in agents]

def build_llm_client(config: dict[str, Any], payload: dict[str, Any], llm_client: Any | None) -> Any:
    if llm_client is not None:
        return llm_client
    if fake_llm_requested(config, payload):
        return DeterministicLLM()
    if get_actor_llm_client is None:
        raise RuntimeError(
            "Legal Assistant requires the shared live LLM client for normal runs. "
            "Install/enable mirrorneuron-litellm-communicate-skill or run with explicit fake/quick-test mode."
        )
    selection = select_default_model(config)
    try:
        client = get_actor_llm_client(config, None)
    except Exception as exc:
        raise RuntimeError(f"Unable to initialize shared live LLM client: {exc}") from exc
    if client is None or str(getattr(client, "provider", "")).lower() in {"fake", "mock", "deterministic", "test"}:
        raise RuntimeError("Shared live LLM client was unavailable for a normal Legal Assistant run.")
    setattr(client, "runtime_selection", selection)
    llm_config = config.get("llm") if isinstance(config.get("llm"), dict) else {}
    profile_name = str(os.environ.get("MN_LLM_CONFIG") or llm_config.get("default_config") or "primary")
    profiles = llm_config.get("configs") if isinstance(llm_config.get("configs"), dict) else {}
    profile = profiles.get(profile_name) if isinstance(profiles.get(profile_name), dict) else profiles.get("primary")
    if isinstance(profile, dict):
        for attribute, key in (
            ("timeout_seconds", "timeout_seconds"),
            ("max_tokens", "max_tokens"),
            ("num_retries", "num_retries"),
            ("retry_backoff_seconds", "retry_backoff_seconds"),
        ):
            if key in profile and hasattr(client, attribute):
                setattr(client, attribute, profile[key])
        if hasattr(client, "strict"):
            setattr(client, "strict", bool(profile.get("strict_json", False)))
    return client

def llm_generate(
    config: dict[str, Any],
    llm: Any,
    *,
    actor_id: str,
    actor_spec: dict[str, Any],
    fallback: dict[str, Any],
    context: dict[str, Any],
    knowledge_context: dict[str, Any],
) -> dict[str, Any]:
    if llm is None:
        llm = DeterministicLLM()
    runtime_selection = getattr(llm, "runtime_selection", {})
    profile = model_profiles_used(config, runtime_selection).get(actor_id) or {}
    role = str(actor_spec.get("role") or actor_id.replace("_", " ").title())
    responsibilities = [str(item) for item in actor_spec.get("responsibilities") or [] if str(item)]
    prompt_details = load_prompt(REVIEW_PROMPT_FILES.get(actor_id, "review-artifact-fields.md"))
    output_contract = {
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
        "optional_analysis_fields": [
            "clause_findings",
            "issue_findings",
            "deterministic_checks",
            "analysis_scope",
        ],
        "field_shapes": {
            "clause_findings": [
                "clause_type",
                "status",
                "source_ref",
                "locator",
                "observed_language",
                "affected_party",
                "bounded_implication",
                "uncertainty",
                "attorney_question",
            ],
            "issue_findings": [
                "area",
                "severity",
                "source_refs",
                "issue",
                "owner",
                "evidence_needed",
            ],
        },
        "source_ref_rule": "Use only supplied local source refs or the bundled legal playbook reference.",
        "unknown_rule": "If evidence is absent, say unknown, not found, ambiguous, or review required; never infer a legal or payable fact.",
    }
    if hasattr(llm, "generate_json"):
        profile_config = llm_profile_config(config, actor_id, runtime_selection)
        previous_values: dict[str, Any] = {}
        for attribute, key in (
            ("timeout_seconds", "timeout_seconds"),
            ("max_tokens", "max_tokens"),
            ("num_retries", "num_retries"),
            ("retry_backoff_seconds", "retry_backoff_seconds"),
        ):
            if key in profile_config and hasattr(llm, attribute):
                previous_values[attribute] = getattr(llm, attribute)
                setattr(llm, attribute, profile_config[key])
        if hasattr(llm, "strict") and "strict_json" in profile_config:
            previous_values["strict"] = getattr(llm, "strict")
            setattr(llm, "strict", bool(profile_config["strict_json"]))
        try:
            response = llm.generate_json(
                system_prompt=render_prompt(
                    "actor-review-system.md",
                    actor_id=actor_id,
                    role=role,
                    responsibilities="\n".join(f"- {item}" for item in responsibilities) or "- Preserve source-grounded, review-only output.",
                    prompt_details=prompt_details,
                ),
                user_prompt=json.dumps(
                    {
                        "actor_id": actor_id,
                        "role": role,
                        "responsibilities": responsibilities,
                        "model_profile": profile,
                        "context": redact_value(context),
                        "knowledge_context": knowledge_context,
                        "output_contract": output_contract,
                        "fallback_shape": fallback,
                    },
                    sort_keys=True,
                    default=str,
                )[:9000],
                fallback=fallback,
            )
            return response if isinstance(response, dict) else fallback
        finally:
            for attribute, value in previous_values.items():
                setattr(llm, attribute, value)
    return fallback

def run_actor_reviews(
    config: dict[str, Any],
    llm_client: Any | None,
    context: dict[str, Any],
    knowledge_context: dict[str, Any],
    rag_state: dict[str, Any],
) -> dict[str, Any]:
    llm = llm_client or DeterministicLLM()
    actor_findings: dict[str, Any] = {}
    agents = (config.get("llm") or {}).get("agents") or {}
    for actor_id in configured_llm_review_agents(config):
        spec = agents[actor_id]
        fallback = {
            "actor_id": actor_id,
            "role": spec.get("role") or actor_id,
            "llm_config": spec.get("llm_config") or "primary",
            "summary": f"{spec.get('role') or actor_id} reviewed the local evidence packet.",
            "key_findings": [],
            "review_questions": [],
            "evidence_gaps": [],
            "risk_flags": [],
            "next_steps": ["Review supplied source evidence before downstream use."],
            "confidence": 0.72,
            "review_only": True,
            "source_refs": [],
            "analysis_scope": ["source-grounded review only"],
            "clause_findings": [],
            "issue_findings": [],
            "deterministic_checks": [],
            "findings": [
                "Keep the packet review-only.",
                "Preserve source references for every extracted value.",
                "Escalate legal, payment, signature, or external-sharing actions for human approval.",
            ],
        }
        actor_knowledge = legal_knowledge_context_for_actor(knowledge_context, rag_state, actor_id)
        finding = llm_generate(
            config,
            llm,
            actor_id=actor_id,
            actor_spec=spec,
            fallback=fallback,
            context=context,
            knowledge_context=actor_knowledge,
        )
        finding.setdefault(
            "knowledge_context",
            {
                "status": actor_knowledge.get("rag_status"),
                "query": actor_knowledge.get("query"),
                "citations": actor_knowledge.get("citations") or [],
                "path": actor_knowledge.get("path"),
                "sha256": actor_knowledge.get("sha256"),
            },
        )
        actor_findings[actor_id] = finding
    return actor_findings

def llm_usage(llm_client: Any | None, actor_findings: dict[str, Any]) -> dict[str, Any]:
    return {
        "provider": getattr(llm_client, "provider", "fake"),
        "model": getattr(llm_client, "model", "deterministic-legal-assistant"),
        "calls": int(getattr(llm_client, "calls", len(actor_findings))),
        "fallback_calls": int(getattr(llm_client, "fallback_calls", 0)),
        "input_tokens": int(getattr(llm_client, "input_tokens", 0) or 0),
        "output_tokens": int(getattr(llm_client, "output_tokens", 0) or 0),
        "total_tokens": int(getattr(llm_client, "total_tokens", 0) or 0),
        "estimated_tokens": int(getattr(llm_client, "estimated_tokens", 0) or 0),
        "runtime_selection": getattr(llm_client, "runtime_selection", {}),
    }


def reconcile_evidence(ctx: dict[str, Any], **_options: Any) -> dict[str, Any]:
    state = load_state(ctx)
    issues = issue_register(state.get("records") or [], state.get("invoice_packet") or {}, state.get("clause_packet") or {})
    for record in state.get("records") or []:
        text = str(record.get("text") or "").lower()
        if "payment instruction change" in text or ("new account" in text and "payment" in text):
            issues.append({
                "area": "payment_controls",
                "severity": "high",
                "source": record.get("filename"),
                "issue": "Payment-instruction change is not supported by an authenticated amendment or trusted-channel verification.",
                "review_owner": "accounts_payable_and_legal_reviewer",
                "required_control": "Quarantine the change and independently verify it using previously trusted supplier contact information.",
            })
    state["issues"] = issues
    save_state(ctx, state, "legal_review_state.json")
    return {"issue_count": len(issues)}


def audit_review(ctx: dict[str, Any], **_options: Any) -> dict[str, Any]:
    state = load_state(ctx)
    records = state.get("records") or []
    llm = build_llm_client(ctx["config"], ctx["payload"], None)
    knowledge = load_legal_knowledge(Path(ctx["blueprint_dir"]))
    rag = prepare_legal_rag(ctx["config"], Path(ctx["blueprint_dir"]), knowledge)
    actor_context = {
        "document_count": len(records),
        "invoice_packet": state.get("invoice_packet") or {},
        "clause_packet": state.get("clause_packet") or {},
        "issue_count": len(state.get("issues") or []),
        "evidence": (state.get("evidence") or [])[:8],
        "review_policy": ctx["payload"].get("review_policy") or {},
        "document_ingestion": {"ocr": state.get("ocr_status") or {}, "source_refs": [record.get("filename") for record in records]},
        "knowledge_rag": {"status": rag.get("status"), "warnings": rag.get("warnings") or []},
    }
    state.update({
        "knowledge": knowledge,
        "rag": {key: value for key, value in rag.items() if not str(key).startswith("_")},
        "actor_findings": run_actor_reviews(ctx["config"], llm, actor_context, knowledge, rag),
    })
    state["llm_usage"] = llm_usage(llm, state["actor_findings"])
    save_state(ctx, state, "legal_review_state.json")
    return {"actor_count": len(state["actor_findings"])}


__all__ = ["audit_review", "reconcile_evidence"]
