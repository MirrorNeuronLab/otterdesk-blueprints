"""Bundled legal playbook and optional retrieval context."""

from .common import *


LEGAL_RAG_QUERIES = {
    "legal_folder_watcher": "legal document intake source traceability privacy and supported evidence",
    "legal_document_reader": "OCR status document classification and source quality for legal review",
    "invoice_bill_extractor": "invoice fields payment terms totals source references and payable blockers",
    "payable_field_validator": "invoice validation missing fields arithmetic consistency and payment controls",
    "contract_clause_extractor": "contract clause taxonomy source snippets defined terms and cross references",
    "contract_playbook_comparator": "contract playbook comparison missing clauses indemnity termination liability assignment and review questions",
    "legal_evidence_reconciler": "legal evidence reconciliation contradictions source hierarchy issue ownership and confidence",
    "legal_review_auditor": "legal review audit privacy privilege deterministic invariance and blocked actions",
    "legal_reporter": "legal report quality evidence traceability bounded next steps and review-only language",
}
LEGAL_RAG_RUN_QUERY = (
    "legal invoice and contract review evidence hierarchy, clause taxonomy, playbook comparison, "
    "privacy and privilege, reconciliation, and human approval boundaries"
)

def load_legal_knowledge(blueprint_root: Path) -> dict[str, Any]:
    playbook_path = blueprint_root / "payloads" / "knowledge" / "legal_playbook.md"
    content = playbook_path.read_text(encoding="utf-8") if playbook_path.exists() else ""
    return {
        "id": "legal_assistant_playbook",
        "title": "Legal Assistant Evidence And Review Playbook",
        "path": str(playbook_path),
        "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest() if content else "",
        "content": content[:12000],
        "judge_rubric": [
            "clause_or_field_accuracy",
            "evidence_traceability",
            "deterministic_output_invariance",
            "assumption_clarity",
            "missing_evidence_honesty",
            "privacy_and_privilege_handling",
            "review_only_language",
            "actionability_without_unauthorized_action",
        ],
        "grounding_rule": "Use the playbook as a review taxonomy and safety boundary, never as governing law or a substitute for qualified counsel.",
    }

def prepare_legal_rag(config: dict[str, Any], blueprint_root: Path, knowledge: dict[str, Any]) -> dict[str, Any]:
    knowledge_config = config.get("knowledge_rag") if isinstance(config.get("knowledge_rag"), dict) else {}
    if prepare_blueprint_knowledge_rag is None:
        return {
            "enabled": bool(knowledge_config.get("enabled")),
            "status": "skill_unavailable",
            "warnings": ["mirrorneuron-rag-skill is unavailable; bundled playbook context remains available."],
            "config": knowledge_config,
        }
    try:
        return prepare_blueprint_knowledge_rag(
            blueprint_id=BLUEPRINT_ID,
            blueprint_dir=blueprint_root,
            config={"knowledge_rag": knowledge_config},
            active_knowledge=knowledge,
        )
    except Exception as exc:  # pragma: no cover - depends on local embedding runtime
        return {
            "enabled": bool(knowledge_config.get("enabled")),
            "status": "knowledge_rag_failed",
            "warnings": [{"kind": "knowledge_rag", "message": "RAG preparation failed; bundled playbook context remains available.", "error": str(exc)}],
            "config": knowledge_config,
        }

def legal_knowledge_context_for_actor(
    knowledge: dict[str, Any],
    rag_state: dict[str, Any],
    actor_id: str,
) -> dict[str, Any]:
    query = LEGAL_RAG_QUERIES.get(actor_id, "legal contract review evidence and human approval boundaries")
    base = {
        "id": knowledge.get("id"),
        "title": knowledge.get("title"),
        "path": knowledge.get("path"),
        "sha256": knowledge.get("sha256"),
        "judge_rubric": list(knowledge.get("judge_rubric") or []),
        "grounding_rule": knowledge.get("grounding_rule"),
        "rag_status": rag_state.get("status") or "not_started",
        "rag_warnings": list(rag_state.get("warnings") or []),
        "query": query,
        "context": "",
        "citations": [],
        "chunks": [],
    }
    rag_config = rag_state.get("_rag_config") if isinstance(rag_state, dict) else None
    if build_rag_context is not None and rag_state.get("status") == "ready" and rag_config is not None:
        try:
            retrieved = rag_state.get("_shared_retrieval")
            if not isinstance(retrieved, dict):
                retrieved = build_rag_context(
                    LEGAL_RAG_RUN_QUERY,
                    rag_config,
                    max_chars=int((rag_state.get("config") or {}).get("max_context_chars") or 4500),
                )
                rag_state["_shared_retrieval"] = retrieved
            if retrieved.get("error"):
                raise RuntimeError(str(retrieved["error"]))
            base.update(
                {
                    "context": retrieved.get("context") or "",
                    "citations": retrieved.get("citations") or [],
                    "chunks": retrieved.get("chunks") or [],
                    "backend": retrieved.get("backend"),
                    "embedding_model": retrieved.get("embedding_model"),
                }
            )
            return base
        except Exception as exc:  # pragma: no cover - depends on local embedding runtime
            rag_state["_shared_retrieval"] = {"error": str(exc)}
            base["rag_status"] = "knowledge_rag_failed"
            base.setdefault("rag_warnings", []).append({"kind": "knowledge_rag", "message": "Actor retrieval failed; bundled playbook context remains available.", "error": str(exc)})
    base["context"] = knowledge.get("content") or ""
    return base
