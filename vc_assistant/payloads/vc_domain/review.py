"""VC actor-review contexts, prompts, and review execution."""

from __future__ import annotations

from .common import *
from .knowledge import (
    RESEARCH_AGENT_PROMPT_FILES,
    REVIEW_AGENT_PROMPT_FILES,
    active_knowledge_reference,
    citation_ref_values,
    knowledge_rag_is_required,
    load_prompt,
    prompt_spec_from_markdown,
    public_knowledge_rag_state,
    rag_ref_values,
    validate_llm_rag_refs,
)
from .research_core import actor_review_config
from .runtime_tools import append_event, observed_operation, stable_text_hash

def build_actor_review_context(
    *,
    analyses: list[dict[str, Any]],
    company_work_queue: list[dict[str, Any]],
    research_coverage: dict[str, Any],
    method_coverage: dict[str, Any],
    processed_company_names: list[str],
    skipped_company_names: list[str],
    output_files: list[dict[str, Any]],
    active_knowledge: dict[str, Any] | None = None,
    knowledge_rag: dict[str, Any] | None = None,
    actor_rag_context: dict[str, Any] | None = None,
    max_context_chars: int = 6000,
) -> dict[str, Any]:
    company_summaries = []
    for analysis in analyses:
        company_summaries.append({
            "company_name": analysis["company_name"],
            "company_slug": analysis["company_slug"],
            "processing_status": analysis.get("processing_status"),
            "composite_score": analysis.get("composite_score"),
            "method_statuses": {method_id: method.get("status") for method_id, method in analysis.get("methods", {}).items()},
            "method_scores": {method_id: method.get("score") for method_id, method in analysis.get("methods", {}).items()},
            "method_evidence": {
                method_id: {
                    "memory_hook": method.get("memory_hook"),
                    "status_reason": (method.get("evidence_summary") or {}).get("status_reason"),
                    "evidence_ref_count": len(method.get("evidence_refs") or []),
                    "missing_evidence": method.get("missing_evidence") or [],
                    "assumptions": method.get("assumptions") or [],
                    "warnings": method.get("warnings") or [],
                }
                for method_id, method in analysis.get("methods", {}).items()
            },
            "missing_methods": (analysis.get("evidence_summary") or {}).get("missing_methods", []),
            "audit_warning_count": len((analysis.get("audit") or {}).get("warnings") or []),
            "research_reconciliation": {
                "confirmation_count": len((analysis.get("research_reconciliation") or {}).get("confirmations") or []),
                "contradiction_count": len((analysis.get("research_reconciliation") or {}).get("contradictions") or []),
                "missing_public_evidence_count": len((analysis.get("research_reconciliation") or {}).get("missing_public_evidence") or []),
            },
            "adaptive_research_plan": {
                "lane_ids": [lane.get("lane_id") for lane in (analysis.get("research_plan") or {}).get("lanes", [])],
                "github_url_count": len((analysis.get("research_plan") or {}).get("github_urls") or []),
                "known_public_url_count": len((analysis.get("research_plan") or {}).get("known_public_urls") or []),
                "signal_keys": sorted(
                    key
                    for key, value in ((analysis.get("research_plan") or {}).get("signals") or {}).items()
                    if value
                ),
            },
        })
    context = {
        "blueprint_id": BLUEPRINT_ID,
        "output_type": OUTPUT_TYPE,
        "report_only": True,
        "active_knowledge": active_knowledge or {},
        "knowledge_rag": public_knowledge_rag_state(knowledge_rag),
        "rag_context": actor_rag_context or {},
        "judge_rubric": list((active_knowledge or {}).get("judge_rubric") or JUDGE_RUBRIC),
        "decision_boundary": "reports include scores, assumptions, evidence, and warnings only; users make all investment decisions",
        "company_count": len(analyses),
        "processed_company_names": processed_company_names,
        "skipped_company_names": skipped_company_names,
        "company_work_queue": [
            {
                "company_name": item.get("company_name"),
                "company_slug": item.get("company_slug"),
                "status": item.get("status"),
                "document_count": item.get("document_count"),
            }
            for item in company_work_queue
        ],
        "company_summaries": company_summaries,
        "research_coverage": research_coverage,
        "method_coverage": method_coverage,
        "output_files": [
            {"kind": item.get("kind"), "path": item.get("path"), "company_slug": item.get("company_slug")}
            for item in output_files[:50]
        ],
        "privacy_controls": {
            "public_research_queries": "company names, domains, categories, and non-confidential public claims only",
            "local_document_text": "not included in actor-review context",
        },
        "actor_review_focus": [
            "judge whether adaptive research lanes matched company-specific evidence",
            "flag missing GitHub, docs, profile, pricing, traction, or market follow-ups when signals were present",
            "verify source quality labels separate confirmation, conflict, blocked, thin, technical, and market-context signals",
        ],
    }
    if len(json.dumps(context, default=str)) <= max_context_chars:
        context["context_json_chars"] = len(json.dumps(context, default=str))
        return context
    compact_company_summaries = []
    for item in company_summaries:
        compact_company_summaries.append({
            "company_name": item.get("company_name"),
            "company_slug": item.get("company_slug"),
            "processing_status": item.get("processing_status"),
            "composite_score": item.get("composite_score"),
            "method_statuses": item.get("method_statuses"),
            "method_scores": item.get("method_scores"),
            "missing_methods": item.get("missing_methods"),
            "audit_warning_count": item.get("audit_warning_count"),
            "research_reconciliation": item.get("research_reconciliation"),
            "adaptive_research_plan": item.get("adaptive_research_plan"),
        })
    rag_citations = (actor_rag_context or {}).get("citations") if isinstance(actor_rag_context, dict) else []
    compact_context = {
        "blueprint_id": BLUEPRINT_ID,
        "output_type": OUTPUT_TYPE,
        "report_only": True,
        "active_knowledge": active_knowledge_reference(active_knowledge or {}) if (active_knowledge or {}).get("content") else (active_knowledge or {}),
        "knowledge_rag": public_knowledge_rag_state(knowledge_rag),
        "rag_context": {
            "enabled": (actor_rag_context or {}).get("enabled") if isinstance(actor_rag_context, dict) else False,
            "status": (actor_rag_context or {}).get("status") if isinstance(actor_rag_context, dict) else "",
            "citation_count": len(rag_citations or []),
            "citations": rag_citations[:5] if isinstance(rag_citations, list) else [],
        },
        "judge_rubric": list((active_knowledge or {}).get("judge_rubric") or JUDGE_RUBRIC),
        "decision_boundary": "reports include scores, assumptions, evidence, and warnings only; users make all investment decisions",
        "company_count": len(analyses),
        "processed_company_names": processed_company_names,
        "skipped_company_names": skipped_company_names,
        "company_work_queue": context["company_work_queue"],
        "company_summaries": compact_company_summaries,
        "research_coverage": {
            "companies": (research_coverage or {}).get("companies", []),
            "generated_at": (research_coverage or {}).get("generated_at"),
        },
        "method_coverage": method_coverage,
        "output_files": context["output_files"][:30],
        "privacy_controls": context["privacy_controls"],
        "actor_review_focus": context["actor_review_focus"],
        "truncated_for_actor_review": True,
    }
    encoded = json.dumps(compact_context, default=str)
    if len(encoded) > max_context_chars:
        compact_context["output_files"] = compact_context["output_files"][:10]
        compact_context["actor_review_focus"] = compact_context["actor_review_focus"][:1]
    compact_context["context_json_chars"] = len(json.dumps(compact_context, default=str))
    return compact_context

def _context_engine_summary(state: dict[str, Any], max_chars: int) -> dict[str, Any]:
    summary_keys = {
        "summary",
        "compiled",
        "compiled_context",
        "context",
        "compressed",
        "compressed_context",
        "messages",
        "items",
        "facts",
    }
    if not isinstance(state, dict):
        return {"compiled_context": _truncate_for_prompt(state, max_chars)}
    selected = {key: value for key, value in state.items() if key in summary_keys}
    if not selected:
        selected = dict(state)
    return _truncate_for_prompt(selected, max_chars)

def _local_context_engine_state(context: dict[str, Any], *, run_id: str, max_context_chars: int) -> dict[str, Any]:
    if WorkingMemory is None or MemoryItem is None:
        raise RuntimeError("mn_context_engine_sdk local WorkingMemory helpers are unavailable")
    focus_id = f"{run_id}_vc_actor_review"
    payload = {
        "decision_boundary": context.get("decision_boundary"),
        "company_count": context.get("company_count"),
        "processed_company_names": context.get("processed_company_names", []),
        "skipped_company_names": context.get("skipped_company_names", []),
        "company_summaries": context.get("company_summaries", []),
        "method_coverage": context.get("method_coverage", {}),
        "rag_context": {
            "enabled": (context.get("rag_context") or {}).get("enabled") if isinstance(context.get("rag_context"), dict) else None,
            "status": (context.get("rag_context") or {}).get("status") if isinstance(context.get("rag_context"), dict) else None,
            "citation_count": len((context.get("rag_context") or {}).get("citations") or []) if isinstance(context.get("rag_context"), dict) else 0,
            "citations": ((context.get("rag_context") or {}).get("citations") or [])[:5] if isinstance(context.get("rag_context"), dict) else [],
        },
        "output_files": (context.get("output_files") or [])[:10],
        "privacy_controls": context.get("privacy_controls", {}),
        "actor_review_focus": context.get("actor_review_focus", [])[:2],
    }
    payload = _truncate_for_prompt(payload, max_context_chars)
    memory = WorkingMemory()
    item = MemoryItem(
        type="Fact",
        status="validated",
        source=BLUEPRINT_ID,
        confidence=0.82,
        content={
            "goal_id": focus_id,
            "artifact_type": "vc_actor_review_context",
            "payload": payload,
            "source_refs": [
                item.get("path")
                for item in context.get("output_files", [])
                if isinstance(item, dict) and item.get("path")
            ],
            "validation": {
                "review_only": True,
                "private_document_text_included": False,
                "persistent_storage": False,
            },
        },
    )
    memory.add(item)
    return {
        "backend": "mn_context_engine_sdk.WorkingMemory",
        "storage": "in_process_only",
        "persisted": False,
        "item_count": len(memory.to_dict().get("items") or []),
        "compiled_context": _truncate_for_prompt(payload, max_context_chars),
    }

def _bounded_actor_prompt_context(context: dict[str, Any], *, compression: dict[str, Any], max_context_chars: int) -> dict[str, Any]:
    rag_context = context.get("rag_context") if isinstance(context.get("rag_context"), dict) else {}
    compressed_state = compression.get("state") if isinstance(compression.get("state"), dict) else {}
    prompt_context = {
        "blueprint_id": BLUEPRINT_ID,
        "output_type": OUTPUT_TYPE,
        "report_only": True,
        "decision_boundary": context.get("decision_boundary"),
        "company_count": context.get("company_count"),
        "processed_company_names": context.get("processed_company_names", []),
        "skipped_company_names": context.get("skipped_company_names", []),
        "company_summaries": context.get("company_summaries", []),
        "method_coverage": context.get("method_coverage", {}),
        "rag_context": {
            "enabled": rag_context.get("enabled"),
            "status": rag_context.get("status"),
            "citation_count": len(rag_context.get("citations") or []),
            "citations": (rag_context.get("citations") or [])[:5],
        },
        "output_files": (context.get("output_files") or [])[:10],
        "privacy_controls": context.get("privacy_controls", {}),
        "actor_review_focus": context.get("actor_review_focus", [])[:2],
        "context_compression": {
            key: value
            for key, value in compression.items()
            if key not in {"state"}
        },
        "memory_boundary": {
            "rag_knowledge": "persistent Redis-backed knowledge index",
            "working_memory": "transient local prompt context; not written to Redis",
        },
    }
    if compressed_state:
        prompt_context["context_engine_summary"] = _context_engine_summary(compressed_state, max(1000, max_context_chars // 2))
        prompt_context["company_summaries"] = (prompt_context["company_summaries"] or [])[:5]
        prompt_context["method_coverage"] = _truncate_for_prompt(prompt_context["method_coverage"], max(800, max_context_chars // 6))
    encoded = json.dumps(prompt_context, default=str, ensure_ascii=False)
    if len(encoded) > max_context_chars:
        prompt_context["company_summaries"] = [
            {
                "company_name": item.get("company_name"),
                "company_slug": item.get("company_slug"),
                "processing_status": item.get("processing_status"),
                "composite_score": item.get("composite_score"),
                "missing_methods": item.get("missing_methods"),
                "audit_warning_count": item.get("audit_warning_count"),
            }
            for item in (prompt_context.get("company_summaries") or [])[:5]
            if isinstance(item, dict)
        ]
        prompt_context["method_coverage"] = _truncate_for_prompt(prompt_context.get("method_coverage", {}), 500)
        prompt_context["output_files"] = (prompt_context.get("output_files") or [])[:5]
        prompt_context["actor_review_focus"] = (prompt_context.get("actor_review_focus") or [])[:1]
    encoded = json.dumps(prompt_context, default=str, ensure_ascii=False)
    if len(encoded) > max_context_chars:
        prompt_context["context_engine_summary"] = _truncate_for_prompt(prompt_context.get("context_engine_summary", {}), max(600, max_context_chars // 3))
    prompt_context["context_json_chars"] = len(json.dumps(prompt_context, default=str, ensure_ascii=False))
    return prompt_context

def prepare_actor_review_prompt_context(
    *,
    run_id: str,
    context: dict[str, Any],
    config: dict[str, Any],
    run_dir: Path | None = None,
) -> dict[str, Any]:
    settings = actor_review_config(config)
    max_context_chars = int(settings["max_context_chars"])
    input_chars = len(json.dumps(context, default=str, ensure_ascii=False))
    compression: dict[str, Any] = {
        "enabled": False,
        "use_context_engine": bool(settings["use_context_engine"]),
        "working_memory_persist_to_redis": bool(settings["working_memory_persist_to_redis"]),
        "working_memory_storage": "local_prompt_only",
        "input_context_chars": input_chars,
        "token_budget": settings["context_token_budget"],
        "target_tokens": settings["context_target_tokens"],
    }
    if settings["working_memory_persist_to_redis"]:
        compression["warning"] = "working_memory_persist_to_redis=true is not supported for VC Assistant; using transient local working memory."
    if not settings["use_context_engine"]:
        compression["reason"] = "disabled"
        return _bounded_actor_prompt_context(context, compression=compression, max_context_chars=max_context_chars)
    with observed_operation(
        run_dir,
        phase="context_engine",
        operation="compile_actor_review_context",
        input_context_chars=input_chars,
        token_budget=settings["context_token_budget"],
        target_tokens=settings["context_target_tokens"],
    ) as op:
        try:
            state = _local_context_engine_state(context, run_id=run_id, max_context_chars=max_context_chars)
            compression.update({
                "enabled": True,
                "state": state if isinstance(state, dict) else {"compiled_context": state},
                "backend": "mn_context_engine_sdk.WorkingMemory",
                "persisted": False,
                "working_memory_storage": "in_process_only",
            })
            prompt_context = _bounded_actor_prompt_context(context, compression=compression, max_context_chars=max_context_chars)
            op.close("completed", enabled=True, persisted=False, output_context_chars=prompt_context["context_json_chars"])
            return prompt_context
        except Exception as exc:  # pragma: no cover - depends on optional runtime service
            compression["warning"] = str(exc)
            prompt_context = _bounded_actor_prompt_context(context, compression=compression, max_context_chars=max_context_chars)
            op.close("completed", enabled=False, warning=str(exc), output_context_chars=prompt_context["context_json_chars"])
            return prompt_context

def actor_prompt_spec(actor_id: str) -> dict[str, Any]:
    if actor_id in REVIEW_AGENT_PROMPT_FILES:
        return prompt_spec_from_markdown(REVIEW_AGENT_PROMPT_FILES[actor_id])
    for method_id, scorer_id in SCORER_AGENT_BY_METHOD.items():
        if actor_id == scorer_id:
            return prompt_spec_from_markdown("method-scorer-review.md", method_id=method_id)
    if actor_id in RESEARCH_AGENT_PROMPT_FILES:
        return prompt_spec_from_markdown("research-agent-review.md", actor_id=actor_id)
    return prompt_spec_from_markdown("generic-actor-review.md", actor_id=actor_id)

def build_actor_review_prompt(
    *,
    actor_id: str,
    actor_spec: dict[str, Any],
    context: dict[str, Any],
    knowledge_rag: dict[str, Any] | None,
) -> tuple[str, dict[str, Any]]:
    prompt_spec = actor_prompt_spec(actor_id)
    available_rag_refs = (context.get("rag_context") or {}).get("citations") if isinstance(context.get("rag_context"), dict) else []
    system_prompt = load_prompt(
        "actor-review-system.md",
        actor_id=actor_id,
        mission=prompt_spec["mission"],
    )
    return system_prompt, {
        "task": prompt_spec["mission"],
        "actor_id": actor_id,
        "configured_role": actor_spec.get("role") or actor_id,
        "configured_responsibilities": actor_spec.get("responsibilities") or [],
        "focus": prompt_spec.get("focus") or [],
        "rag_refs_required": knowledge_rag_is_required(knowledge_rag),
        "available_rag_refs": available_rag_refs,
        "context": context,
        "required_schema": {
            "summary": "short role-specific review summary",
            "findings": [
                {
                    "severity": "info|warning|error",
                    "message": "specific finding",
                    "company": "optional",
                    "method_id": "optional",
                    "evidence_ref": "optional",
                    "rag_refs": ["citation ref numbers used"],
                }
            ],
            "risks": ["role-specific residual risks"],
            "evidence_gaps": ["missing evidence or missing outputs"],
            "rag_refs": ["top-level citation ref numbers used"],
            "recommended_next_step": "one bounded next workflow action, no investment recommendation",
        },
    }

def default_actor_rag_refs(context: dict[str, Any]) -> list[Any]:
    rag_context = context.get("rag_context") if isinstance(context.get("rag_context"), dict) else {}
    return shared_default_actor_rag_refs({"rag_context": rag_context, "citations": citation_ref_values(rag_context)})

def not_llm_reviewed_actor_finding(actor_id: str, actor_spec: dict[str, Any]) -> dict[str, Any]:
    return {
        "actor_id": actor_id,
        "role": actor_spec.get("role") or actor_id,
        "responsibilities": actor_spec.get("responsibilities") or [],
        "summary": "Deterministic workflow artifact was preserved; this actor was not selected for live LLM review in the current throughput profile.",
        "findings": [],
        "risks": [],
        "evidence_gaps": [],
        "rag_refs": [],
        "recommended_next_step": "Review deterministic outputs and selected live actor reviews.",
        "provider": "not_llm_reviewed",
        "model": "not_llm_reviewed",
        "status": "not_llm_reviewed",
        "generated_at": utc_now_iso(),
    }

def run_vc_actor_reviews(
    *,
    config: dict[str, Any],
    llm: Any,
    actor_ids: list[str] | tuple[str, ...] | set[str],
    state: dict[str, Any],
    context: dict[str, Any],
    knowledge_rag: dict[str, Any] | None,
    event_sink: Path | None = None,
) -> dict[str, Any]:
    actor_specs = resolve_actor_specs(config, actor_ids=list(actor_ids))
    findings = state.setdefault("actor_findings", {})
    review_config = actor_review_config(config)
    selected_actor_ids = {actor_id for actor_id in review_config["llm_actor_ids"] if actor_id in set(actor_ids)}
    for actor_id in actor_ids:
        actor_id = str(actor_id)
        actor_spec = dict(actor_specs.get(actor_id) or {})
        if actor_id not in selected_actor_ids:
            findings[actor_id] = not_llm_reviewed_actor_finding(actor_id, actor_spec)
            if event_sink is not None:
                append_event(event_sink, "actor_activity", {"agent_id": actor_id, "status": "not_llm_reviewed", "summary": findings[actor_id]["summary"]})
            continue
        system_prompt, prompt = build_actor_review_prompt(
            actor_id=actor_id,
            actor_spec=actor_spec,
            context=context,
            knowledge_rag=knowledge_rag,
        )
        fallback = {
            "actor_id": actor_id,
            "summary": "Actor review unavailable; deterministic VC report artifacts were preserved.",
            "findings": [],
            "risks": [],
            "evidence_gaps": [],
            "rag_refs": [],
            "recommended_next_step": "Review deterministic outputs manually.",
            "confidence": 0.35,
        }
        with observed_operation(
            event_sink,
            phase="actor_review",
            operation=actor_id,
            agent_id=actor_id,
            prompt_hash=stable_text_hash(json.dumps(prompt, default=str)),
            prompt_chars=len(json.dumps(prompt, default=str)),
        ) as op:
            finding = llm.generate_json(system_prompt=system_prompt, user_prompt=json.dumps(prompt, default=str), fallback=fallback)
            op.close("completed", provider=finding.get("provider") if isinstance(finding, dict) else "", response_chars=len(json.dumps(finding, default=str)) if isinstance(finding, dict) else len(str(finding)))
        if not isinstance(finding, dict):
            raise RuntimeError(f"Actor {actor_id} returned non-object JSON.")
        if knowledge_rag_is_required(knowledge_rag) and not rag_ref_values(finding):
            refs = default_actor_rag_refs(context)
            if refs:
                finding["rag_refs"] = refs
                finding.setdefault("evidence_gaps", [])
                if isinstance(finding["evidence_gaps"], list):
                    finding["evidence_gaps"].append("Actor review omitted explicit RAG refs; refs were attached from the shared review context.")
        validate_llm_rag_refs(finding, knowledge_rag=knowledge_rag, stage=actor_id)
        finding.setdefault("actor_id", actor_id)
        finding.setdefault("role", actor_spec.get("role") or actor_id)
        finding.setdefault("responsibilities", actor_spec.get("responsibilities") or [])
        finding.setdefault("generated_at", utc_now_iso())
        findings[actor_id] = finding
        if event_sink is not None:
            append_event(event_sink, "actor_activity", {"agent_id": actor_id, "status": "completed", "summary": finding.get("summary")})
    return findings

