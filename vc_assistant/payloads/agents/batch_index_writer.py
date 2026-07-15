from __future__ import annotations

from typing import Any

from mn_blueprint_support import llm_usage
from mn_prototype_artifact_finalizer_agent import (
    ArtifactBundle,
    ArtifactFinalizerSpec,
    ArtifactWrite,
    create_agent as create_artifact_finalizer,
)
from mn_sdk.blueprint_support import (
    bounded_int,
    elapsed_ms_from_started_at,
    observation_trace_summary,
    read_workflow_state,
    step_result,
    utc_now_iso,
    write_json,
)
from runtime.runtime import (
    BLUEPRINT_ID,
    BLUEPRINT_NAME,
    KNOWLEDGE_PLAYBOOK_RELATIVE_PATH,
    METHOD_IDS,
    OUTPUT_TYPE,
    RECOMMENDED_ACTION,
    RESEARCH_STAGE_IDS,
    WORKFLOW_STEP_IDS,
    active_knowledge_reference,
    actor_review_config,
    append_event,
    build_artifact_quality_report,
    build_cache_policy_summary,
    build_company_evidence_summaries,
    build_method_coverage,
    build_research_coverage,
    build_run_health_report,
    company_worker_count,
    ensure_all_actor_findings,
    flattened_sources,
    load_vc_knowledge,
    normalized_actor_review_warnings,
    observed_operation,
    normalized_research_ledger,
    persist_action_budget_state,
    processed_and_skipped_company_names,
    public_knowledge_rag_state,
    run_step_actor_review,
    scoring_worker_count,
    write_actor_review_warnings_state,
)

def run_batch_index_writer_step(ctx: dict[str, Any], *, llm_client: Any | None = None) -> dict[str, Any]:
    store = ctx["state_store"]
    company_records = store.read_object("company_records.json")
    company_work_queue = store.read_list("company_work_queue.json")
    analyses = sorted(
        (analysis for analysis in store.list_entity_objects("analyses").values() if analysis),
        key=lambda analysis: analysis.get("company_slug") or "",
    )
    research_ledgers = {
        analysis["company_name"]: normalized_research_ledger(
            store.read_entity_object("research_ledgers", analysis["company_name"])
        )
        for analysis in analyses
    }
    output_files = read_workflow_state(ctx["run_dir"], "output_files.json", []) or []
    output_files = [item for item in output_files if isinstance(item, dict)]
    services = ctx["services"]
    active_knowledge = services.get("active_knowledge") or load_vc_knowledge(ctx["blueprint_dir"])
    knowledge_rag = services.get("knowledge_rag") or {}
    run_step_actor_review(ctx, "batch_index_writer", services, llm_client=llm_client)
    action_ledger = persist_action_budget_state(ctx, services["action_budget"])
    actor_findings = ensure_all_actor_findings(ctx)
    actor_review_warnings = normalized_actor_review_warnings(ctx, actor_findings)
    write_actor_review_warnings_state(ctx, actor_review_warnings)
    processed_company_names, skipped_company_names = processed_and_skipped_company_names(company_work_queue)
    research_coverage = build_research_coverage(research_ledgers)
    method_coverage = build_method_coverage(analyses)
    cache_policy_summary = build_cache_policy_summary(
        company_work_queue,
        processed_company_names=processed_company_names,
        skipped_company_names=skipped_company_names,
    )
    artifact_quality = build_artifact_quality_report(
        analyses=analyses,
        company_records=company_records,
        research_ledgers=research_ledgers,
        output_files=output_files,
        knowledge_rag=knowledge_rag,
        actor_findings=actor_findings,
        actor_review_settings=actor_review_config(ctx["config"]),
    )
    observation_summary = observation_trace_summary(ctx["run_dir"])
    run_health = build_run_health_report(
        run_id=ctx["run_id"],
        started_at=ctx["started_at"],
        elapsed_ms=elapsed_ms_from_started_at(ctx["started_at"]),
        artifact_quality=artifact_quality,
        observation_summary=observation_summary,
        action_ledger=action_ledger,
        knowledge_rag=knowledge_rag,
        research_ledgers=research_ledgers,
        cache_policy_summary=cache_policy_summary,
        actor_review_warnings=actor_review_warnings,
        actor_review_settings=actor_review_config(ctx["config"]),
        llm_limiter=services["llm_limiter"],
    )
    budget_warnings = []
    if action_ledger["exhausted"]:
        budget_warnings.append(
            {
                "kind": "budget",
                "status": "budget_exhausted",
                "message": "The VC Assistant action budget was exhausted; later research, financial-tool, or actor-review calls may be partial.",
            }
        )
    knowledge_rag_warnings = list(knowledge_rag.get("warnings") or [])
    company_evidence_summaries = build_company_evidence_summaries(analyses, company_records, research_ledgers)
    final_artifact = {
        "type": OUTPUT_TYPE,
        "executive_summary": f"{BLUEPRINT_NAME} prepared score-only VC heuristic reports for {len(analyses)} startup companies; {len(skipped_company_names)} unchanged companies used cached reports.",
        "recommended_action": RECOMMENDED_ACTION,
        "confidence": 0.74 if any(item["composite_score"] is not None for item in analyses) else 0.35,
        "evidence": [record for records in company_records.values() for record in records[:5]],
        "next_steps": [
            "Review each company subfolder before deciding what to diligence next.",
            "Check insufficient_evidence method sections and add source documents where needed.",
            "Use public source refs only as context; verify material claims independently.",
        ],
        "source_refs": ["inputs.json", "events.jsonl", "llm_rag_trace.jsonl", "result.json", "final_artifact.json", "action_ledger.json", "artifact_quality.json", "run_health.json", "company_index.json", KNOWLEDGE_PLAYBOOK_RELATIVE_PATH],
        "active_knowledge": active_knowledge_reference(active_knowledge),
        "knowledge_rag": public_knowledge_rag_state(knowledge_rag),
        "research_summary": {
            "company_count": len(research_ledgers),
            "processed_company_count": len(processed_company_names),
            "skipped_company_count": len(skipped_company_names),
            "privacy_policy": "no confidential excerpts in public research queries",
            "stage_ids": RESEARCH_STAGE_IDS,
            "coverage": research_coverage,
            "knowledge_rag": public_knowledge_rag_state(knowledge_rag),
        },
        "research_sources": [source for ledger in research_ledgers.values() for source in flattened_sources(ledger)],
        "company_evidence_summaries": company_evidence_summaries,
        "research_warnings": [*budget_warnings, *knowledge_rag_warnings],
        "actor_review_warnings": actor_review_warnings,
        "report_only": True,
        "company_reports": analyses,
        "method_ids": METHOD_IDS,
        "workflow_step_ids": WORKFLOW_STEP_IDS,
        "company_work_queue": company_work_queue,
        "cache_policy": cache_policy_summary,
        "method_coverage": method_coverage,
        "artifact_quality": artifact_quality,
        "run_health": {
            "status": run_health["status"],
            "warning_count": len(run_health["warnings"]),
            "failure_count": len(run_health["failures"]),
            "elapsed_ms": run_health["elapsed_ms"],
            "artifact": "run_health.json",
        },
        "parallel_execution": {
            "max_company_workers": company_worker_count(ctx["config"], len(company_records)),
            "max_stage_workers": bounded_int((ctx["config"].get("internet_research") or {}).get("max_stage_workers"), default=len(RESEARCH_STAGE_IDS), maximum=len(RESEARCH_STAGE_IDS)),
            "max_scoring_workers": scoring_worker_count(ctx["config"]),
            "llm_backpressure": services["llm_limiter"].config_summary(),
            "company_processing_order": [analysis["company_slug"] for analysis in analyses],
        },
        "actor_review": {
            "llm_actor_ids": actor_review_config(ctx["config"])["llm_actor_ids"],
            "max_context_chars": actor_review_config(ctx["config"])["max_context_chars"],
            "context_json_chars": None,
            "prompt_context_json_chars": None,
            "context_compression": {"distributed_by_workflow_step": True},
        },
        "observability": observation_summary,
        "memory_boundary": {
            "rag_knowledge": {
                "storage": "redis_vector_index",
                "purpose": "durable playbook and method knowledge used to do the VC job",
                "namespace": (knowledge_rag.get("config") or {}).get("namespace") if isinstance(knowledge_rag.get("config"), dict) else "",
            },
            "working_memory": {
                "storage": "local_artifacts_and_prompt_context",
                "persist_to_redis": False,
                "purpose": "transient browser/tool observations and actor-review context",
            },
        },
        "monitor_state": {
            "mode": "folder_monitoring",
            "cycles_completed": 1,
            "max_cycles": ctx["max_cycles"],
            "processed_company_count": len(processed_company_names),
            "skipped_company_count": len(skipped_company_names),
            "watch_state": read_workflow_state(ctx["run_dir"], "watch_state.json", {}),
        },
        "output_files": output_files,
        "actor_findings": actor_findings,
        "llm_usage": llm_usage(services.get("llm")) if services.get("llm") is not None else {"provider": "none", "model": "none", "calls": 0},
        "action_ledger": action_ledger,
    }
    root_output_files = [
        {"kind": "final_artifact_json", "path": str(ctx["output_folder"] / "final_artifact.json")},
        {"kind": "action_ledger_json", "path": str(ctx["output_folder"] / "action_ledger.json")},
        {"kind": "artifact_quality_json", "path": str(ctx["output_folder"] / "artifact_quality.json")},
        {"kind": "run_health_json", "path": str(ctx["output_folder"] / "run_health.json")},
    ]
    trace_path = ctx["run_dir"] / "llm_rag_trace.jsonl"
    trace_output_path = ctx["output_folder"] / "llm_rag_trace.jsonl"
    if trace_path.exists():
        root_output_files.append({"kind": "llm_rag_trace_jsonl", "path": str(trace_output_path)})
    final_artifact["output_files"] = [*output_files, *root_output_files]
    result = {"run_id": ctx["run_id"], "blueprint_id": BLUEPRINT_ID, "status": "completed", "final_artifact": final_artifact}

    append_event(ctx["run_dir"], "blueprint_phase_completed", {"phase": "running_worker", "component": BLUEPRINT_ID})
    append_event(ctx["run_dir"], "human_input_requested", {"mode": "approval_required", "reason": "Reports contain heuristic investment-analysis scores for human review only."})
    append_event(ctx["run_dir"], "blueprint_phase_started", {"phase": "writing_artifacts", "component": BLUEPRINT_ID})
    writes = [
        ArtifactWrite("final_artifact.json", final_artifact, destination="both"),
        ArtifactWrite("action_ledger.json", action_ledger, destination="both"),
        ArtifactWrite("artifact_quality.json", artifact_quality, destination="both"),
        ArtifactWrite("run_health.json", run_health, destination="both"),
        ArtifactWrite("result.json", result, destination="run"),
    ]
    def artifact_event_writer(run_dir, event_type, payload):
        event_payload = dict(payload)
        path = str(event_payload.get("path") or "")
        if path.startswith(str(run_dir) + "/"):
            event_payload["path"] = str(path[len(str(run_dir)) + 1 :])
        append_event(run_dir, event_type, event_payload)

    finalizer = create_artifact_finalizer(
        ArtifactFinalizerSpec(
            compose=lambda _context, **_options: ArtifactBundle(
                final_artifact=final_artifact,
                writes=tuple(writes),
                result=result,
            ),
            step_id="batch_index_writer",
            event_writer=artifact_event_writer,
            result_builder=lambda context, _result, **_options: step_result(
                context,
                "batch_index_writer",
                final_artifact=final_artifact,
            ),
        )
    )
    with observed_operation(
        ctx["run_dir"],
        phase="writing_artifacts",
        operation="write_final_outputs",
        output_file_count=len(final_artifact["output_files"]),
    ):
        finalized_result = finalizer(ctx)
    if trace_path.exists():
        create_artifact_finalizer(
            ArtifactFinalizerSpec(
                compose=lambda _context, **_options: ArtifactBundle(
                    final_artifact=final_artifact,
                    writes=(
                        ArtifactWrite(
                            "llm_rag_trace.jsonl",
                            trace_path.read_bytes(),
                            kind="bytes",
                            destination="output",
                        ),
                    ),
                ),
                event_writer=artifact_event_writer,
            )
        )(ctx)
        append_event(ctx["run_dir"], "artifact_written", {"path": "llm_rag_trace.jsonl"})
    append_event(ctx["run_dir"], "blueprint_phase_completed", {"phase": "writing_artifacts", "component": BLUEPRINT_ID})
    append_event(ctx["run_dir"], "blueprint_phase_completed", {"phase": "completed", "component": BLUEPRINT_ID})
    write_json(ctx["run_dir"] / "run.json", {"run_id": ctx["run_id"], "blueprint_id": BLUEPRINT_ID, "status": "completed", "completed_at": utc_now_iso()})
    return finalized_result
