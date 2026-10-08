"""Evidence preparation, privacy-safe source research, and deterministic posture."""

from __future__ import annotations

import csv
import io
import os
import re
from pathlib import Path
from typing import Any

from mn_public_research_orchestrator_skill import BrowserResearch, load_browser as _load_web_browser_skill

from .common import DEFAULT_OUTPUT_FOLDER, runtime_asset_root
from .inputs import expand_runtime_path, load_input_documents, resolve_input_folder
from .knowledge import load_research_knowledge, prepare_research_rag, retrieve_research_rag_context
from .state import _inputs, _save, _state


def prepare_evidence_context(
    config: dict[str, Any],
    inputs: dict[str, Any],
    root: Path,
    run_id: str,
    *,
    quick_test: bool,
) -> dict[str, Any]:
    """Build the same evidence state for direct and staged workflow execution."""
    folder = resolve_input_folder(config, inputs, root)
    documents, document_warnings = load_input_documents(folder, config)
    knowledge = load_research_knowledge(runtime_asset_root())
    rag = prepare_research_rag(config, runtime_asset_root(), knowledge, documents, run_id)
    rag_query = " ".join(build_public_queries(inputs))
    retrieval = retrieve_research_rag_context(
        rag_query,
        rag,
        knowledge,
        documents,
        max_chars=int((config.get("knowledge_rag") or {}).get("max_context_chars", 6000)),
    )
    rag["context"] = retrieval["context"]
    rag["citations"] = retrieval["citations"]
    rag["chunks"] = retrieval["chunks"]
    rag["retrieval_backend"] = retrieval["backend"]
    if retrieval.get("warning"):
        rag.setdefault("warnings", []).append(retrieval["warning"])
    if rag.get("status") == "knowledge_rag_failed" and retrieval.get("context"):
        rag["embedding_status"] = "knowledge_rag_failed"
        rag["status"] = "local_lexical_fallback"
        rag["fallback_active"] = True
        for warning in rag.get("warnings") or []:
            if warning.get("status") == "knowledge_rag_failed":
                warning["message"] = "Embedding RAG failed; bundled local lexical retrieval supplied the research-method guidance."
    else:
        rag["fallback_active"] = False
    rag.pop("_rag_config", None)
    queries = build_public_queries(inputs)
    sources, web_warnings = research_public_sources(queries, config, quick_test=quick_test)
    evidence = research_evidence(inputs, documents, sources)
    return {
        "folder": folder,
        "documents": documents,
        "knowledge": knowledge,
        "rag": rag,
        "sources": sources,
        "evidence": evidence,
        "warnings": [*document_warnings, *(rag.get("warnings") or []), *web_warnings],
        "public_research_warnings": web_warnings,
    }


def build_public_queries(inputs: dict[str, Any]) -> list[str]:
    research_goal = sanitize_public_text(inputs.get("research_goal", ""))
    if not research_goal:
        return []
    base = " ".join(part for part in [
        sanitize_public_text(inputs.get("research_domain", "")),
        research_goal,
        sanitize_public_text(inputs.get("research_question", "")),
    ] if part).strip()
    return [
        f"{base} primary evidence methods limitations",
        f"{base} experiment design baseline controls measurement confounders",
        f"{base} competing hypotheses replication review",
    ]


def sanitize_public_text(value: Any) -> str:
    text = str(value or "")
    blocked = ("raw_document_text", "private_financial", "account number", "password", "ssn", "confidential", "contact details")
    lowered = text.lower()
    if any(marker in lowered for marker in blocked):
        return ""
    text = re.sub(r"[\r\n\t]+", " ", text)
    return re.sub(r"[^\w\s.,:/-]", "", text)[:180]


def research_public_sources(queries, config, *, quick_test=False):
    internet = config.get("internet_research") if isinstance(config.get("internet_research"), dict) else {}
    if not internet.get("enabled", True):
        return [], [{"status": "disabled", "message": "Public research is disabled by configuration."}]
    if quick_test:
        return [], [{"status": "skipped_quick_test", "message": "Public research is skipped in fake/quick-test mode."}]
    browser = BrowserResearch(internet, entity="research", verification_target="research_source",
                              browser_loader=_load_web_browser_skill)
    browser.research_queries(queries[:int(internet.get("max_queries", 6))],
                             max_sources=int(internet.get("max_sources", 8)))
    return browser.sources, browser.warnings


def _status_counts(records: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in records:
        status = str(item.get("status") or "unknown")
        counts[status] = counts.get(status, 0) + 1
    return counts


def resolve_output_folder(config: dict[str, Any], inputs: dict[str, Any]) -> Path | None:
    runtime_output_folder = os.environ.get("MN_JOB_OUTPUT_DIR")
    if runtime_output_folder:
        return expand_runtime_path(runtime_output_folder)
    value = inputs.get("output_folder") or (config.get("outputs") or {}).get("folder_path") or DEFAULT_OUTPUT_FOLDER
    value = str(value).strip()
    if not value:
        return None
    return expand_runtime_path(value)


def research_evidence(
    inputs: dict[str, Any], documents: list[dict[str, Any]], sources: list[dict[str, Any]]
) -> dict[str, Any]:
    """Build deterministic evidence coverage without inferring scientific results."""
    usable_documents = [
        item
        for item in documents
        if item.get("status") == "extracted" and str(item.get("text") or "").strip()
    ]
    observed_sources = [
        item
        for item in sources
        if item.get("status") == "observed" and (str(item.get("url") or "").strip() or str(item.get("snippet") or "").strip())
    ]
    local_text = "\n".join(str(item.get("text") or "") for item in usable_documents)
    lowered = local_text.lower()
    source_refs = [item.get("source_ref") for item in [*usable_documents, *observed_sources] if item.get("source_ref")]
    checks = {
        "research_goal_defined": bool(inputs.get("research_goal")),
        "question_or_scope_defined": bool(inputs.get("research_question") or inputs.get("scope")),
        "local_evidence_present": bool(usable_documents),
        "public_evidence_present": bool(observed_sources),
        "method_or_measurement_discussed": any(
            marker in lowered
            for marker in ("method", "measure", "measurement", "baseline", "control", "dataset", "protocol")
        ),
        "constraints_or_review_boundary_defined": bool(inputs.get("constraints")),
    }
    evidence_gaps = [
        key.replace("_", " ")
        for key, present in checks.items()
        if not present and key not in {"public_evidence_present"}
    ]
    if not observed_sources:
        evidence_gaps.append("verified public evidence")
    if not source_refs:
        evidence_gaps.append("usable research evidence")
    if any(item.get("status") == "blocked" for item in sources):
        evidence_gaps.append("access-limited public sources")
    return {
        "research_goal": inputs.get("research_goal"),
        "research_domain": inputs.get("research_domain"),
        "deterministic_checks": checks,
        "document_count": len(documents),
        "public_source_count": len(observed_sources),
        "usable_local_document_count": len(usable_documents),
        "usable_public_source_count": len(observed_sources),
        "usable_evidence_present": bool(source_refs),
        "public_source_status_counts": _status_counts(sources),
        "evidence_gaps": list(dict.fromkeys(evidence_gaps)),
        "source_refs": list(dict.fromkeys(source_refs)),
        "document_profiles": [_document_profile(item) for item in usable_documents],
        "facts_policy": "Source records support observations only; hypotheses and inferences must be labeled separately.",
    }


def _document_profile(document: dict[str, Any]) -> dict[str, Any]:
    profile: dict[str, Any] = {
        "source_ref": document.get("source_ref"),
        "name": document.get("name"),
        "suffix": document.get("suffix"),
        "chars": len(str(document.get("text") or "")),
    }
    if document.get("suffix") != ".csv":
        return profile
    try:
        rows = list(csv.DictReader(io.StringIO(str(document.get("text") or ""))))
    except csv.Error as exc:
        return {**profile, "profile_status": "failed", "warning": str(exc)[:500]}
    columns = list(rows[0]) if rows else []
    numeric: dict[str, dict[str, float | int]] = {}
    categorical: dict[str, list[dict[str, Any]]] = {}
    for column in columns:
        values = [str(row.get(column) or "").strip() for row in rows]
        parsed: list[float] = []
        for value in values:
            try:
                parsed.append(float(value))
            except ValueError:
                parsed = []
                break
        if parsed and len(parsed) == len(values):
            numeric[column] = {
                "count": len(parsed),
                "min": round(min(parsed), 4),
                "mean": round(sum(parsed) / len(parsed), 4),
                "max": round(max(parsed), 4),
            }
        else:
            counts: dict[str, int] = {}
            for value in values:
                if value:
                    counts[value] = counts.get(value, 0) + 1
            categorical[column] = [
                {"value": value, "count": count}
                for value, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:8]
            ]
    return {
        **profile,
        "profile_status": "described_not_interpreted",
        "row_count": len(rows),
        "columns": columns,
        "numeric_summary": numeric,
        "categorical_summary": categorical,
    }


def deterministic_research_posture(evidence: dict[str, Any]) -> dict[str, Any]:
    gaps = len(evidence.get("evidence_gaps") or [])
    if not evidence.get("usable_evidence_present"):
        action, confidence = "gather_more_evidence", "low"
    elif gaps >= 3:
        action, confidence = "gather_more_evidence", "low"
    elif gaps:
        action, confidence = "review_research_packet", "medium"
    else:
        action, confidence = "review_research_packet", "high"
    return {
        "recommended_action": action,
        "confidence": confidence,
        "rationale": "The review posture follows evidence coverage and does not validate a hypothesis or authorize an experiment.",
    }


def prepare_evidence(ctx: dict[str, Any], **_options: Any) -> dict[str, Any]:
    state = _state(ctx)
    inputs = _inputs(ctx)
    llm_mode = str((ctx["config"].get("llm") or {}).get("mode") or "live")
    prepared = prepare_evidence_context(
        ctx["config"], inputs, Path(ctx["blueprint_dir"]), ctx["run_id"],
        quick_test=llm_mode in {"fake", "mock"} or bool((ctx["config"].get("execution") or {}).get("quick_test")),
    )
    state.update({"inputs": inputs, "documents": prepared["documents"], "rag": prepared["rag"], "sources": prepared["sources"], "evidence": prepared["evidence"], "posture": deterministic_research_posture(prepared["evidence"]), "warnings": prepared["warnings"]})
    _save(ctx, state)
    return {"source_count": len(prepared["sources"]), "document_count": len(prepared["documents"])}


__all__ = [
    "_load_web_browser_skill",
    "_status_counts",
    "build_public_queries",
    "deterministic_research_posture",
    "_document_profile",
    "prepare_evidence",
    "prepare_evidence_context",
    "research_evidence",
    "research_public_sources",
    "resolve_output_folder",
    "sanitize_public_text",
]
