"""Deterministic materialization and verification of frozen evidence indexes."""

from dataclasses import asdict
import hashlib
import json
import shutil
from pathlib import Path

from mn_document_reading_skill.search import PassageIndex
from mn_graph_analysis_skill import GraphClient
from mn_prototype_bounded_tool_loop_agent.checkpoint import atomic_json
from mn_sdk.step_runtime import artifact_reference

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
        "documents.sqlite3",
        "evidence.rgx",
    ):
        if digest(case / name) != receipt["hashes"][name]:
            raise ValueError("evidence index hash mismatch: " + name)
    if receipt["access_scope"] != scope:
        raise ValueError("index scope mismatch")
    return corpus, receipt


def build_indexes(context, *, llm_client=None):
    case = Path(context["run_dir"]) / "case"
    scope = context["config"]["investigation"]["access_scope"]
    corpus = PreparedCorpus(case, scope)
    receipt_path = case / "indexes.json"
    if receipt_path.exists():
        validate_indexes(case, scope)
    else:
        # No receipt means an interrupted build; these are derived artifacts only.
        for name in ("documents.sqlite3", "evidence.rgx"):
            path = case / name
            if path.exists():
                shutil.rmtree(path) if path.is_dir() else path.unlink()
        PassageIndex.build(
            case / "documents.sqlite3", [asdict(d) for d in corpus.scan()], scope
        )
        graph = GraphClient(case / "evidence.rgx")
        CaseGraphProjector(graph.database_path, graph.binary).project(corpus.scan())
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
                        "documents.sqlite3",
                        "evidence.rgx",
                    )
                },
            },
        )
    refs = [
        artifact_reference(key, "case/" + name)
        for key, name in (
            ("document_index", "documents.sqlite3"),
            ("evidence_graph", "evidence.rgx"),
            ("index_receipt", "indexes.json"),
        )
    ]
    return {"index_receipt": refs[-1]}, refs
