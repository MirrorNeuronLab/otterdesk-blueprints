"""Research-method knowledge loading and job-scoped retrieval."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .common import BLUEPRINT_ID, _sha256

try:
    from mn_rag_skill import build_rag_context, prepare_blueprint_knowledge_rag
except Exception:  # pragma: no cover - optional runtime skill
    build_rag_context = None
    prepare_blueprint_knowledge_rag = None


def load_research_knowledge(root: Path) -> dict[str, Any]:
    files = []
    combined: list[str] = []
    for path in sorted((root / "knowledge").rglob("*")) if (root / "knowledge").exists() else []:
        if path.is_file() and path.suffix.lower() in {".md", ".txt", ".json", ".csv"}:
            text = path.read_text(encoding="utf-8", errors="replace")
            files.append({"path": str(path), "name": path.name, "sha256": _sha256(text), "chars": len(text)})
            combined.append(f"\n## {path.name}\n{text}")
    content = "".join(combined)
    return {
        "id": "research_coscientist_playbook",
        "title": "Research Co-Scientist Evidence And Review Playbook",
        "files": files,
        "content": content[:40000],
        "sha256": _sha256(content),
        "grounding_rule": "Use retrieved guidance as a checklist; facts must come from user documents or cited public sources.",
    }


def prepare_research_rag(config: dict[str, Any], root: Path, knowledge: dict[str, Any], documents: list[dict[str, Any]], run_id: str | None = None) -> dict[str, Any]:
    raw = config.get("knowledge_rag") if isinstance(config.get("knowledge_rag"), dict) else {}
    state: dict[str, Any] = {
        "enabled": bool(raw.get("enabled", True)),
        "status": "disabled" if raw.get("enabled") is False else "local_ready",
        "config": raw,
        "namespace": f"{raw.get('namespace') or 'research_coscientist'}:{run_id or 'local'}",
        "knowledge_files": knowledge.get("files", []),
        "user_documents_indexed": [item.get("source_ref") for item in documents if item.get("text")],
        "warnings": [],
    }
    if not state["enabled"]:
        return state
    execution = config.get("execution") if isinstance(config.get("execution"), dict) else {}
    llm = config.get("llm") if isinstance(config.get("llm"), dict) else {}
    if bool(execution.get("quick_test")) or str(llm.get("mode") or "").lower() in {"fake", "mock", "test"}:
        state["status"] = "skipped_quick_test"
        state["warnings"].append({"status": "skipped_quick_test", "message": "Embedding preparation is skipped in deterministic quick-test mode; local lexical retrieval remains enabled."})
        return state
    if prepare_blueprint_knowledge_rag is None:
        state["warnings"].append({"status": "skill_unavailable", "message": "mirrorneuron-rag-skill is unavailable; lexical local retrieval remains enabled."})
        return state
    try:
        rag_state = prepare_blueprint_knowledge_rag(
            blueprint_id=BLUEPRINT_ID,
            blueprint_dir=root,
            config={"knowledge_rag": raw},
            active_knowledge=knowledge,
        )
        state.update({key: value for key, value in rag_state.items() if key not in {"config"}})
        state["config"] = rag_state.get("config") or raw
    except Exception as exc:  # pragma: no cover - runtime embedding failures
        state["status"] = "knowledge_rag_failed"
        state["warnings"].append({"status": "knowledge_rag_failed", "message": str(exc)})
    return state


def retrieve_local_context(query: str, knowledge: dict[str, Any], documents: list[dict[str, Any]], top_k: int = 6, max_chars: int = 6000) -> dict[str, Any]:
    terms = {token.lower() for token in re.findall(r"[a-zA-Z0-9][a-zA-Z0-9_-]+", query) if len(token) > 2}
    chunks: list[dict[str, Any]] = []
    corpus = [{"source_ref": "knowledge/", "text": knowledge.get("content", ""), "title": knowledge.get("title")}]
    corpus.extend({"source_ref": item.get("source_ref"), "text": item.get("text", ""), "title": item.get("name")} for item in documents)
    for item in corpus:
        text = str(item.get("text") or "")
        for index, chunk in enumerate(_chunks(text, 1200)):
            lowered = chunk.lower()
            score = sum(1 for term in terms if term in lowered)
            if score or not terms:
                chunks.append({"source_ref": item.get("source_ref"), "title": item.get("title"), "chunk_index": index, "score": score, "text": chunk})
    chunks.sort(key=lambda item: (-int(item["score"]), str(item.get("source_ref"))))
    selected = chunks[: max(1, top_k)]
    context = "\n\n".join(f"[{item.get('source_ref')}] {item['text']}" for item in selected)
    citations = [item.get("source_ref") for item in selected if item.get("source_ref")]
    return {"context": context[:max_chars], "citations": citations, "chunks": selected, "backend": "local_lexical_rag"}


def retrieve_research_rag_context(query: str, rag_state: dict[str, Any], knowledge: dict[str, Any], documents: list[dict[str, Any]], *, max_chars: int = 6000) -> dict[str, Any]:
    """Use the shared embedding RAG skill when available, with local evidence retrieval alongside it."""
    lexical = retrieve_local_context(query, knowledge, documents, max_chars=max_chars)
    rag_config = rag_state.get("_rag_config") if isinstance(rag_state, dict) else None
    if build_rag_context is not None and rag_state.get("status") == "ready" and rag_config is not None:
        try:
            retrieved = build_rag_context(query, rag_config, max_chars=max_chars)
            return {
                "context": retrieved.get("context") or lexical["context"],
                "citations": list(dict.fromkeys([*(retrieved.get("citations") or []), *lexical["citations"]])),
                "chunks": retrieved.get("chunks") or lexical["chunks"],
                "backend": retrieved.get("backend") or "milvus_lite",
                "embedding_model": retrieved.get("embedding_model"),
            }
        except Exception as exc:  # pragma: no cover - depends on embedding runtime
            lexical["warning"] = {"status": "knowledge_rag_failed", "message": str(exc)}
    return lexical


def _chunks(text: str, size: int) -> list[str]:
    words = text.split()
    return [" ".join(words[index : index + size]) for index in range(0, len(words), size)] or [""]


__all__ = ['load_research_knowledge', 'prepare_research_rag', 'retrieve_local_context', 'retrieve_research_rag_context', '_chunks']
