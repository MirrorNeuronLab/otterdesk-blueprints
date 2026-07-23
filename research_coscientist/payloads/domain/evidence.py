"""Evidence preparation, privacy-safe source research, and deterministic posture."""

from __future__ import annotations

import os
import re
import urllib.parse
from pathlib import Path
from typing import Any

from .common import DEFAULT_OUTPUT_FOLDER, _now, runtime_asset_root
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


def _load_w3m() -> tuple[Any, Any, Any]:
    try:
        from mn_w3m_browser_skill import W3mBrowserConfig, browse_url, research_topic
        return W3mBrowserConfig, browse_url, research_topic
    except Exception:
        return None, None, None


def _load_rendered_browser() -> tuple[Any, Any]:
    try:
        from mn_web_browser_skill import WebBrowserConfig, scrape_page
        return WebBrowserConfig, scrape_page
    except Exception:
        return None, None


def _source_record(*, url: str, title: str, snippet: str, status: str, skill: str, query: str, warning: str = "") -> dict[str, Any]:
    lowered = f"{title} {snippet} {warning}".lower()
    if any(marker in lowered for marker in ("captcha", "login required", "robots.txt", "access denied", "blocked")):
        status = "blocked"
    return {
        "source_ref": f"web:{_sha256(url or query)[:12]}",
        "url": url,
        "title": title or url or skill,
        "snippet": snippet[:1800],
        "status": status,
        "skill": skill,
        "query": query,
        "retrieved_at": _now(),
        "warning": warning,
    }


def _normalize_browser_result(result: Any, query: str, skill: str) -> list[dict[str, Any]]:
    if isinstance(result, dict):
        candidates = result.get("sources") or result.get("results") or result.get("items") or [result]
    elif isinstance(result, list):
        candidates = result
    else:
        candidates = [{"text": str(result or "")}] if result else []
    records = []
    for item in candidates:
        if isinstance(item, str):
            item = {"text": item}
        records.append(_source_record(
            url=str(item.get("url") or item.get("link") or ""),
            title=str(item.get("title") or item.get("name") or ""),
            snippet=str(item.get("snippet") or item.get("text") or item.get("content") or ""),
            status=str(item.get("status") or "observed"),
            skill=skill,
            query=query,
            warning=str(item.get("warning") or ""),
        ))
    return records


def research_public_sources(queries: list[str], config: dict[str, Any], *, quick_test: bool = False) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    internet = config.get("internet_research") if isinstance(config.get("internet_research"), dict) else {}
    if not internet.get("enabled", True):
        return [], [{"status": "disabled", "message": "Public research is disabled by configuration."}]
    if quick_test:
        return [], [{"status": "skipped_quick_test", "message": "Public research is skipped in fake/quick-test mode."}]
    sources: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    max_queries = int(internet.get("max_queries", 6))
    w3m_config_cls, browse_url, research_topic = _load_w3m()
    for query in queries[:max_queries]:
        if research_topic is None:
            warnings.append({"status": "skill_unavailable", "skill": "w3m_browser_skill", "message": "Install the w3m browser skill for public research."})
            break
        try:
            raw_config = {"timeout_seconds": internet.get("timeout_seconds", 20), "max_chars": internet.get("max_chars", 12000)}
            browser_config = _instantiate(w3m_config_cls, raw_config)
            result = _call_optional(research_topic, query=query, topic=query, config=browser_config, browser_config=browser_config, max_sources=int(internet.get("max_sources", 8)))
            sources.extend(_normalize_browser_result(result, query, "w3m_browser_skill"))
        except Exception as exc:
            warnings.append({"status": "failed", "skill": "w3m_browser_skill", "query": query, "message": str(exc)})
    if not sources and internet.get("rendered_browser", {}).get("enabled", True):
        rendered_cls, scrape_page = _load_rendered_browser()
        if scrape_page is None:
            warnings.append({"status": "skill_unavailable", "skill": "web_browser_skill", "message": "Rendered-browser fallback is unavailable."})
        else:
            for query in queries[:2]:
                url = "https://www.google.com/search?" + urllib.parse.urlencode({"q": query})
                try:
                    browser_config = _instantiate(rendered_cls, {"timeout_seconds": 30, "max_chars": 12000})
                    result = _call_optional(scrape_page, url=url, config=browser_config, browser_config=browser_config)
                    sources.extend(_normalize_browser_result(result, query, "web_browser_skill"))
                except Exception as exc:
                    warnings.append({"status": "failed", "skill": "web_browser_skill", "url": url, "message": str(exc)})
    return sources, warnings


def _instantiate(cls: Any, values: dict[str, Any]) -> Any:
    if cls is None:
        return values
    try:
        params = inspect.signature(cls).parameters
        return cls(**{key: value for key, value in values.items() if key in params})
    except (TypeError, ValueError):
        return cls()


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
        "facts_policy": "Source records support observations only; hypotheses and inferences must be labeled separately.",
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
    "_instantiate",
    "_load_rendered_browser",
    "_load_w3m",
    "_normalize_browser_result",
    "_source_record",
    "_status_counts",
    "build_public_queries",
    "deterministic_research_posture",
    "prepare_evidence",
    "prepare_evidence_context",
    "research_evidence",
    "research_public_sources",
    "resolve_output_folder",
    "sanitize_public_text",
]
