"""Deterministic materialization and verification of frozen evidence indexes."""

from mn_sdk.agent_events import activity_operation

import hashlib
import json
import shutil
from pathlib import Path

from mn_graph_analysis_skill import GraphClient
from mn_prototype_bounded_tool_loop_agent.checkpoint import atomic_json

from .intake import PreparedCorpus
from .graph_projection.projector import CaseGraphProjector


def digest(path):
    path = Path(path)
    if path.is_symlink():
        raise ValueError("symbolic link in evidence artifact")
    h = hashlib.sha256()
    paths = sorted(path.rglob("*")) if path.is_dir() else [path]
    for item in paths:
        if item.is_symlink():
            raise ValueError("symbolic link in evidence artifact")
        if item.is_dir():
            continue
        if path.is_dir():
            h.update(item.relative_to(path).as_posix().encode() + b"\0")
        with item.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                h.update(block)
    return h.hexdigest()


def validate_indexes(case, scope):
    corpus = PreparedCorpus(case, scope)
    receipt = json.loads((case / "indexes.json").read_text())
    for name in (
        "sources.json",
        "source_inventory.json",
        "source-query.json",
        "evidence.rgx",
        "source-relationships.json",
    ):
        if digest(case / name) != receipt["hashes"][name]:
            raise ValueError("evidence index hash mismatch: " + name)
    if receipt["access_scope"] != scope:
        raise ValueError("index scope mismatch")
    return corpus, receipt


@activity_operation('Indexing case evidence', completed='Indexing case evidence: completed')
def build_indexes(context, inputs):
    from .state import read_capture, indexed, read_seal
    capture_reference = inputs["previous"]["result"]["evidence"]
    read_capture(context, capture_reference)
    case = context.store.run_dir / "case"
    scope = context.config["investigation"]["access_scope"]
    llm_client = context.resources.get("llm")
    corpus = PreparedCorpus(case, scope)
    receipt_path = case / "indexes.json"
    if receipt_path.exists():
        validate_indexes(case, scope)
    else:
        # No receipt means an interrupted build; these are derived artifacts only.
        for name in ("evidence.rgx",):
            path = case / name
            if path.exists():
                shutil.rmtree(path) if path.is_dir() else path.unlink()
        # Seal the SDK SourceCorpus catalog rather than build a second text index.
        if not (case / "source-query.json").is_file():
            raise ValueError("Original source catalog must be prepared before indexing")
        graph = GraphClient(case / "evidence.rgx")
        inventory = json.loads((case / 'source_inventory.json').read_text())
        from .relationship_index import build as build_relationships
        relationships = build_relationships(context, corpus.scan(), llm_client=llm_client)
        CaseGraphProjector(graph.database_path, graph.binary).project(corpus.scan(),
            repository_id=inventory.get('repository_id'), file_identities=inventory.get('file_identities'),
            relationship_index=relationships)
        graph.check()
        atomic_json(
            receipt_path,
            {
                "access_scope": scope,
                "hashes": {
                    name: digest(case / name)
                    for name in (
                        "sources.json",
                        "source_inventory.json",
                        "source-query.json",
                        "evidence.rgx",
                        "source-relationships.json",
                    )
                },
            },
        )
    evidence = indexed(context, capture_reference)
    return {"index_receipt": read_seal(context, evidence, "indexed")["index_receipt"], "evidence": evidence}


def verified(context, result):
    from .state import read_indexed
    read_indexed(context, result["evidence"])
    return True
