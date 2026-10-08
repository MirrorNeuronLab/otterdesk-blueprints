"""Domain playbook metadata and policy over shared knowledge retrieval."""

from pathlib import Path
from typing import Any

from mn_sdk_rag import (
    load_text_knowledge,
    prepare_optional_knowledge_rag,
    retrieve_local_context,
    retrieve_optional_knowledge_context,
)
from mn_sdk.integrations.rag import build_rag_context, prepare_blueprint_knowledge_rag

from .common import BLUEPRINT_ID, quick_test_enabled


def load_research_knowledge(root: Path) -> dict[str, Any]:
    return {
        **load_text_knowledge(root / "knowledge"),
        "id": "research_assistant_playbook",
        "title": "Research Assistant Evidence And Review Playbook",
        "grounding_rule": "Use retrieved guidance as a checklist; facts must come from user documents or cited public sources.",
    }


def prepare_research_rag(config, root, knowledge, documents, run_id=None):
    return prepare_optional_knowledge_rag(
        config,
        blueprint_id=BLUEPRINT_ID,
        root=root,
        knowledge=knowledge,
        documents=documents,
        run_id=run_id,
        offline=quick_test_enabled(config),
        prepare=prepare_blueprint_knowledge_rag,
    )


def retrieve_research_rag_context(
    query, rag_state, knowledge, documents, *, max_chars=6000
):
    return retrieve_optional_knowledge_context(
        query,
        rag_state,
        knowledge,
        documents,
        max_chars=max_chars,
        retrieve=build_rag_context,
    )


__all__ = [
    "load_research_knowledge",
    "prepare_research_rag",
    "retrieve_local_context",
    "retrieve_research_rag_context",
]
