"""VC prompt-library and knowledge-RAG policy adapters."""

from __future__ import annotations

from .common import *
from .intake import slugify
from .runtime_tools import (
    append_event,
    append_observation_record,
    observed_operation,
    quick_test_mode_enabled,
    stable_text_hash,
)

def prompt_library_for_runtime() -> PromptLibrary:
    for parent in Path(__file__).resolve().parents:
        prompt_dir = parent / "prompts"
        if prompt_dir.is_dir():
            return PromptLibrary(prompt_dir)
    return PromptLibrary.from_script(__file__, parents_up=2)

PROMPTS = prompt_library_for_runtime()

def _agent_prompt_files(agent_ids: list[str]) -> dict[str, str]:
    return {
        agent_id: filename
        for agent_id in agent_ids
        for filename in [f"{agent_id.replace('_', '-')}.md"]
        if (PROMPTS.prompt_dir / filename).is_file()
    }


RESEARCH_AGENT_PROMPT_FILES = _agent_prompt_files(DEFAULT_AGENTIC_RESEARCH_AGENT_IDS)
REVIEW_AGENT_PROMPT_FILES = _agent_prompt_files(
    [agent_id for agent_id in AGENT_IDS if agent_id not in RESEARCH_AGENT_PROMPT_FILES]
)

def load_prompt(name: str, **values: Any) -> str:
    return PROMPTS.load(name, **values)

def prompt_spec_from_markdown(name: str, **values: Any) -> dict[str, Any]:
    return PROMPTS.spec_from_markdown(name, **values)

def vc_knowledge_search_roots(blueprint_dir: Path) -> list[Path]:
    roots = [blueprint_dir, blueprint_dir / "payloads"]
    bundle_dir = os.environ.get("MN_BLUEPRINT_BUNDLE_DIR")
    if bundle_dir:
        roots.append(Path(bundle_dir).expanduser())
    script_path = Path(__file__).resolve()
    roots.extend([script_path.parents[1], script_path.parents[2], script_path.parents[3]])
    unique_roots = []
    for root in roots:
        if root not in unique_roots:
            unique_roots.append(root)
    return unique_roots

def load_vc_knowledge(blueprint_dir: Path) -> dict[str, Any]:
    playbook_path = next(
        (
            root / KNOWLEDGE_PLAYBOOK_RELATIVE_PATH
            for root in vc_knowledge_search_roots(blueprint_dir)
            if (root / KNOWLEDGE_PLAYBOOK_RELATIVE_PATH).exists()
        ),
        blueprint_dir / KNOWLEDGE_PLAYBOOK_RELATIVE_PATH,
    )
    try:
        content = playbook_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        content = ""
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest() if content else ""
    return {
        "id": "vc_startup_research_playbook",
        "title": "VC Startup Research And Method Playbook",
        "path": KNOWLEDGE_PLAYBOOK_RELATIVE_PATH,
        "resolved_path": str(playbook_path),
        "sha256": digest,
        "content": content[:16000],
        "method_guidance": VC_METHOD_GUIDANCE,
        "judge_rubric": JUDGE_RUBRIC,
        "domain_guard": "Use VC analysis knowledge only; ignore unrelated non-VC domain knowledge.",
    }

def knowledge_rag_config(config: dict[str, Any]) -> dict[str, Any]:
    config = with_runtime_knowledge_rag_defaults(config)
    if fake_skills_mode_enabled(config):
        raw = config.get("knowledge_rag") if isinstance(config.get("knowledge_rag"), dict) else {}
        return {
            "enabled": True,
            "status": "mock_ready",
            "required": False,
            "mocked": True,
            "config": {
                "namespace": raw.get("namespace", "vc_assistant_context"),
                "top_k": raw.get("top_k", 3),
                "max_context_chars": raw.get("max_context_chars", 3000),
                "required": False,
            },
        }
    return skill_knowledge_rag_config(config)

def with_runtime_knowledge_rag_defaults(config: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(config, dict):
        return config

    raw = config.get("knowledge_rag") if isinstance(config.get("knowledge_rag"), dict) else {}
    updates: dict[str, Any] = {}
    if raw.get("enabled", True) and not str(raw.get("backend") or "").strip():
        updates["backend"] = "milvus_lite"

    runtime_db_root = (os.environ.get("MN_RAG_DB_ROOT") or "").strip()
    if runtime_db_root and not str(raw.get("db_root") or "").strip():
        updates["db_root"] = runtime_db_root

    if not updates:
        return config

    patched = dict(config)
    patched["knowledge_rag"] = {**raw, **updates}
    return patched

def resolve_knowledge_dir(
    blueprint_dir: Path,
    active_knowledge: dict[str, Any],
    configured_path: str | Path | None = None,
) -> Path:
    if fake_skills_mode_enabled():
        return blueprint_dir / "knowledge"
    if configured_path:
        payload_root = (
            blueprint_dir / "payloads"
            if (blueprint_dir / "payloads").is_dir()
            else blueprint_dir
        )
        return resolve_blueprint_path(
            configured_path,
            bundle_root=blueprint_dir,
            payload_root=payload_root,
        )
    return skill_resolve_blueprint_knowledge_dir(
        blueprint_dir,
        active_knowledge=active_knowledge,
        configured_path=configured_path,
    )

def prepare_knowledge_rag(
    *,
    blueprint_dir: Path,
    resolved_config: dict[str, Any],
    active_knowledge: dict[str, Any],
    run_dir: Path | None = None,
) -> dict[str, Any]:
    resolved_config = with_runtime_knowledge_rag_defaults(resolved_config)
    raw = resolved_config.get("knowledge_rag") if isinstance(resolved_config.get("knowledge_rag"), dict) else {}
    if fake_skills_mode_enabled(resolved_config):
        state = {
            "enabled": True,
            "status": "mock_ready",
            "required": False,
            "mocked": True,
            "warnings": [],
            "config": {
                "namespace": raw.get("namespace", "vc_assistant_context"),
                "embedding_provider": "mock",
                "embedding_model": "mock-deterministic-rag",
                "top_k": raw.get("top_k", 3),
                "max_context_chars": raw.get("max_context_chars", 3000),
                "index_on_startup": False,
                "required": False,
            },
        }
        append_observation_record(
            run_dir,
            "skill_mock_used",
            {
                "phase": "knowledge_rag",
                "operation": "prepare",
                "tool": "rag_skill",
                "status": "mocked",
                "mocked": True,
            },
        )
        return state
    if fake_llm_mode_enabled(resolved_config):
        return {
            "enabled": False,
            "status": "disabled_for_fake_llm",
            "required": False,
            "warnings": [
                {
                    "kind": "knowledge_rag",
                    "status": "disabled_for_fake_llm",
                    "message": "Knowledge RAG embedding calls are disabled during explicit fake-LLM smoke runs.",
                }
            ],
            "config": {
                "namespace": raw.get("namespace", ""),
                "embedding_provider": raw.get("embedding_provider", ""),
                "embedding_model": raw.get("embedding_model", ""),
                "top_k": raw.get("top_k", 5),
                "max_context_chars": raw.get("max_context_chars", 6000),
                "index_on_startup": raw.get("index_on_startup", True),
                "required": False,
            },
        }
    if quick_test_mode_enabled(resolved_config):
        return {
            "enabled": False,
            "status": "disabled",
            "required": False,
            "warnings": [
                {
                    "kind": "knowledge_rag",
                    "status": "disabled_for_quick_test",
                    "message": "Knowledge RAG embedding calls are disabled during quick-test runs; bundled static VC knowledge was used instead.",
                }
            ],
            "config": {
                "namespace": raw.get("namespace", ""),
                "embedding_provider": raw.get("embedding_provider", ""),
                "embedding_model": raw.get("embedding_model", ""),
                "top_k": raw.get("top_k", 5),
                "max_context_chars": raw.get("max_context_chars", 6000),
                "index_on_startup": raw.get("index_on_startup", True),
                "required": False,
            },
        }
    if not bool(raw.get("enabled", True)):
        return {
            "enabled": False,
            "status": "disabled",
            "warnings": [],
            "config": {
                "namespace": raw.get("namespace", ""),
                "embedding_provider": raw.get("embedding_provider", ""),
                "embedding_model": raw.get("embedding_model", ""),
                "top_k": raw.get("top_k", 5),
                "max_context_chars": raw.get("max_context_chars", 6000),
                "index_on_startup": raw.get("index_on_startup", True),
            },
        }
    def event_callback(event_type: str, payload: dict[str, Any]) -> None:
        if run_dir:
            append_event(run_dir, event_type, payload)

    try:
        return KnowledgeRagSession(
            blueprint_id=BLUEPRINT_ID,
            blueprint_dir=blueprint_dir,
            config=resolved_config,
            active_knowledge=active_knowledge,
            knowledge_dir=resolve_knowledge_dir(
                blueprint_dir,
                active_knowledge,
                raw.get("knowledge_dir"),
            ),
            event_callback=event_callback,
            prepare_callback=skill_prepare_blueprint_knowledge_rag,
            retrieve_callback=skill_retrieve_knowledge_rag_context,
            require_callback=skill_require_ready_knowledge_rag,
            public_state_callback=skill_public_rag_state,
        ).prepare()
    except Exception as exc:
        warning = {
            "kind": "knowledge_rag",
            "status": "knowledge_rag_failed",
            "message": "Knowledge RAG was enabled but Milvus Lite indexing could not complete; no static playbook fallback was injected.",
            "error": str(exc),
        }
        state = {
            "enabled": bool(raw.get("enabled", True)),
            "status": "knowledge_rag_failed",
            "warnings": [warning],
            "config": {
                "namespace": raw.get("namespace", ""),
                "embedding_provider": raw.get("embedding_provider", ""),
                "embedding_model": raw.get("embedding_model", ""),
                "top_k": raw.get("top_k", 5),
                "max_context_chars": raw.get("max_context_chars", 6000),
                "index_on_startup": raw.get("index_on_startup", True),
            },
        }
        append_event(run_dir, "tool_call_failed", {"tool": "knowledge_rag.index", "status": "knowledge_rag_failed", "error": str(exc)}) if run_dir else None
        return state

def public_knowledge_rag_state(state: dict[str, Any] | None) -> dict[str, Any]:
    if not state:
        return {"enabled": False, "status": "disabled"}
    return skill_public_rag_state(state)

def knowledge_rag_is_required(state: dict[str, Any] | None) -> bool:
    if not state or not state.get("enabled"):
        return False
    config = state.get("config") if isinstance(state.get("config"), dict) else {}
    value = state.get("required", config.get("required"))
    return bool(value) if isinstance(value, bool) else str(value or "").strip().lower() in {"1", "true", "yes", "on"}

def require_ready_rag(
    knowledge_rag: dict[str, Any] | None,
    *,
    stage: str = "",
    company: str = "",
    context: dict[str, Any] | None = None,
    min_citations: int = 0,
    run_dir: Path | None = None,
) -> dict[str, Any] | None:
    if isinstance(knowledge_rag, dict) and knowledge_rag.get("mocked"):
        return context if context is not None else knowledge_rag
    if not knowledge_rag_is_required(knowledge_rag):
        return context if context is not None else knowledge_rag
    with observed_operation(
        run_dir,
        phase="knowledge_rag",
        operation="require_ready",
        stage=stage,
        company=company,
        min_citations=min_citations,
        citation_count=len((context or {}).get("citations") or []) if isinstance(context, dict) else None,
        context_chars=len(str((context or {}).get("context") or "")) if isinstance(context, dict) else None,
    ):
        return KnowledgeRagSession.from_state(
            knowledge_rag,
            blueprint_id=BLUEPRINT_ID,
            require_callback=skill_require_ready_knowledge_rag,
        ).require_ready(
            stage=stage,
            company=company,
            context=context,
            min_citations=min_citations,
        )

def active_knowledge_for_prompt(active_knowledge: dict[str, Any], knowledge_rag: dict[str, Any] | None) -> dict[str, Any]:
    if (knowledge_rag or {}).get("enabled"):
        ref = active_knowledge_reference(active_knowledge)
        ref["domain_guard"] = active_knowledge.get("domain_guard")
        ref["content_retrieval"] = "redis_rag"
        return ref
    return active_knowledge

def retrieve_knowledge_rag_context(
    *,
    knowledge_rag: dict[str, Any] | None,
    query: str,
    stage: str = "",
    company: str = "",
    run_dir: Path | None = None,
) -> dict[str, Any]:
    metadata = {
        "stage": stage,
        "company": company,
        "query_hash": stable_text_hash(query),
        "query_chars": len(query or ""),
    }
    if fake_skills_mode_enabled() or (isinstance(knowledge_rag, dict) and knowledge_rag.get("mocked")):
        with observed_operation(run_dir, phase="knowledge_rag", operation="retrieve", mocked=True, **metadata) as op:
            ref = f"mock-rag:{slugify(stage or 'stage')}:{stable_text_hash(company or query)[:8]}"
            context = {
                "enabled": True,
                "status": "mock_ready",
                "mocked": True,
                "query": query,
                "context": f"Mock VC knowledge context for {company or stage}: use evidence-backed scoring, note assumptions, and keep recommendations review-only.",
                "citations": [
                    {
                        "ref": ref,
                        "title": "Mock VC assistant knowledge",
                        "source": "fake_skills",
                        "score": 1.0,
                    }
                ],
            }
            op.close("completed", mocked=True, rag_status=context["status"], citation_count=1, context_chars=len(context["context"]))
            return context
    try:
        with observed_operation(run_dir, phase="knowledge_rag", operation="retrieve", **metadata) as op:
            context = KnowledgeRagSession.from_state(
                knowledge_rag,
                blueprint_id=BLUEPRINT_ID,
                retrieve_callback=skill_retrieve_knowledge_rag_context,
                require_callback=skill_require_ready_knowledge_rag,
                public_state_callback=skill_public_rag_state,
            ).retrieve(
                query,
                stage=stage,
                company=company,
            )
            if isinstance(context, dict):
                op.close(
                    "completed",
                    rag_status=context.get("status"),
                    citation_count=len(context.get("citations") or []),
                    context_chars=len(str(context.get("context") or "")),
                )
            return context
    except Exception as exc:
        append_observation_record(
            run_dir,
            "observability_operation_failed",
            {
                "phase": "knowledge_rag",
                "operation": "retrieve",
                "status": "failed",
                "error": str(exc),
                "error_type": type(exc).__name__,
                **metadata,
            },
        )
        return {
            "enabled": bool((knowledge_rag or {}).get("enabled")),
            "status": "knowledge_rag_failed",
            "query": query,
            "context": "",
            "citations": [],
            "chunks": [],
            "warnings": [
                {
                    "kind": "knowledge_rag",
                    "status": "knowledge_rag_failed",
                    "message": f"Knowledge RAG retrieval failed for {stage or 'prompt'}; prompt continued without retrieved knowledge context.",
                    "error": str(exc),
                }
            ],
            "stage": stage,
            "company": company,
        }

def rag_ref_values(value: Any) -> list[Any]:
    refs: list[Any] = []
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {"rag_refs", "rag_ref", "citation_refs", "citations"}:
                if isinstance(item, list):
                    refs.extend(item)
                elif item not in (None, ""):
                    refs.append(item)
            else:
                refs.extend(rag_ref_values(item))
    elif isinstance(value, list):
        for item in value:
            refs.extend(rag_ref_values(item))
    return refs

def validate_llm_rag_refs(decision: dict[str, Any], *, knowledge_rag: dict[str, Any] | None, stage: str, company: str = "") -> None:
    if knowledge_rag_is_required(knowledge_rag) and not rag_ref_values(decision):
        label = f"{stage}{f' / {company}' if company else ''}"
        raise RuntimeError(f"Required RAG citation refs missing from LLM output for {label}.")

def citation_ref_values(rag_context: dict[str, Any] | None, *, limit: int = 3) -> list[Any]:
    refs = []
    for citation in (rag_context or {}).get("citations") or []:
        if isinstance(citation, dict) and citation.get("ref") not in (None, ""):
            refs.append(citation.get("ref"))
    return refs[:limit]

def active_knowledge_reference(active_knowledge: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": active_knowledge.get("id"),
        "title": active_knowledge.get("title"),
        "path": active_knowledge.get("path"),
        "sha256": active_knowledge.get("sha256"),
        "method_memory_hooks": {
            method_id: guidance["memory_hook"]
            for method_id, guidance in (active_knowledge.get("method_guidance") or {}).items()
            if isinstance(guidance, dict) and guidance.get("memory_hook")
        },
        "judge_rubric": list(active_knowledge.get("judge_rubric") or []),
    }
