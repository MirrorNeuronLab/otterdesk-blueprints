"""Provenance-preserving case-document graph projection."""

from __future__ import annotations

from dataclasses import dataclass
from email import policy
from email.parser import Parser
from email.utils import getaddresses
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
from typing import Any, Iterable
from uuid import uuid4

from mn_graph_analysis_skill import GraphClient as RGXCliClient

from ..models import CaseDocument


EMAIL_HEADER_EXTRACTOR_VERSION = "rfc822-observed-headers/1"


@dataclass(frozen=True, slots=True)
class GraphProjectionSummary:
    graph_path: Path
    node_count: int
    edge_count: int


def _logical_id(namespace: str, value: str) -> int:
    digest = hashlib.blake2b(f"{namespace}|{value}".encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "big")


def _email_headers(text: str) -> dict[str, Any]:
    """Extract only fields observed in the normalized RFC-822 header block."""

    message = Parser(policy=policy.default).parsestr(text)

    def addresses(name: str) -> list[dict[str, str]]:
        values: list[dict[str, str]] = []
        seen: set[str] = set()
        for display_name, address in getaddresses(message.get_all(name, [])):
            normalized_name = " ".join(display_name.split())
            normalized_address = address.strip().casefold()
            identity = normalized_address or (
                f"name:{normalized_name.casefold()}" if normalized_name else ""
            )
            if not identity or identity in seen:
                continue
            seen.add(identity)
            values.append(
                {
                    "identity": identity,
                    "email": normalized_address,
                    "display_name": normalized_name,
                }
            )
        return values

    return {
        "subject": str(message.get("Subject", "")).strip(),
        "date": str(message.get("Date", "")).strip(),
        "from": addresses("From"),
        "to": addresses("To"),
        "cc": addresses("Cc"),
    }


def build_records(
    documents: Iterable[CaseDocument],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    ordered = sorted(documents, key=lambda item: item.source_id)
    node_sources: dict[int, str] = {}
    edge_ids: dict[int, str] = {}
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    email_headers: dict[str, dict[str, Any]] = {}
    correspondents: dict[tuple[str, str], dict[str, set[str]]] = {}

    def register(identifier: int, source_id: str) -> None:
        prior = node_sources.get(identifier)
        if prior is not None and prior != source_id:
            raise ValueError(f"logical-ID collision between {prior!r} and {source_id!r}")
        node_sources[identifier] = source_id

    def add_edge(
        edge_key: str,
        src: int,
        dst: int,
        rel_type: str,
        properties: dict[str, Any],
    ) -> None:
        edge_id = _logical_id("edge", edge_key)
        prior = edge_ids.get(edge_id)
        if prior is not None and prior != edge_key:
            raise ValueError(f"logical edge-ID collision between {prior!r} and {edge_key!r}")
        edge_ids[edge_id] = edge_key
        edges.append(
            {
                "id": edge_id,
                "src": src,
                "dst": dst,
                "rel_type": rel_type,
                "properties": properties,
            }
        )

    for document in ordered:
        if document.media_type != "message/rfc822" or document.text is None:
            continue
        headers = _email_headers(document.text)
        email_headers[document.source_id] = headers
        for header_name in ("from", "to", "cc"):
            for value in headers[header_name]:
                key = (document.access_scope, value["identity"])
                aggregate = correspondents.setdefault(
                    key,
                    {
                        "display_names": set(),
                        "emails": set(),
                        "source_ids": set(),
                        "content_sha256s": set(),
                    },
                )
                if value["display_name"]:
                    aggregate["display_names"].add(value["display_name"])
                if value["email"]:
                    aggregate["emails"].add(value["email"])
                aggregate["source_ids"].add(document.source_id)
                aggregate["content_sha256s"].add(document.content_sha256)

    for (access_scope, identity), aggregate in sorted(correspondents.items()):
        source_key = f"correspondent:{access_scope}:{identity}"
        identifier = _logical_id("node", source_key)
        register(identifier, source_key)
        names = sorted(aggregate["display_names"])
        emails = sorted(aggregate["emails"])
        nodes.append(
            {
                "id": identifier,
                "kind": "Correspondent",
                "labels": ["ExtractedEntity", "Correspondent"],
                "properties": {
                    "logical_id": identifier,
                    "identity": identity,
                    "email": emails[0] if emails else "",
                    "display_name": names[0] if names else "",
                    "aliases": names,
                    "access_scope": access_scope,
                    "provenance_kind": "extracted",
                    "extractor_version": EMAIL_HEADER_EXTRACTOR_VERSION,
                    "source_ids": sorted(aggregate["source_ids"]),
                    "content_sha256s": sorted(aggregate["content_sha256s"]),
                },
            }
        )

    containers = sorted(
        {item.container_source_id for item in ordered if item.container_source_id is not None}
    )
    for source_id in containers:
        identifier = _logical_id("node", source_id)
        register(identifier, source_id)
        scope = next(
            item.access_scope for item in ordered if item.container_source_id == source_id
        )
        nodes.append(
            {
                "id": identifier,
                "kind": "Mailbox",
                "labels": ["SourceArtifact", "Mailbox"],
                "properties": {
                    "logical_id": identifier,
                    "source_id": source_id,
                    "access_scope": scope,
                },
            }
        )

    for document in ordered:
        identifier = _logical_id("node", document.source_id)
        register(identifier, document.source_id)
        kind = "Email" if document.media_type == "message/rfc822" else "Document"
        properties: dict[str, Any] = {
            "logical_id": identifier,
            "title": document.relative_path.rsplit("/", 1)[-1],
            "filename": document.relative_path,
            "doc_type": document.media_type,
            "source_id": document.source_id,
            "relative_path": document.relative_path,
            "media_type": document.media_type,
            "content_sha256": document.content_sha256,
            "size_bytes": document.size_bytes,
            "access_scope": document.access_scope,
        }
        if document.text is not None:
            properties["text"] = document.text
        headers = email_headers.get(document.source_id)
        if headers is not None:
            properties.update(
                {
                    "subject": headers["subject"],
                    "date": headers["date"],
                    "sender": [
                        item["email"] or item["display_name"] for item in headers["from"]
                    ],
                    "recipients": [
                        item["email"] or item["display_name"]
                        for item in [*headers["to"], *headers["cc"]]
                    ],
                    "header_extractor_version": EMAIL_HEADER_EXTRACTOR_VERSION,
                }
            )
        nodes.append(
            {
                "id": identifier,
                "kind": kind,
                "labels": ["SourceArtifact", kind],
                "properties": properties,
            }
        )

        if document.container_source_id is not None:
            container_id = _logical_id("node", document.container_source_id)
            add_edge(
                f"{document.source_id}|CONTAINED_IN|{document.container_source_id}",
                identifier,
                container_id,
                "CONTAINED_IN",
                {"source_id": document.source_id},
            )

        if headers is not None:
            for header_name, rel_type in (("from", "SENT"), ("to", "TO"), ("cc", "CC")):
                for position, value in enumerate(headers[header_name]):
                    correspondent_id = _logical_id(
                        "node",
                        f"correspondent:{document.access_scope}:{value['identity']}",
                    )
                    src, dst = (
                        (correspondent_id, identifier)
                        if header_name == "from"
                        else (identifier, correspondent_id)
                    )
                    add_edge(
                        f"{document.source_id}|{rel_type}|{value['identity']}|{position}",
                        src,
                        dst,
                        rel_type,
                        {
                            "source_id": document.source_id,
                            "content_sha256": document.content_sha256,
                            "access_scope": document.access_scope,
                            "provenance_kind": "extracted",
                            "extractor_version": EMAIL_HEADER_EXTRACTOR_VERSION,
                        },
                    )

    nodes.sort(key=lambda item: item["id"])
    edges.sort(key=lambda item: item["id"])
    return nodes, edges


class CaseGraphProjector:
    def __init__(
        self,
        graph_path: str | Path,
        rgx_binary: str | Path,
        timeout_seconds: float = 120.0,
    ) -> None:
        self.graph_path = Path(graph_path).expanduser().resolve()
        self.rgx_binary = str(rgx_binary)
        self.timeout_seconds = timeout_seconds

    def project(self, documents: Iterable[CaseDocument]) -> GraphProjectionSummary:
        if self.graph_path.exists():
            raise FileExistsError(f"RGX graph already exists: {self.graph_path}")
        nodes, edges = build_records(documents)
        self.graph_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_graph = self.graph_path.with_name(
            f".{self.graph_path.name}.{uuid4().hex}.tmp"
        )
        try:
            with tempfile.TemporaryDirectory(
                prefix="rgx-projection-", dir=self.graph_path.parent
            ) as directory:
                work = Path(directory)
                nodes_path = work / "nodes.json"
                edges_path = work / "edges.json"
                nodes_path.write_text(json.dumps(nodes), encoding="utf-8")
                edges_path.write_text(json.dumps(edges), encoding="utf-8")
                RGXCliClient(
                    temporary_graph,
                    self.rgx_binary,
                    timeout_seconds=self.timeout_seconds,
                ).import_json(nodes_path, edges_path)
            temporary_graph.replace(self.graph_path)
        except Exception:
            if temporary_graph.is_dir():
                shutil.rmtree(temporary_graph)
            elif temporary_graph.exists():
                temporary_graph.unlink()
            raise
        return GraphProjectionSummary(self.graph_path, len(nodes), len(edges))
