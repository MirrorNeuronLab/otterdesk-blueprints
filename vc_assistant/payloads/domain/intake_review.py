"""Optional specialist review policy on the native block context."""

from mn_sdk.blueprint_support import write_workflow_state
from mn_sdk.integrations.block_llm import DurableJsonModel

from .common import BLUEPRINT_ID, OUTPUT_TYPE
from .knowledge import (
    active_knowledge_reference,
    public_knowledge_rag_state, require_ready_rag, retrieve_knowledge_rag_context,
    knowledge_rag_is_required,
)
from .research_core import actor_review_config
from .research_services import research_resources
from .review import run_vc_actor_reviews
from .runtime_tools import llm_requires_live, append_event


def review_snapshot(block, state, role):
    if role not in actor_review_config(block.config).get("llm_actor_ids", []):
        return
    block.check()
    run_dir = block.store.run_dir
    resources = research_resources(block, state, role)
    knowledge, rag, budget = resources.knowledge, resources.rag, resources.budget
    def prepare_context():
        selected = retrieve_knowledge_rag_context(knowledge_rag=rag,
            query=f"{role} {block.step_id} VC workflow quality evidence grounding scoring research report-only boundary",
            stage=role, run_dir=run_dir)
        require_ready_rag(rag, stage=role, context=selected, min_citations=1, run_dir=run_dir)
        context = {
            "blueprint_id": BLUEPRINT_ID, "workflow_step_id": block.step_id, "agent_id": role,
            "output_type": OUTPUT_TYPE, "report_only": True,
            "decision_boundary": "reports include scores, assumptions, evidence, and warnings only; users make all investment decisions",
            "state_summary": {"document_file_count": len(state["files"]),
                "company_record_count": len(state.get("records", {})),
                "queued_company_count": len(state.get("queue", [])),
                "analysis_count": len(state.get("cached", {}).get("analyses", {})),
                "companies": sorted(state.get("records", {})),
                "queued_statuses": sorted({item["status"] for item in state.get("queue", [])})},
            "active_knowledge": active_knowledge_reference(knowledge),
            "knowledge_rag": public_knowledge_rag_state(rag),
            "rag_context": {key: selected[key] for key in ("status", "context", "citations") if key in selected},
            "privacy_controls": {"public_research_queries": "company names, domains, categories, and non-confidential public claims only",
                "local_document_text": "not included in actor-review context"},
        }
        from .text_memory import snapshot_memory_context
        context = snapshot_memory_context(block, state, context, role=role)
        return {"context": context, "memory_witnesses": state.get("memory_witnesses", {})}

    path = block.root + "/actor-review-context.json"
    reference = block.freeze_checkpoint(path, prepare_context)
    frozen = block.read_checkpoint(reference, expected_path=path)
    context = frozen["context"]
    state["memory_witnesses"] = frozen["memory_witnesses"]
    state.setdefault("review_contexts", {})[role] = reference.to_dict()
    model = DurableJsonModel(block, resources.model, scope=f"intake-review:{role}")
    findings = dict(state.get("actor_findings") or {})
    warnings = list(state.get("actor_review_warnings") or [])
    try:
        result = run_vc_actor_reviews(config=block.config, llm=model, actor_ids=[role],
            state={"actor_findings": findings}, context=context, knowledge_rag=rag, event_sink=run_dir)
        findings.update(result)
    except Exception as exc:
        if llm_requires_live(block.config) or knowledge_rag_is_required(rag):
            raise
        from mn_actor_review_skill import actor_review_unavailable_findings
        findings.update(actor_review_unavailable_findings([role], exc,
            summary="Actor review unavailable; deterministic VC report artifacts were preserved.",
            finding_message="LLM actor review failed after deterministic reports were generated."))
        warnings.append({"kind": "actor_review", "status": "actor_review_unavailable",
            "message": "Specialist actor review was unavailable; deterministic evidence is preserved.",
            "error": str(exc), "affected_actor_count": 1})
        append_event(run_dir, "tool_call_failed", {"tool": "actor_llm", "status": "actor_review_unavailable", "agent_id": role})
    finally:
        state["action_ledger"] = budget.summary(include_actions=True)
        write_workflow_state(run_dir, "action_ledger.json", state["action_ledger"])
    state.update(actor_findings=findings, actor_review_warnings=warnings)
    write_workflow_state(run_dir, "actor_findings.json", findings)
    write_workflow_state(run_dir, "actor_review_warnings.json", warnings)


def complete_findings(block, state):
    from .common import AGENT_IDS, resolve_actor_specs, shared_normalize_actor_review_warnings
    from .review import not_llm_reviewed_actor_finding

    specs = resolve_actor_specs(block.config)
    findings = state.setdefault("actor_findings", {})
    for role in AGENT_IDS:
        findings.setdefault(role, not_llm_reviewed_actor_finding(role, dict(specs.get(role) or {})))
    unavailable = [finding for finding in findings.values() if finding.get("provider") == "actor_review_unavailable"]
    if unavailable:
        state["actor_review_warnings"] = [{"kind": "actor_review", "status": "actor_review_unavailable",
            "message": "One or more LLM actor reviews failed after deterministic reports were generated; report artifacts were preserved.",
            "error": str(unavailable[0].get("error") or ""), "affected_actor_count": len(unavailable)}]
    else:
        state["actor_review_warnings"] = shared_normalize_actor_review_warnings(findings) or state.get("actor_review_warnings", [])
