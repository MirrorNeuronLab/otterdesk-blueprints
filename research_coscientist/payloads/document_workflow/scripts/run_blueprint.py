#!/usr/bin/env python3.11
"""Run the mixed deterministic/autonomous Research Co-Scientist workflow.

Deterministic stages own source records, evidence gaps, and review boundaries.
One job-scoped OpenShell worker owns every autonomous phase. Models may set or
refine goals, create prompts, call allowlisted skills, generate bounded code,
and critique hypotheses, but cannot turn a hypothesis into a fact or authorize
an experiment, public claim, or consequential decision.
"""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import inspect
import json
import os
import re
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


RUNTIME_SKILL_PACKAGES = (
    "mirrorneuron-blueprint-support-skill",
    "mirrorneuron-llm-ocr-skill",
    "mirrorneuron-rag-skill",
    "mirrorneuron-w3m-browser-skill",
    "mirrorneuron-web-browser-skill",
    "mirrorneuron-autonomous-research-skill",
)


def _bootstrap_runtime() -> None:
    for parent in Path(__file__).resolve().parents:
        helper = parent / "otterdesk_blueprint_env.py"
        if helper.exists():
            spec = importlib.util.spec_from_file_location("otterdesk_blueprint_env", helper)
            if spec is None or spec.loader is None:
                return
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            module.bootstrap_blueprint_runtime(__file__, packages=RUNTIME_SKILL_PACKAGES)
            return


_bootstrap_runtime()

from mn_blueprint_support import (  # noqa: E402
    PromptLibrary,
    architecture_contract,
    create_runtime_context,
    get_llm_client,
    llm_usage,
    load_config,
    resolve_actor_specs,
    resolve_input_overrides,
    run_actor_reviews,
    run_blueprint_cli,
    utc_now_iso,
)
from mn_blueprint_support.web_ui import maybe_write_static_output  # noqa: E402
from mn_autonomous_research_skill import (  # noqa: E402
    AutonomousResearchSession,
    GeneratedCodePolicy,
    ToolRegistry,
    create_research_goal,
)

try:  # Optional in local fake/quick-test environments.
    from mn_rag_skill import build_rag_context, prepare_blueprint_knowledge_rag
except Exception:  # pragma: no cover - depends on the runtime skill image
    build_rag_context = None
    prepare_blueprint_knowledge_rag = None

try:  # Optional OCR dependency; text-like inputs never require it.
    from mn_llm_ocr_skill import extract_document
except Exception:  # pragma: no cover - depends on the runtime skill image
    extract_document = None


BLUEPRINT_ID = "research_coscientist"
BLUEPRINT_NAME = "Research Co-Scientist"
CATEGORY = "Science"
OUTPUT_TYPE = "research_coscientist_packet"
DEFAULT_OUTPUT_FOLDER = "~/Downloads/research_coscientist"
SUPPORTED_SUFFIXES = {".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp", ".txt", ".md", ".json", ".csv"}
TEXT_SUFFIXES = {".txt", ".md", ".json", ".csv"}
RESEARCH_ACTIONS = {"review_research_packet", "gather_more_evidence"}
BLOCKED_ACTIONS = [
    "execute_unapproved_experiment",
    "claim_validated_result",
    "publish_or_submit_manuscript",
    "contact_external_research_participant",
    "make_clinical_or_safety_decision",
]
PROMPTS = PromptLibrary.from_script(__file__, parents_up=1)


def load_prompt(name: str) -> str:
    return PROMPTS.load(name)


def _script_blueprint_root() -> Path:
    script = Path(__file__).resolve()
    for parent in script.parents:
        if (parent / "manifest.json").exists():
            return parent
    return script.parents[3]


def runtime_asset_root() -> Path:
    """Return the self-contained directory uploaded to every workflow worker."""
    return Path(__file__).resolve().parents[1]


def default_config_path() -> Path:
    configured = os.environ.get("MN_BLUEPRINT_CONFIG_PATH")
    if configured and Path(configured).expanduser().exists():
        return Path(configured).expanduser()
    bundle = os.environ.get("MN_BLUEPRINT_BUNDLE_DIR")
    if bundle and (Path(bundle).expanduser() / "config" / "default.json").exists():
        return Path(bundle).expanduser() / "config" / "default.json"
    if os.environ.get("MN_BLUEPRINT_CONFIG_JSON"):
        # Docker worker attempts may carry embedded config without mounting
        # the bundle's config file. Resolve relative to the attempt root.
        return Path(__file__).resolve().parents[2] / "config" / "default.json"
    return _script_blueprint_root() / "config" / "default.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _sha256(value: str | bytes) -> str:
    raw = value.encode("utf-8") if isinstance(value, str) else value
    return hashlib.sha256(raw).hexdigest()


def _json_safe(value: Any) -> Any:
    try:
        json.dumps(value)
        return value
    except (TypeError, ValueError):
        if isinstance(value, dict):
            return {str(k): _json_safe(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [_json_safe(v) for v in value]
        return str(value)


def _compact(value: Any, limit: int = 1800) -> str:
    text = value if isinstance(value, str) else json.dumps(_json_safe(value), sort_keys=True, default=str)
    return text if len(text) <= limit else text[: limit - 3] + "..."


def normalize_inputs(inputs: dict[str, Any] | None) -> dict[str, Any]:
    payload = copy.deepcopy(inputs or {})
    payload["research_goal"] = str(payload.get("research_goal") or payload.get("goal") or payload.get("query") or "").strip()
    payload["research_domain"] = str(payload.get("research_domain") or payload.get("domain") or "general").strip()
    payload["research_question"] = str(payload.get("research_question") or payload.get("question") or "").strip()
    payload["scope"] = str(payload.get("scope") or "").strip()
    payload["success_criteria"] = _as_list(payload.get("success_criteria"))
    payload["seed_hypotheses"] = _as_list(payload.get("seed_hypotheses"))
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


def resolve_input_folder(config: dict[str, Any], inputs: dict[str, Any], root: Path) -> Path | None:
    value = inputs.get("input_folder") or (config.get("inputs") or {}).get("payload", {}).get("input_folder")
    if not value:
        return None
    path = expand_runtime_path(value)
    if not path.is_absolute():
        bundled_path = runtime_asset_root() / path
        if bundled_path.exists():
            return bundled_path
        path = root.parent / path
    return path


def _looks_like_sandbox_home(path: Path) -> bool:
    raw = str(path)
    return raw in {"/root", "/tmp", "/var/root"} or raw.startswith(
        ("/root/", "/tmp/", "/private/tmp/", "/var/root/", "/var/folders/", "/private/var/folders/")
    )


def _home_from_mirror_neuron_path(value: str | Path | None) -> Path | None:
    if not value:
        return None
    path = Path(value).expanduser()
    parts = path.parts
    if ".mn" not in parts:
        return None
    marker_index = parts.index(".mn")
    if marker_index <= 0:
        return None
    home = Path(*parts[:marker_index])
    return home if str(home) and not _looks_like_sandbox_home(home) else None


def _home_from_macos_users_dir() -> Path | None:
    users_dir = Path("/Users")
    if not users_dir.exists():
        return None
    names = [os.environ.get("SUDO_USER"), os.environ.get("LOGNAME"), os.environ.get("USER")]
    for name in names:
        if not name or name in {"root", "daemon", "nobody"}:
            continue
        candidate = users_dir / name
        if candidate.exists() and not _looks_like_sandbox_home(candidate):
            return candidate
    candidates = [
        path
        for path in users_dir.iterdir()
        if path.is_dir()
        and path.name not in {"Shared", "Guest", "Deleted Users"}
        and not path.name.startswith(".")
        and ((path / "Downloads").exists() or (path / ".mn").exists())
    ]
    if len(candidates) == 1 and not _looks_like_sandbox_home(candidates[0]):
        return candidates[0]
    return None


def runtime_user_home() -> Path:
    for env_name in ("MN_OUTPUT_HOME", "MN_USER_HOME", "OTTERDESK_USER_HOME"):
        value = os.environ.get(env_name)
        if value:
            return Path(value).expanduser()
    for env_name in ("MN_RUN_DIR", "MN_RUNS_ROOT", "MN_HOME", "OTTERDESK_RUN_DIR", "OTTERDESK_RUNS_ROOT"):
        home = _home_from_mirror_neuron_path(os.environ.get(env_name))
        if home:
            return home
    expanded = Path("~").expanduser()
    if not _looks_like_sandbox_home(expanded):
        return expanded
    try:
        import pwd

        account_home = Path(pwd.getpwuid(os.getuid()).pw_dir)
        if account_home and not _looks_like_sandbox_home(account_home):
            return account_home
    except Exception:
        pass
    macos_home = _home_from_macos_users_dir()
    if macos_home:
        return macos_home
    return expanded


def expand_runtime_path(value: str | Path) -> Path:
    raw = str(value)
    if raw == "~":
        return runtime_user_home()
    if raw.startswith("~/") or raw.startswith("~\\"):
        return runtime_user_home() / raw[2:]
    return Path(raw).expanduser()


def load_input_documents(folder: Path | None, config: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if folder is None or not folder.exists():
        return [], [] if folder is None else [{"status": "missing", "path": str(folder), "warning": "input_folder does not exist"}]
    records: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    for path in sorted(item for item in folder.rglob("*") if item.is_file() and item.suffix.lower() in SUPPORTED_SUFFIXES):
        suffix = path.suffix.lower()
        try:
            if suffix in TEXT_SUFFIXES:
                text = path.read_text(encoding="utf-8", errors="replace")
                method = "direct_text"
            elif extract_document is not None:
                text = _call_optional(extract_document, path=str(path), file_path=str(path), config=config) or ""
                method = "ocr_skill" if text else "ocr_empty"
            else:
                text = ""
                method = "ocr_unavailable"
            record = {
                "path": str(path),
                "name": path.name,
                "suffix": suffix,
                "bytes": path.stat().st_size,
                "sha256": _sha256(path.read_bytes()),
                "extraction_method": method,
                "status": "extracted" if text else "review_required",
                "text": text[:20000],
                "source_ref": f"local:{path.name}",
            }
            records.append(record)
            if not text:
                warnings.append({"path": str(path), "status": "review_required", "message": f"No usable text extracted from {path.name}."})
        except Exception as exc:  # Keep one bad document from hiding the rest.
            warnings.append({"path": str(path), "status": "failed", "message": str(exc)})
    return records, warnings


def _call_optional(function: Callable[..., Any], **kwargs: Any) -> Any:
    try:
        signature = inspect.signature(function)
        accepted = {name: value for name, value in kwargs.items() if name in signature.parameters}
        return function(**accepted)
    except (TypeError, ValueError):
        return function(next(iter(kwargs.values())))


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


def _chunks(text: str, size: int) -> list[str]:
    words = text.split()
    return [" ".join(words[index : index + size]) for index in range(0, len(words), size)] or [""]


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


def _fallback_hypotheses(inputs: dict[str, Any], evidence: dict[str, Any]) -> list[dict[str, str]]:
    seed_hypotheses = list(inputs.get("seed_hypotheses") or [])
    if not seed_hypotheses:
        seed_hypotheses = [
            f"A controlled intervention related to the research goal may change the target outcome: {inputs.get('research_goal')}."
        ]
    refs = list(evidence.get("source_refs") or [])
    return [
        {
            "statement": statement[:800],
            "prediction": "A pre-specified measurement would differ from a matched baseline if this hypothesis is correct.",
            "evidence_support": refs[:4],
            "counterargument": "The apparent change could be explained by an uncontrolled confounder, measurement error, or an alternative mechanism.",
            "disconfirming_observation": "A controlled test fails to show the predicted difference after checking measurement quality and pre-specified controls.",
        }
        for statement in seed_hypotheses[:3]
    ]


def _normalize_hypotheses(
    candidates: Any, inputs: dict[str, Any], evidence: dict[str, Any]
) -> list[dict[str, Any]]:
    raw = candidates if isinstance(candidates, list) else []
    normalized: list[dict[str, Any]] = []
    for candidate in raw[:3]:
        if not isinstance(candidate, dict):
            continue
        statement = str(candidate.get("statement") or candidate.get("hypothesis") or "").strip()
        if not statement:
            continue
        normalized.append(
            {
                "hypothesis_id": f"H{len(normalized) + 1}",
                "statement": statement[:800],
                "prediction": str(candidate.get("prediction") or "A pre-specified measurement differs from baseline if the hypothesis is correct.")[:800],
                "evidence_support": candidate.get("evidence_support") or list(evidence.get("source_refs") or [])[:4],
                "counterargument": str(candidate.get("counterargument") or "A competing explanation or unmeasured confounder could account for the observation.")[:800],
                "disconfirming_observation": str(candidate.get("disconfirming_observation") or "A controlled test does not show the predicted difference.")[:800],
                "status": "hypothesis_for_review",
            }
        )
    if not normalized:
        normalized = _fallback_hypotheses(inputs, evidence)
        for index, item in enumerate(normalized, start=1):
            item["hypothesis_id"] = f"H{index}"
            item["status"] = "hypothesis_for_review"
    return normalized


def ask_llm_for_research_packet(
    llm: Any, inputs: dict[str, Any], evidence: dict[str, Any], rag: dict[str, Any], posture: dict[str, Any]
) -> dict[str, Any]:
    fallback = {
        **posture,
        "candidate_hypotheses": _fallback_hypotheses(inputs, evidence),
        "tool_requests": [],
        "generated_python": "",
    }
    user = json.dumps(
        {
            "inputs": inputs,
            "deterministic_evidence": evidence,
            "retrieved_context": rag.get("context", ""),
            "review_posture": posture,
        },
        sort_keys=True,
        default=str,
    )
    try:
        response = llm.generate_json(
            system_prompt=load_prompt("research-packet-system.md"),
            user_prompt=f"{load_prompt('research-review-task.md')}\n\n{user}",
            fallback=fallback,
        )
    except Exception:
        response = fallback
    if not isinstance(response, dict):
        response = fallback
    action = str(response.get("recommended_action") or posture["recommended_action"]).lower()
    if action not in RESEARCH_ACTIONS:
        action = posture["recommended_action"]
    confidence = str(response.get("confidence") or posture["confidence"]).lower()
    if confidence not in {"low", "medium", "high"}:
        confidence = posture["confidence"]
    return {
        "recommended_action": action,
        "confidence": confidence,
        "rationale": str(response.get("rationale") or posture["rationale"])[:2000],
        "candidate_hypotheses": _normalize_hypotheses(response.get("candidate_hypotheses"), inputs, evidence),
        "tool_requests": response.get("tool_requests") if isinstance(response.get("tool_requests"), list) else [],
        "generated_python": str(response.get("generated_python") or "")[:40000],
    }


def _document_tool(documents: list[dict[str, Any]], arguments: dict[str, Any]) -> dict[str, Any]:
    query = str(arguments.get("query") or arguments.get("source_ref") or "").strip().lower()
    matches = []
    for document in documents:
        haystack = f"{document.get('source_ref', '')} {document.get('name', '')} {document.get('text', '')}".lower()
        if not query or query in haystack:
            matches.append(
                {
                    "source_ref": document.get("source_ref"),
                    "name": document.get("name"),
                    "text": str(document.get("text") or "")[:4000],
                    "status": document.get("status"),
                }
            )
    return {"query": query, "matches": matches[:5]}


def _rank_hypotheses_tool(arguments: dict[str, Any]) -> dict[str, Any]:
    candidates = arguments.get("candidates") if isinstance(arguments.get("candidates"), list) else []
    ranked = []
    for index, candidate in enumerate(candidates[:20]):
        item = candidate if isinstance(candidate, dict) else {"statement": str(candidate)}
        support = item.get("evidence_support") if isinstance(item.get("evidence_support"), list) else []
        ranked.append(
            {
                "index": index,
                "statement": str(item.get("statement") or item.get("hypothesis") or "")[:800],
                "traceable_support_count": len([ref for ref in support if str(ref).strip()]),
            }
        )
    ranked.sort(key=lambda item: (-item["traceable_support_count"], item["index"]))
    return {"ranking_rule": "traceable_support_count_then_input_order", "ranked": ranked}


def run_autonomous_research(
    llm: Any,
    inputs: dict[str, Any],
    evidence: dict[str, Any],
    rag: dict[str, Any],
    posture: dict[str, Any],
    config: dict[str, Any],
    documents: list[dict[str, Any]],
    sources: list[dict[str, Any]],
    *,
    workspace: Path,
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    """Run every autonomous subphase through one auditable session.

    The workflow manifest places this function in its only OpenShell node.
    Direct fake-mode calls exercise the same contract for local tests.
    """

    autonomous_config = config.get("agentic_research") if isinstance(config.get("agentic_research"), dict) else {}
    allowed_tools = {
        str(item)
        for item in autonomous_config.get("allowed_tools") or []
        if str(item) in {"document_extract", "browser_search", "browser_page", "knowledge_retrieve", "hypothesis_rank", "finish"}
    }
    registry = ToolRegistry(allowed_tools)
    warnings: list[dict[str, Any]] = []
    if "document_extract" in allowed_tools:
        registry.register("document_extract", lambda arguments: _document_tool(documents, arguments))
    if "knowledge_retrieve" in allowed_tools:
        registry.register(
            "knowledge_retrieve",
            lambda arguments: {
                "query": str(arguments.get("query") or inputs.get("research_question") or inputs.get("research_goal"))[:1000],
                "context": str(rag.get("context") or "")[:6000],
                "citations": list(rag.get("citations") or [])[:20],
            },
        )
    if "hypothesis_rank" in allowed_tools:
        registry.register("hypothesis_rank", _rank_hypotheses_tool)
    if "finish" in allowed_tools:
        registry.register("finish", lambda arguments: {"status": "finished", "summary": str(arguments.get("summary") or "")[:2000]})

    quick_test = str((config.get("llm") or {}).get("mode") or "").lower() in {"fake", "mock"} or bool(
        (config.get("execution") or {}).get("quick_test")
    )

    def public_search(arguments: dict[str, Any]) -> dict[str, Any]:
        query = sanitize_public_text(arguments.get("query") or arguments.get("url") or "")
        if not query:
            raise ValueError("public research tool requires a privacy-safe query")
        observed, tool_warnings = research_public_sources([query], config, quick_test=quick_test)
        sources.extend(observed)
        warnings.extend(tool_warnings)
        return {"query": query, "sources": observed, "warnings": tool_warnings}

    for tool_name in ("browser_search", "browser_page"):
        if tool_name in allowed_tools:
            registry.register(tool_name, public_search)

    generated = autonomous_config.get("generated_code") if isinstance(autonomous_config.get("generated_code"), dict) else {}
    goal = create_research_goal(
        inputs.get("research_goal") or "Investigate the supplied research question",
        question=inputs.get("research_question") or "",
        success_criteria=list(inputs.get("success_criteria") or []),
        constraints=inputs.get("constraints") or {},
    )
    session = AutonomousResearchSession(
        goal,
        registry,
        workspace / str(generated.get("workspace") or "generated_research"),
        max_tool_calls=max(0, int(autonomous_config.get("max_total_tool_calls", 12))),
        code_policy=GeneratedCodePolicy(
            timeout_seconds=max(1, int(generated.get("timeout_seconds", 15))),
            max_output_chars=max(1000, int(generated.get("max_output_chars", 20000))),
            max_memory_mb=max(64, int(generated.get("max_memory_mb", 256))),
        ),
    )
    context_refs = list(dict.fromkeys([*(evidence.get("source_refs") or []), *(rag.get("citations") or [])]))[:30]
    session.create_prompt(
        phase="goal_expansion",
        instructions=["Refine the goal into falsifiable questions without widening the supplied constraints.", "Keep facts, assumptions, and unknowns separate."],
        context_refs=context_refs,
        allowed_tools=[],
    )
    session.create_prompt(
        phase="exploration_and_adversarial_generation",
        instructions=["Explore competing mechanisms, not variations of one idea.", "Request allowlisted skills only when they can resolve a named gap.", "Attach source references or label the result as a hypothesis."],
        context_refs=context_refs,
        allowed_tools=sorted(allowed_tools - {"finish"}),
    )
    session.create_prompt(
        phase="computational_probe_and_synthesis",
        instructions=["Use generated Python only for bounded ranking, sensitivity, or consistency analysis.", "Treat code output as an internal probe, never as empirical validation.", "Produce at most three falsifiable candidates for deterministic verification."],
        context_refs=context_refs,
        allowed_tools=["hypothesis_rank"] if "hypothesis_rank" in allowed_tools else [],
    )

    recommendation = ask_llm_for_research_packet(llm, inputs, evidence, rag, posture)
    observations: list[dict[str, Any]] = []
    for index, request in enumerate(recommendation.pop("tool_requests", [])[: session.max_tool_calls], start=1):
        if not isinstance(request, dict):
            continue
        tool = str(request.get("tool") or "")
        arguments = request.get("arguments") if isinstance(request.get("arguments"), dict) else {}
        try:
            observation = session.use_tool(tool, arguments)
            observations.append({"request_index": index, "tool": tool, "status": "completed", "observation": _json_safe(observation)})
        except Exception as exc:
            observations.append({"request_index": index, "tool": tool, "status": "failed", "error": str(exc)[:1000]})
            warnings.append({"status": "autonomous_tool_failed", "tool": tool, "message": str(exc)[:1000]})

    generated_python = recommendation.pop("generated_python", "")
    code_result: dict[str, Any] | None = None
    if generated_python and autonomous_config.get("allow_generated_code", True):
        try:
            code_result = session.execute_python(
                generated_python,
                input_payload={
                    "evidence": evidence,
                    "candidate_hypotheses": recommendation.get("candidate_hypotheses") or [],
                    "tool_observations": observations,
                },
            )
            if code_result.get("status") != "completed":
                warnings.append({"status": "generated_code_failed", "message": str(code_result.get("stderr") or code_result.get("status"))[:1000]})
        except Exception as exc:
            warnings.append({"status": "generated_code_rejected", "message": str(exc)[:1000]})

    autonomous = {
        "schema_version": "mn.blueprint.autonomous_research.v1",
        "isolation_required": True,
        "runner": "openshell",
        "single_job_instance": True,
        "session": session.snapshot(),
        "tool_observations": observations,
        "generated_code_result": code_result,
    }
    return recommendation, autonomous, warnings


def _experiment_concepts(hypotheses: list[dict[str, Any]], inputs: dict[str, Any]) -> list[dict[str, Any]]:
    concepts = []
    for hypothesis in hypotheses:
        concepts.append(
            {
                "hypothesis_id": hypothesis["hypothesis_id"],
                "design_status": "concept_for_human_review",
                "baseline": "Pre-specified matched baseline or control condition.",
                "intervention": hypothesis["statement"],
                "measurements": ["primary outcome", "relevant confounders", "pre-specified safety or quality boundary"],
                "decision_rule": "Compare the pre-specified outcome with the baseline and report uncertainty, sensitivity checks, and deviations.",
                "approval_dependencies": ["qualified human review", *(["scope constraint review"] if inputs.get("constraints") else [])],
                "not_executed": True,
            }
        )
    return concepts


def build_research_packet(
    inputs: dict[str, Any],
    evidence: dict[str, Any],
    recommendation: dict[str, Any],
    rag: dict[str, Any],
    sources: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
    documents: list[dict[str, Any]],
    actor_findings: dict[str, Any],
    autonomous: dict[str, Any],
    run_id: str,
) -> dict[str, Any]:
    hypotheses = recommendation["candidate_hypotheses"]
    usable_evidence = bool(evidence.get("usable_evidence_present"))
    status = "review_ready" if usable_evidence else "needs_evidence"
    recommended_action = recommendation["recommended_action"] if usable_evidence else "gather_more_evidence"
    confidence = recommendation["confidence"] if usable_evidence else "low"
    recommendation_rationale = (
        recommendation["rationale"]
        if usable_evidence
        else "No extracted local document or observed public source is available for review."
    )
    source_refs = list(dict.fromkeys(evidence.get("source_refs") or []))
    next_steps = [
        "Review the evidence ledger and resolve the highest-impact gaps.",
        "Ask a qualified reviewer to validate the ranked hypotheses and experiment concepts.",
        "Obtain required safety, ethics, operational, or institutional approvals before any real-world action.",
    ]
    if not usable_evidence:
        next_steps = []
        if not evidence.get("usable_local_document_count"):
            next_steps.append("Provide an approved local paper, note, dataset, or measurement with usable text.")
        if not evidence.get("usable_public_source_count"):
            next_steps.append("Retry public retrieval or provide approved local evidence; no observed public source is available.")
        next_steps.append("Do not use the candidate hypotheses as an evidence-based recommendation until usable evidence is available.")
    return {
        "type": OUTPUT_TYPE,
        "schema_version": "mn.blueprint.research_coscientist.v2",
        "blueprint_id": BLUEPRINT_ID,
        "run_id": run_id,
        "status": status,
        "research_goal": inputs.get("research_goal"),
        "research_domain": inputs.get("research_domain"),
        "research_question": inputs.get("research_question"),
        "scope": inputs.get("scope"),
        "executive_summary": f"Research packet for: {inputs.get('research_goal') or 'unspecified research goal'}. Status: {status}. Posture: {recommended_action} with {confidence} confidence.",
        "recommended_action": recommended_action,
        "confidence": confidence,
        "recommendation_rationale": recommendation_rationale,
        "evidence": {
            "deterministic": evidence,
            "documents": [{key: value for key, value in item.items() if key != "text"} for item in documents],
            "public_sources": sources,
        },
        "hypothesis_ledger": hypotheses,
        "adversarial_review": {
            "required_for_each_hypothesis": ["counterargument", "disconfirming_observation"],
            "actor_findings": actor_findings,
        },
        "autonomous_research": autonomous,
        "experiment_concepts": _experiment_concepts(hypotheses, inputs),
        "knowledge_rag": {key: value for key, value in rag.items() if key not in {"_rag_config", "context"}},
        "evidence_gaps": evidence.get("evidence_gaps") or [],
        "warnings": warnings,
        "next_steps": next_steps,
        "source_refs": source_refs,
        "provenance_refs": ["inputs.json", "events.jsonl", "result.json"],
        "review_boundary": {
            "review_required": True,
            "blocked_actions": BLOCKED_ACTIONS,
            "reason": "Generated hypotheses and plans are decision support only; they are not validated results or authorization for research activity.",
        },
    }


def research_artifact_quality(packet: dict[str, Any]) -> dict[str, Any]:
    deterministic = (packet.get("evidence") or {}).get("deterministic") or {}
    usable_evidence = bool(deterministic.get("usable_evidence_present"))
    expected_status = "review_ready" if usable_evidence else "needs_evidence"
    checks = [
        {"name": "research_action_valid", "passed": packet.get("recommended_action") in RESEARCH_ACTIONS},
        {"name": "usable_evidence_present", "passed": usable_evidence},
        {"name": "packet_status_matches_evidence", "passed": packet.get("status") == expected_status},
        {"name": "hypotheses_labeled", "passed": all(item.get("status") == "hypothesis_for_review" for item in packet.get("hypothesis_ledger") or [])},
        {"name": "review_boundary_present", "passed": bool(packet.get("review_boundary"))},
        {"name": "autonomous_isolation_declared", "passed": (packet.get("autonomous_research") or {}).get("isolation_required") is True},
        {"name": "autonomous_trace_present", "passed": bool(((packet.get("autonomous_research") or {}).get("session") or {}).get("trace"))},
    ]
    return {
        "schema_version": "mn.blueprint.artifact_quality.v1",
        "status": "needs_evidence" if not usable_evidence else ("usable_with_review" if all(item["passed"] for item in checks) else "usable_with_review_warnings"),
        "review_required": True,
        "quality_checks": checks,
        "warnings": packet.get("warnings") or [],
    }


def render_research_markdown(packet: dict[str, Any]) -> str:
    deterministic = (packet.get("evidence") or {}).get("deterministic") or {}
    lines = [
        "# Research Co-Scientist Brief",
        "",
        f"**Research goal:** {packet.get('research_goal') or 'Not specified'}",
        f"**Domain:** {packet.get('research_domain') or 'General'}",
        f"**Status:** {packet.get('status')}",
        f"**Review posture:** {packet.get('recommended_action')}",
        f"**Confidence:** {packet.get('confidence')}",
        "",
        "## Executive Summary",
        str(packet.get("executive_summary") or ""),
        "",
        "## Evidence Coverage",
        f"- Local documents reviewed: {deterministic.get('document_count', 0)}",
        f"- Public sources observed: {deterministic.get('public_source_count', 0)}",
        f"- Usable evidence present: {'Yes' if deterministic.get('usable_evidence_present') else 'No'}",
        "",
        "## Candidate Hypotheses",
    ]
    for hypothesis in packet.get("hypothesis_ledger") or []:
        lines.extend([
            f"### {hypothesis.get('hypothesis_id')}: {hypothesis.get('statement')}",
            f"- Prediction: {hypothesis.get('prediction')}",
            f"- Counterargument: {hypothesis.get('counterargument')}",
            f"- Disconfirming observation: {hypothesis.get('disconfirming_observation')}",
        ])
    lines.extend(["", "## Evidence Gaps"])
    lines.extend(f"- {gap}" for gap in packet.get("evidence_gaps") or ["No gaps recorded."])
    lines.extend(["", "## Next Steps"])
    lines.extend(f"- {step}" for step in packet.get("next_steps") or [])
    lines.extend(["", "## Review Boundary"])
    lines.extend(f"- Do not: {action}" for action in (packet.get("review_boundary") or {}).get("blocked_actions") or BLOCKED_ACTIONS)
    lines.append("")
    return "\n".join(lines)


def write_research_outputs(
    packet: dict[str, Any], result: dict[str, Any], config: dict[str, Any], inputs: dict[str, Any]
) -> list[dict[str, str]]:
    output_dir = resolve_output_folder(config, inputs)
    if output_dir is None:
        return []
    output_dir.mkdir(parents=True, exist_ok=True)
    quality = research_artifact_quality(packet)
    health = {
        "schema_version": "mn.blueprint.run_health.v1",
        "status": "completed_with_warnings" if packet.get("warnings") else "completed",
        "warning_count": len(packet.get("warnings") or []),
        "llm": result.get("llm", {}),
    }
    review_ledger = [
        {"stage": "goal_framing", "status": "completed"},
        {"stage": "evidence_evaluation", "status": "completed", "source_refs": packet.get("source_refs", [])},
        {"stage": "hypothesis_and_adversarial_review", "status": "completed", "hypothesis_count": len(packet.get("hypothesis_ledger") or [])},
        {"stage": "human_review_gate", "status": "blocked_pending_review", "blocked_actions": BLOCKED_ACTIONS},
    ]
    packet["artifact_quality"] = quality
    packet["run_health"] = health
    packet["review_ledger"] = review_ledger
    paths = {
        "research_packet": output_dir / "research_packet.json",
        "research_brief": output_dir / "research_brief.md",
        "evidence_ledger": output_dir / "evidence_ledger.json",
        "hypothesis_ledger": output_dir / "hypothesis_ledger.json",
        "review_ledger": output_dir / "review_ledger.json",
        "artifact_quality": output_dir / "artifact_quality.json",
        "run_health": output_dir / "run_health.json",
    }
    output_files = [{"kind": kind, "path": str(path)} for kind, path in paths.items()]
    packet["output_files"] = output_files
    paths["research_packet"].write_text(json.dumps(packet, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    paths["research_brief"].write_text(render_research_markdown(packet), encoding="utf-8")
    paths["evidence_ledger"].write_text(json.dumps(packet["evidence"], indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    paths["hypothesis_ledger"].write_text(json.dumps(packet["hypothesis_ledger"], indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    paths["review_ledger"].write_text(json.dumps(review_ledger, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    paths["artifact_quality"].write_text(json.dumps(quality, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    paths["run_health"].write_text(json.dumps(health, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    return output_files


def run_blueprint(
    blueprint_id: str = BLUEPRINT_ID,
    *,
    inputs: dict[str, Any] | None = None,
    llm_client: Any | None = None,
    config: dict[str, Any] | None = None,
    config_path: str | Path | None = None,
    config_json: str | None = None,
    run_id: str | None = None,
    runs_root: str | Path | None = None,
    input_adapter: str | None = None,
    input_file: str | Path | None = None,
    write_run_store: bool | None = None,
) -> dict[str, Any]:
    if blueprint_id != BLUEPRINT_ID:
        raise ValueError(f"this runner handles {BLUEPRINT_ID!r}, got {blueprint_id!r}")
    resolved_default_config = default_config_path()
    embedded_config_json = config_json or os.environ.get("MN_BLUEPRINT_CONFIG_JSON")
    resolved_config = load_config(
        BLUEPRINT_ID,
        default_config_path=resolved_default_config if resolved_default_config.exists() else None,
        config=config,
        config_path=config_path,
        config_json=embedded_config_json,
        runs_root=runs_root,
        run_id=run_id,
        input_adapter=input_adapter,
        input_file=input_file,
        write_run_store=write_run_store,
    )
    adapter_inputs, input_source = resolve_input_overrides(resolved_config)
    runtime_inputs = normalize_inputs({**((resolved_config.get("inputs") or {}).get("payload") or {}), **adapter_inputs, **(inputs or {})})
    root = _script_blueprint_root()
    llm_mode = str((resolved_config.get("llm") or {}).get("mode") or "ollama")
    llm = llm_client or get_llm_client("fake" if llm_mode in {"fake", "mock"} else None)
    context = create_runtime_context(BLUEPRINT_ID, resolved_config, runtime_inputs, input_source)
    context.start()
    try:
        prepared = prepare_evidence_context(
            resolved_config,
            runtime_inputs,
            root,
            context.run_id,
            quick_test=llm_mode in {"fake", "mock"} or bool((resolved_config.get("execution") or {}).get("quick_test")),
        )
        folder = prepared["folder"]
        documents = prepared["documents"]
        rag = prepared["rag"]
        sources = prepared["sources"]
        evidence = prepared["evidence"]
        context.event("inputs_loaded", {"research_goal": runtime_inputs["research_goal"], "research_domain": runtime_inputs["research_domain"], "document_count": len(documents), "input_folder": str(folder) if folder else None})
        context.event("knowledge_rag_prepared", {"status": rag.get("status"), "citations": rag.get("citations", []), "user_documents_indexed": len(rag.get("user_documents_indexed") or [])})
        context.event("public_research_completed", {"source_count": len(sources), "warning_count": len(prepared["public_research_warnings"])})
        deterministic = deterministic_research_posture(evidence)
        context.event(
            "autonomous_research_started",
            {
                "runner": "openshell",
                "single_job_instance": True,
                "allowed_tools": (resolved_config.get("agentic_research") or {}).get("allowed_tools", []),
            },
        )
        recommendation, autonomous, autonomous_warnings = run_autonomous_research(
            llm,
            runtime_inputs,
            evidence,
            rag,
            deterministic,
            resolved_config,
            documents,
            sources,
            workspace=Path(os.environ.get("MN_WORKDIR") or context.run_dir or "/tmp/research-coscientist"),
        )
        context.event(
            "autonomous_research_completed",
            {
                "tool_calls": autonomous["session"]["tool_calls_used"],
                "generated_code_runs": autonomous["session"]["generated_code_runs"],
                "warning_count": len(autonomous_warnings),
            },
        )
        actor_state: dict[str, Any] = {}
        actor_findings = run_actor_reviews(
            config=resolved_config,
            llm=llm,
            actor_ids=list(resolve_actor_specs(resolved_config).keys()),
            state=actor_state,
            task=load_prompt("research-review-task.md"),
            context={"inputs": runtime_inputs, "evidence": evidence, "recommendation": recommendation, "rag": rag, "sources": sources},
            event_sink=context,
        )
        warnings = [*prepared["warnings"], *autonomous_warnings]
        final = build_research_packet(
            runtime_inputs,
            evidence,
            recommendation,
            rag,
            sources,
            warnings,
            documents,
            actor_findings,
            autonomous,
            context.run_id,
        )
        result = {
            "identity": {"blueprint_id": BLUEPRINT_ID, "name": BLUEPRINT_NAME, "run_id": context.run_id},
            "blueprint": BLUEPRINT_ID,
            "name": BLUEPRINT_NAME,
            "category": CATEGORY,
            "description": "A research co-scientist with deterministic evidence and verification stages around one isolated autonomous OpenShell worker.",
            "run": {"run_id": context.run_id, "run_dir": str(context.run_dir) if context.run_dir else None, "status": "completed"},
            "architecture": architecture_contract(resolved_config, input_source),
            "config": resolved_config,
            "inputs": runtime_inputs,
            "input_source": input_source,
            "runtime_features": ["deterministic evidence preparation", "single job-scoped OpenShell autonomous worker", "on-demand mn-skills tools", "bounded generated Python", "adversarial hypothesis review", "deterministic artifact verification", "human review gate"],
            "knowledge_rag": rag,
            "research_sources": sources,
            "evidence": evidence,
            "research_posture": recommendation,
            "autonomous_research": autonomous,
            "final_artifact": final,
            "artifacts": [{"artifact_id": "final_artifact", "type": "final_artifact", "path": "final_artifact.json", "schema_version": "mn.blueprint.final_artifact.v1", "source_refs": ["inputs.json", "events.jsonl", "result.json"]}],
            "llm": llm_usage(llm),
        }
        final["llm_usage"] = result["llm"]
        output_files = write_research_outputs(final, result, resolved_config, runtime_inputs)
        if output_files:
            result["output_files"] = output_files
            context.event("user_output_bundle_written", {"output_files": output_files})
        web_ui = maybe_write_static_output(context.run_store, result, resolved_config)
        if web_ui:
            result["web_ui"] = web_ui.to_dict()
        context.finish(result)
        return result
    except Exception as error:
        context.fail(error)
        raise


def _runtime_message_value(message: Any | None = None) -> Any:
    if message is not None:
        return message
    path = os.environ.get("MN_MESSAGE_FILE")
    if not path or not Path(path).is_file():
        return {}
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _runtime_workflow_payload(message: Any | None = None) -> dict[str, Any]:
    raw = _runtime_message_value(message)

    def find(value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            payload = value.get("workflow_payload")
            if isinstance(payload, dict):
                return payload
            # Runner envelopes carry the current command output in ``sandbox.stdout``
            # and the prior workflow message in ``input``. Prefer the current result;
            # otherwise a multi-stage workflow can accidentally unwrap stale input.
            for key in ("stdout", "sandbox", "body", "payload", "data", "message", "content", "input"):
                found = find(value.get(key))
                if found:
                    return found
            for nested in value.values():
                found = find(nested)
                if found:
                    return found
        elif isinstance(value, list):
            for nested in value:
                found = find(nested)
                if found:
                    return found
        elif isinstance(value, str) and value.strip().startswith(("{", "[")):
            try:
                return find(json.loads(value))
            except json.JSONDecodeError:
                return {}
        return {}

    return find(raw)


def _runtime_message_inputs(message: Any | None = None) -> dict[str, Any]:
    interesting = {
        "research_goal",
        "goal",
        "research_domain",
        "domain",
        "research_question",
        "question",
        "scope",
        "constraints",
        "input_folder",
        "output_folder",
    }

    def find(value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            if interesting & set(value):
                return dict(value)
            for key in ("kwargs", "payload", "body", "data", "message", "content", "input"):
                found = find(value.get(key))
                if found:
                    return found
            for nested in value.values():
                found = find(nested)
                if found:
                    return found
        elif isinstance(value, list):
            for nested in value:
                found = find(nested)
                if found:
                    return found
        elif isinstance(value, str) and value.strip().startswith(("{", "[")):
            try:
                return find(json.loads(value))
            except json.JSONDecodeError:
                return {}
        return {}

    return find(_runtime_message_value(message))


def _resolve_runtime_stage_request(context: Any | None = None) -> tuple[dict[str, Any], dict[str, Any], Any, dict[str, Any]]:
    embedded_config_json = os.environ.get("MN_BLUEPRINT_CONFIG_JSON")
    resolved_default_config = default_config_path()
    resolved_config = load_config(
        BLUEPRINT_ID,
        default_config_path=resolved_default_config if resolved_default_config.exists() else None,
        config=getattr(context, "config", None) or None,
        config_json=embedded_config_json,
        run_id=getattr(context, "run_id", None) or os.environ.get("MN_JOB_ID") or None,
        write_run_store=False,
    )
    adapter_inputs, input_source = resolve_input_overrides(resolved_config)
    message = getattr(context, "message", None)
    previous = _runtime_workflow_payload(message)
    previous_inputs = previous.get("inputs") if isinstance(previous.get("inputs"), dict) else {}
    runtime_inputs = normalize_inputs(
        {
            **((resolved_config.get("inputs") or {}).get("payload") or {}),
            **adapter_inputs,
            **previous_inputs,
            **_runtime_message_inputs(message),
        }
    )
    llm_mode = str((resolved_config.get("llm") or {}).get("mode") or "ollama")
    llm = get_llm_client("fake" if llm_mode in {"fake", "mock"} else None)
    return resolved_config, runtime_inputs, llm, {"previous": previous, "input_source": input_source, "llm_mode": llm_mode}


def run_runtime_step(step_id: str, *, context: Any | None = None) -> dict[str, Any]:
    """Execute one workflow stage in the runner declared by the manifest."""

    resolved_config, runtime_inputs, llm, stage = (
        _resolve_runtime_stage_request()
        if context is None
        else _resolve_runtime_stage_request(context)
    )
    previous = stage["previous"]
    run_id = (
        getattr(context, "run_id", None)
        or os.environ.get("MN_JOB_ID")
        or os.environ.get("MN_RUN_ID")
        or f"research-stage-{_sha256(json.dumps(runtime_inputs, sort_keys=True))[:12]}"
    )
    root = _script_blueprint_root()

    if step_id == "frame_research_goal":
        goal = create_research_goal(
            runtime_inputs.get("research_goal") or "Investigate the supplied research question",
            question=runtime_inputs.get("research_question") or "",
            success_criteria=list(runtime_inputs.get("success_criteria") or []),
            constraints=runtime_inputs.get("constraints") or {},
        )
        payload = {
            "inputs": runtime_inputs,
            "deterministic_stage": "goal_framing",
            "goal": goal,
            "checks": {
                "goal_present": bool(runtime_inputs.get("research_goal")),
                "constraints_normalized": isinstance(runtime_inputs.get("constraints"), dict),
                "public_query_privacy_checked": True,
            },
        }
    elif step_id == "retrieve_and_evaluate_evidence":
        prepared = prepare_evidence_context(
            resolved_config,
            runtime_inputs,
            root,
            run_id,
            quick_test=stage["llm_mode"] in {"fake", "mock"} or bool((resolved_config.get("execution") or {}).get("quick_test")),
        )
        payload = {
            **previous,
            "inputs": runtime_inputs,
            "deterministic_stage": "evidence_preparation",
            "documents": prepared["documents"],
            "rag": prepared["rag"],
            "sources": prepared["sources"],
            "evidence": prepared["evidence"],
            "posture": deterministic_research_posture(prepared["evidence"]),
            "warnings": prepared["warnings"],
        }
    elif step_id == "autonomous_research":
        documents = previous.get("documents") if isinstance(previous.get("documents"), list) else []
        sources = previous.get("sources") if isinstance(previous.get("sources"), list) else []
        rag = previous.get("rag") if isinstance(previous.get("rag"), dict) else {}
        evidence = previous.get("evidence") if isinstance(previous.get("evidence"), dict) else research_evidence(runtime_inputs, documents, sources)
        posture = previous.get("posture") if isinstance(previous.get("posture"), dict) else deterministic_research_posture(evidence)
        recommendation, autonomous, autonomous_warnings = run_autonomous_research(
            llm,
            runtime_inputs,
            evidence,
            rag,
            posture,
            resolved_config,
            documents,
            sources,
            workspace=Path(os.environ.get("MN_WORKDIR") or "/sandbox/job/document_workflow"),
        )
        verified_evidence = research_evidence(runtime_inputs, documents, sources)
        actor_state: dict[str, Any] = {}
        actor_findings = run_actor_reviews(
            config=resolved_config,
            llm=llm,
            actor_ids=list(resolve_actor_specs(resolved_config).keys()),
            state=actor_state,
            task=load_prompt("research-review-task.md"),
            context={"inputs": runtime_inputs, "evidence": verified_evidence, "recommendation": recommendation, "rag": rag, "sources": sources},
        )
        payload = {
            **previous,
            "inputs": runtime_inputs,
            "autonomous_stage": "completed_in_openshell",
            "sources": sources,
            "evidence": verified_evidence,
            "posture": deterministic_research_posture(verified_evidence),
            "recommendation": recommendation,
            "autonomous": autonomous,
            "actor_findings": actor_findings,
            "warnings": [*(previous.get("warnings") or []), *autonomous_warnings],
            "llm_usage": llm_usage(llm),
        }
    elif step_id == "verify_and_publish_packet":
        required = ("evidence", "recommendation", "autonomous")
        missing = [key for key in required if not isinstance(previous.get(key), dict)]
        if missing:
            raise ValueError(f"autonomous worker output is missing required records: {', '.join(missing)}")
        autonomous = previous["autonomous"]
        session = autonomous.get("session") if isinstance(autonomous.get("session"), dict) else {}
        if autonomous.get("isolation_required") is not True or not session.get("trace"):
            raise ValueError("autonomous output lacks the required OpenShell isolation and trace contract")
        final = build_research_packet(
            runtime_inputs,
            previous["evidence"],
            previous["recommendation"],
            previous.get("rag") if isinstance(previous.get("rag"), dict) else {},
            previous.get("sources") if isinstance(previous.get("sources"), list) else [],
            previous.get("warnings") if isinstance(previous.get("warnings"), list) else [],
            previous.get("documents") if isinstance(previous.get("documents"), list) else [],
            previous.get("actor_findings") if isinstance(previous.get("actor_findings"), dict) else {},
            autonomous,
            run_id,
        )
        result = {
            "identity": {"blueprint_id": BLUEPRINT_ID, "name": BLUEPRINT_NAME, "run_id": run_id},
            "blueprint": BLUEPRINT_ID,
            "name": BLUEPRINT_NAME,
            "run": {"run_id": run_id, "status": "completed"},
            "inputs": runtime_inputs,
            "evidence": previous["evidence"],
            "autonomous_research": autonomous,
            "final_artifact": final,
            "llm": previous.get("llm_usage") or {},
        }
        output_files = write_research_outputs(final, result, resolved_config, runtime_inputs)
        if output_files:
            result["output_files"] = output_files
        return {
            "run_id": run_id,
            "status": "completed",
            "workflow_step_id": step_id,
            "deterministic_verification": research_artifact_quality(final),
            "final_artifact": final,
            "output_files": output_files,
        }
    else:
        raise ValueError(f"unknown Research Co-Scientist workflow step: {step_id}")

    return {
        "run_id": run_id,
        "status": "completed",
        "workflow_step_id": step_id,
        "workflow_payload": payload,
    }


def main(argv: list[str] | None = None) -> None:
    step_id = os.environ.get("MN_WORKFLOW_STEP_ID", "").strip()
    if step_id:
        print(json.dumps(run_runtime_step(step_id), indent=2, sort_keys=True, default=str))
        return
    run_blueprint_cli(run_blueprint, argv, description="Run the Research Co-Scientist.", default_blueprint_id=BLUEPRINT_ID)


if __name__ == "__main__":
    main()
