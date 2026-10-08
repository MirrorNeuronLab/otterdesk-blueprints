"""Research request normalization, path resolution, and local evidence intake."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from mn_sdk.blueprint_support import expand_runtime_path, runtime_user_home

from mn_docs_to_markdown_skill import DocumentIntakeOptions, read_packet_document, scan_document_packet

from .common import DEFAULT_OUTPUT_FOLDER, SUPPORTED_SUFFIXES, TEXT_SUFFIXES, runtime_asset_root

try:
    from mn_docs_to_markdown_skill import extract_document
except Exception:  # pragma: no cover - optional runtime skill
    extract_document = None


def normalize_inputs(inputs: dict[str, Any] | None) -> dict[str, Any]:
    payload = copy.deepcopy(inputs or {})
    payload["research_goal"] = str(payload.get("research_goal") or payload.get("goal") or payload.get("query") or "").strip()
    payload["research_domain"] = str(payload.get("research_domain") or payload.get("domain") or "general").strip()
    payload["research_question"] = str(payload.get("research_question") or payload.get("question") or "").strip()
    payload["scope"] = str(payload.get("scope") or "").strip()
    payload["success_criteria"] = _as_list(payload.get("success_criteria"))
    payload["seed_hypotheses"] = _as_seed_hypotheses(payload.get("seed_hypotheses"))
    payload["constraints"] = payload.get("constraints") if isinstance(payload.get("constraints"), dict) else {}
    payload["input_folder"] = str(payload.get("input_folder") or "").strip()
    payload["output_folder"] = str(payload.get("output_folder") or DEFAULT_OUTPUT_FOLDER).strip()
    payload["research_mode"] = str(payload.get("research_mode") or "local_rag_and_public_web")
    return payload


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value)]


def _as_seed_hypotheses(value: Any) -> list[str | dict[str, Any]]:
    if value is None:
        return []
    raw = value if isinstance(value, (list, tuple)) else [value]
    normalized: list[str | dict[str, Any]] = []
    for item in raw:
        if isinstance(item, dict):
            statement = str(item.get("statement") or item.get("hypothesis") or "").strip()
            if statement:
                copy_item = copy.deepcopy(item)
                copy_item["statement"] = statement
                normalized.append(copy_item)
        elif str(item).strip():
            normalized.append(str(item).strip())
    return normalized


def resolve_input_folder(config: dict[str, Any], inputs: dict[str, Any], root: Path) -> Path | None:
    value = inputs.get("input_folder") or (config.get("inputs") or {}).get("payload", {}).get("input_folder")
    if not value:
        return None
    path = expand_runtime_path(value)
    if not path.is_absolute():
        bundled_path = runtime_asset_root() / path
        if bundled_path.exists():
            return bundled_path
        path = root / path
    return path


def load_input_documents(folder: Path | None, config: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if folder is None or not folder.exists():
        return [], [] if folder is None else [{"status": "missing", "path": str(folder), "warning": "input_folder does not exist"}]
    def extract(path: Path) -> dict[str, Any]:
        return read_packet_document(path, text_suffixes=TEXT_SUFFIXES,
                                    extractor=extract_document, config=config)

    packet = scan_document_packet(
        folder,
        options=DocumentIntakeOptions(
            supported_suffixes=frozenset(SUPPORTED_SUFFIXES),
            text_suffixes=frozenset(TEXT_SUFFIXES),
            max_chars_per_file=20_000,
        ),
        extractor=extract,
    )
    records: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    for item in packet.records:
        path = folder / item["path"]
        if item["status"] == "failed":
            warnings.append({"path": str(path), "status": "failed", "message": "; ".join(item["warnings"])})
            continue
        record = {
            "path": str(path), "name": item["filename"], "suffix": item["suffix"],
            "bytes": path.stat().st_size, "sha256": item["sha256"],
            "extraction_method": item["extraction_method"],
            "status": "extracted" if item["text"] else "review_required",
            "text": item["text"], "source_ref": f"local:{item['filename']}",
        }
        if item["warnings"]:
            record["warnings"] = item["warnings"]
        records.append(record)
        if not item["text"]:
            warnings.append({"path": str(path), "status": "review_required", "message": f"No usable text extracted from {item['filename']}."})
    warnings.extend(dict(item) for item in packet.warnings if item.get("status") != "document_failed")
    return records, warnings


__all__ = ['normalize_inputs', '_as_list', '_as_seed_hypotheses', 'resolve_input_folder', 'runtime_user_home', 'expand_runtime_path', 'load_input_documents']
