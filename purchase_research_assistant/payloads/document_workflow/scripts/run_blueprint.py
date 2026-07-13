#!/usr/bin/env python3.11
"""Run the general purchase research workflow.

The runner deliberately keeps deterministic extraction and policy checks in
Python. LLMs may summarize and recommend among bounded labels, but they do
not author source facts or perform purchase transactions.
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
    get_actor_llm_client,
    llm_usage,
    load_config,
    resolve_actor_specs,
    resolve_input_overrides,
    run_actor_reviews,
    run_blueprint_cli,
    utc_now_iso,
)
from mn_blueprint_support.web_ui import maybe_write_static_output  # noqa: E402

try:  # Optional in local fake/quick-test environments.
    from mn_rag_skill import build_rag_context, prepare_blueprint_knowledge_rag
except Exception:  # pragma: no cover - depends on the runtime skill image
    build_rag_context = None
    prepare_blueprint_knowledge_rag = None

try:  # Optional OCR dependency; text-like inputs never require it.
    from mn_llm_ocr_skill import extract_document
except Exception:  # pragma: no cover - depends on the runtime skill image
    extract_document = None


BLUEPRINT_ID = "purchase_research_assistant"
BLUEPRINT_NAME = "Purchase Research Assistant"
CATEGORY = "Finance"
OUTPUT_TYPE = "purchase_research_report"
DEFAULT_OUTPUT_FOLDER = "~/Downloads/purchase_research_assistant"
SUPPORTED_SUFFIXES = {".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp", ".txt", ".md", ".json", ".csv"}
TEXT_SUFFIXES = {".txt", ".md", ".json", ".csv"}
PURCHASE_TYPES = {"property", "rental_property", "car", "airline_ticket", "custom"}
RECOMMENDATIONS = {"buy", "consider", "wait", "avoid", "insufficient_evidence"}
BLOCKED_ACTIONS = [
    "buy_or_book",
    "pay_or_transfer_funds",
    "submit_application_or_offer",
    "contact_seller_provider_or_broker",
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
    purchase_type = str(payload.get("purchase_type") or payload.get("category") or "custom").strip().lower()
    aliases = {"vehicle": "car", "automobile": "car", "flight": "airline_ticket", "ticket": "airline_ticket", "rental": "rental_property"}
    payload["purchase_type"] = aliases.get(purchase_type, purchase_type if purchase_type in PURCHASE_TYPES else "custom")
    payload["item_description"] = str(payload.get("item_description") or payload.get("query") or "").strip()
    payload["budget"] = payload.get("budget", payload.get("price_ceiling"))
    payload["location"] = str(payload.get("location") or "").strip()
    payload["route"] = str(payload.get("route") or "").strip()
    payload["travel_dates"] = payload.get("travel_dates") or payload.get("dates") or ""
    payload["priorities"] = _as_list(payload.get("priorities"))
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


def load_purchase_knowledge(root: Path) -> dict[str, Any]:
    files = []
    combined: list[str] = []
    for path in sorted((root / "knowledge").rglob("*")) if (root / "knowledge").exists() else []:
        if path.is_file() and path.suffix.lower() in {".md", ".txt", ".json", ".csv"}:
            text = path.read_text(encoding="utf-8", errors="replace")
            files.append({"path": str(path), "name": path.name, "sha256": _sha256(text), "chars": len(text)})
            combined.append(f"\n## {path.name}\n{text}")
    content = "".join(combined)
    return {
        "id": "purchase_research_playbook",
        "title": "Purchase Research Evidence And Review Playbook",
        "files": files,
        "content": content[:40000],
        "sha256": _sha256(content),
        "grounding_rule": "Use retrieved guidance as a checklist; facts must come from user documents or cited public sources.",
    }


def prepare_purchase_rag(config: dict[str, Any], root: Path, knowledge: dict[str, Any], documents: list[dict[str, Any]], run_id: str | None = None) -> dict[str, Any]:
    raw = config.get("knowledge_rag") if isinstance(config.get("knowledge_rag"), dict) else {}
    state: dict[str, Any] = {
        "enabled": bool(raw.get("enabled", True)),
        "status": "disabled" if raw.get("enabled") is False else "local_ready",
        "config": raw,
        "namespace": f"{raw.get('namespace') or 'purchase_research'}:{run_id or 'local'}",
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


def retrieve_purchase_rag_context(query: str, rag_state: dict[str, Any], knowledge: dict[str, Any], documents: list[dict[str, Any]], *, max_chars: int = 6000) -> dict[str, Any]:
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


def build_public_queries(inputs: dict[str, Any], intake_plan: dict[str, Any] | None = None) -> list[str]:
    intake_plan = intake_plan if isinstance(intake_plan, dict) else {}
    constraint_parts = []
    for key, value in (inputs.get("constraints") or {}).items():
        safe_value = sanitize_public_text(value)
        safe_key = sanitize_public_text(key)
        if safe_key and safe_value:
            constraint_parts.append(f"{safe_key} {safe_value}")
    priority_parts = [sanitize_public_text(item) for item in inputs.get("priorities") or []]
    plan_topics = [sanitize_public_text(item) for item in intake_plan.get("public_query_topics") or []]
    base = " ".join(
        part for part in [
            inputs.get("purchase_type"),
            sanitize_public_text(inputs.get("item_description", "")),
            sanitize_public_text(inputs.get("location", "")),
            sanitize_public_text(inputs.get("route", "")),
            sanitize_public_text(inputs.get("travel_dates", "")),
            *priority_parts,
            *constraint_parts,
        ] if part
    ).strip()
    if not base:
        return []
    generic_topics = [
        "current price availability and comparable alternatives",
        "full total cost taxes fees recurring usage maintenance delivery and exit costs",
        "quality reliability safety compatibility warranty returns and support",
        "seller provider reputation policy eligibility privacy security and regulatory risks",
        "timing logistics constraints and what to verify before purchase",
    ]
    topics = {
        "property": ["market price taxes insurance inspection risks", "comparable listings fees ownership costs"],
        "rental_property": ["rent yield operating costs insurance tenant risks", "lease terms deposits maintenance fees"],
        "car": ["market price reliability ownership cost warranty recalls", "taxes registration insurance maintenance fees"],
        "airline_ticket": ["fare rules baggage seat fees cancellation change policy", "airport taxes schedule reliability alternatives"],
        "custom": ["category-specific price availability and alternatives", "category-specific quality policy compatibility and risks"],
    }
    selected_topics = list(dict.fromkeys([*plan_topics, *generic_topics, *topics.get(inputs.get("purchase_type"), topics["custom"])]))
    return [f"{base} {topic}" for topic in selected_topics if topic][:8]


def sanitize_public_text(value: Any) -> str:
    text = str(value or "")
    blocked = (
        "raw_document_text",
        "private_financial",
        "private financial",
        "account number",
        "account_number",
        "password",
        "ssn",
        "confidential",
        "contact details",
        "customer name",
        "email",
        "phone",
    )
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


def deterministic_evidence(inputs: dict[str, Any], documents: list[dict[str, Any]], sources: list[dict[str, Any]]) -> dict[str, Any]:
    text = "\n".join(str(item.get("text") or "") for item in documents)
    lowered = text.lower()
    price_values = [float(value.replace(",", "")) for value in re.findall(r"(?:\$|usd\s*)(\d[\d,]*(?:\.\d{1,2})?)", text, flags=re.I)]
    budget = _number(inputs.get("budget"))
    flags: list[str] = []
    checks = {
        "return_or_cancellation_policy": any(term in lowered for term in ("return", "cancel", "refund")),
        "warranty_or_insurance": any(term in lowered for term in ("warranty", "insurance", "coverage")),
        "fees_and_taxes": any(term in lowered for term in ("fee", "tax", "surcharge", "hoa", "baggage")),
        "condition_or_inspection": any(term in lowered for term in ("inspection", "condition", "recall", "maintenance")),
    }
    for name, present in checks.items():
        if not present:
            flags.append(f"Missing evidence for {name.replace('_', ' ')}.")
    if budget is not None and price_values and min(price_values) > budget:
        flags.append("Observed price evidence exceeds the stated budget.")
    if any(item.get("status") == "blocked" for item in sources):
        flags.append("One or more public sources were blocked or access-limited.")
    source_refs = [item.get("source_ref") for item in documents + sources if item.get("source_ref")]
    return {
        "purchase_type": inputs.get("purchase_type"),
        "budget": budget,
        "observed_price_values": price_values[:20],
        "deterministic_checks": checks,
        "risk_flags": flags,
        "evidence_gaps": [name for name, present in checks.items() if not present],
        "document_count": len(documents),
        "public_source_count": len([item for item in sources if item.get("status") == "observed"]),
        "source_refs": source_refs,
    }


def _number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(re.sub(r"[^0-9.-]", "", str(value)))
    except ValueError:
        return None


def deterministic_recommendation(evidence: dict[str, Any], sources: list[dict[str, Any]]) -> dict[str, Any]:
    gaps = len(evidence.get("evidence_gaps") or [])
    flags = len(evidence.get("risk_flags") or [])
    if not evidence.get("document_count") and not evidence.get("public_source_count"):
        label = "insufficient_evidence"
    elif flags >= 3 or gaps >= 3:
        label = "wait"
    elif flags >= 1 or gaps >= 1:
        label = "consider"
    else:
        label = "buy"
    confidence = "low" if gaps >= 3 else "medium" if gaps else "high"
    return {
        "label": label,
        "confidence": confidence,
        "rationale": "Recommendation is constrained by deterministic evidence checks and may change when missing evidence is supplied.",
        "risk_flags": list(evidence.get("risk_flags") or []),
        "evidence_gaps": list(evidence.get("evidence_gaps") or []),
        "public_source_status_counts": _status_counts(sources),
    }


def _normalize_intake_plan(response: Any, inputs: dict[str, Any]) -> dict[str, Any]:
    fallback = {
        "normalized_goal": str(inputs.get("item_description") or "Study the requested purchase."),
        "category": str(inputs.get("purchase_type") or "custom"),
        "must_haves": list(inputs.get("priorities") or []),
        "deal_breakers": [],
        "decision_criteria": [
            "fit to the stated need",
            "total cost over the decision horizon",
            "quality, reliability, and safety",
            "terms, policy, and provider risk",
            "credible alternatives",
        ],
        "research_questions": [
            "What facts could materially change the decision?",
            "What is the total cost beyond the advertised price?",
            "What evidence is needed to verify quality, terms, and risk?",
        ],
        "public_query_topics": [],
        "unknowns": [],
    }
    if not isinstance(response, dict):
        return fallback
    normalized = dict(fallback)
    for key in ("normalized_goal", "category"):
        value = str(response.get(key) or "").strip()
        if value:
            normalized[key] = value[:500]
    for key in ("must_haves", "deal_breakers", "decision_criteria", "research_questions", "public_query_topics", "unknowns"):
        values = response.get(key)
        if isinstance(values, str):
            values = [values]
        if isinstance(values, (list, tuple, set)):
            cleaned = [str(item).strip()[:400] for item in values if str(item).strip()]
            normalized[key] = list(dict.fromkeys(cleaned))[:12]
    return normalized


def ask_llm_for_intake(llm: Any, inputs: dict[str, Any], documents: list[dict[str, Any]], knowledge: dict[str, Any]) -> dict[str, Any]:
    """Use the research model before retrieval so early workflow stages are model-guided."""
    fallback = _normalize_intake_plan({}, inputs)
    local_evidence = [
        {"source_ref": item.get("source_ref"), "name": item.get("name"), "text": _compact(item.get("text") or "", 2500)}
        for item in documents[:8]
    ]
    user = json.dumps(
        {
            "inputs": inputs,
            "local_evidence": local_evidence,
            "available_guidance": [item.get("name") for item in knowledge.get("files") or []],
            "output_contract": list(fallback.keys()),
        },
        sort_keys=True,
        default=str,
    )
    try:
        response = llm.generate_json(
            system_prompt=load_prompt("purchase-intake-task.md"),
            user_prompt=user,
            fallback=fallback,
        )
    except Exception:
        response = fallback
    return _normalize_intake_plan(response, inputs)


def _status_counts(records: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in records:
        status = str(item.get("status") or "unknown")
        counts[status] = counts.get(status, 0) + 1
    return counts


def ask_llm_for_recommendation(llm: Any, inputs: dict[str, Any], evidence: dict[str, Any], rag: dict[str, Any], deterministic: dict[str, Any]) -> dict[str, Any]:
    fallback = {"label": deterministic["label"], "confidence": deterministic["confidence"], "rationale": deterministic["rationale"]}
    prompt = load_prompt("purchase-review-task.md")
    system = load_prompt("recommendation-system.md")
    user = json.dumps({"inputs": inputs, "evidence": evidence, "rag_context": rag.get("context", ""), "deterministic_recommendation": deterministic}, sort_keys=True, default=str)
    try:
        response = llm.generate_json(system_prompt=system, user_prompt=f"{prompt}\n\n{user}", fallback=fallback)
    except Exception:
        response = fallback
    if not isinstance(response, dict):
        return fallback
    label = str(response.get("label") or response.get("recommendation") or fallback["label"]).lower()
    if label not in RECOMMENDATIONS:
        label = fallback["label"]
    confidence = str(response.get("confidence") or fallback["confidence"]).lower()
    if confidence not in {"low", "medium", "high"}:
        confidence = fallback["confidence"]
    return {"label": label, "confidence": confidence, "rationale": str(response.get("rationale") or fallback["rationale"])[:2000]}


def build_final_artifact(inputs: dict[str, Any], evidence: dict[str, Any], recommendation: dict[str, Any], rag: dict[str, Any], sources: list[dict[str, Any]], warnings: list[dict[str, Any]], documents: list[dict[str, Any]], actor_findings: dict[str, Any], run_id: str, intake_plan: dict[str, Any] | None = None) -> dict[str, Any]:
    source_refs = list(dict.fromkeys(["inputs.json", "events.jsonl", "result.json", *(evidence.get("source_refs") or []), *(rag.get("citations") or []), *(item.get("source_ref") for item in sources if item.get("source_ref"))]))
    return {
        "type": OUTPUT_TYPE,
        "schema_version": "mn.blueprint.purchase_research.v1",
        "blueprint_id": BLUEPRINT_ID,
        "run_id": run_id,
        "status": "review_ready",
        "purchase_type": inputs.get("purchase_type"),
        "item_description": inputs.get("item_description"),
        "executive_summary": f"Research packet for {inputs.get('purchase_type')} purchase: {inputs.get('item_description') or 'unspecified item'}. Recommendation: {recommendation.get('label')} with {recommendation.get('confidence')} confidence.",
        "recommended_action": recommendation.get("label"),
        "confidence": recommendation.get("confidence"),
        "recommendation_rationale": recommendation.get("rationale"),
        "intake_plan": intake_plan or {},
        "evidence": {"deterministic": evidence, "documents": [{key: value for key, value in item.items() if key != "text"} for item in documents], "public_sources": sources},
        "risk_flags": recommendation.get("risk_flags") or [],
        "evidence_gaps": recommendation.get("evidence_gaps") or [],
        "knowledge_rag": {key: value for key, value in rag.items() if key not in {"_rag_config"}},
        "actor_findings": actor_findings,
        "warnings": warnings,
        "next_steps": ["Review the cited evidence and fill the listed evidence gaps.", "Verify volatile price, availability, policy, and fee facts immediately before acting."],
        "source_refs": source_refs,
        "review_boundary": {"review_required": True, "blocked_actions": BLOCKED_ACTIONS, "reason": "The assistant provides decision support only and does not perform purchase or booking actions."},
    }


def write_user_outputs(final_artifact: dict[str, Any], result: dict[str, Any], config: dict[str, Any], inputs: dict[str, Any]) -> list[dict[str, str]]:
    output_dir = resolve_output_folder(config, inputs)
    if output_dir is None:
        return []
    output_dir.mkdir(parents=True, exist_ok=True)
    quality = build_artifact_quality(final_artifact)
    health = {"schema_version": "mn.blueprint.run_health.v1", "status": "completed_with_warnings" if final_artifact.get("warnings") else "completed", "warning_count": len(final_artifact.get("warnings") or []), "llm": result.get("llm", {})}
    ledger = [
        {"step": "purchase_intake", "status": "completed", "purchase_type": final_artifact.get("purchase_type")},
        {"step": "evidence_and_rag_review", "status": "completed", "source_refs": final_artifact.get("source_refs", [])},
        {"step": "public_research", "status": "completed", "source_count": len((final_artifact.get("evidence") or {}).get("public_sources") or [])},
        {"step": "recommendation", "status": "completed", "label": final_artifact.get("recommended_action"), "confidence": final_artifact.get("confidence")},
        {"step": "human_review_gate", "status": "blocked_pending_review", "blocked_actions": BLOCKED_ACTIONS},
    ]
    final_artifact["artifact_quality"] = quality
    final_artifact["run_health"] = health
    final_artifact["action_ledger"] = ledger
    evidence = final_artifact.get("evidence") or {}
    paths = {
        "purchase_research_json": output_dir / "purchase_research.json",
        "report_markdown": output_dir / "purchase_research_report.md",
        "evidence_json": output_dir / "evidence.json",
        "research_sources_json": output_dir / "research_sources.json",
        "knowledge_rag_json": output_dir / "knowledge_rag.json",
        "action_ledger_json": output_dir / "action_ledger.json",
        "artifact_quality_json": output_dir / "artifact_quality.json",
        "run_health_json": output_dir / "run_health.json",
    }
    output_files = [{"kind": kind, "path": str(path)} for kind, path in paths.items()]
    final_artifact["output_files"] = output_files
    paths["purchase_research_json"].write_text(json.dumps(final_artifact, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    paths["report_markdown"].write_text(render_markdown(final_artifact), encoding="utf-8")
    paths["evidence_json"].write_text(json.dumps(evidence, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    paths["research_sources_json"].write_text(json.dumps(evidence.get("public_sources") or [], indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    paths["knowledge_rag_json"].write_text(json.dumps(final_artifact.get("knowledge_rag") or {}, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    paths["action_ledger_json"].write_text(json.dumps(ledger, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    paths["artifact_quality_json"].write_text(json.dumps(quality, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    paths["run_health_json"].write_text(json.dumps(health, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    return output_files


def resolve_output_folder(config: dict[str, Any], inputs: dict[str, Any]) -> Path | None:
    runtime_output_folder = os.environ.get("MN_JOB_OUTPUT_DIR")
    if runtime_output_folder:
        return expand_runtime_path(runtime_output_folder)
    value = inputs.get("output_folder") or (config.get("outputs") or {}).get("folder_path") or DEFAULT_OUTPUT_FOLDER
    value = str(value).strip()
    if not value:
        return None
    return expand_runtime_path(value)


def build_artifact_quality(final_artifact: dict[str, Any]) -> dict[str, Any]:
    checks = [
        {"name": "recommendation_label_valid", "passed": final_artifact.get("recommended_action") in RECOMMENDATIONS},
        {"name": "source_refs_present", "passed": bool(final_artifact.get("source_refs"))},
        {"name": "review_boundary_present", "passed": bool(final_artifact.get("review_boundary"))},
        {"name": "evidence_gaps_explicit", "passed": isinstance(final_artifact.get("evidence_gaps"), list)},
    ]
    passed = all(item["passed"] for item in checks)
    return {"schema_version": "mn.blueprint.artifact_quality.v1", "status": "usable_with_review" if passed else "usable_with_review_warnings", "review_required": True, "quality_checks": checks, "warnings": final_artifact.get("warnings") or []}


def render_markdown(artifact: dict[str, Any]) -> str:
    evidence = artifact.get("evidence") or {}
    intake_plan = artifact.get("intake_plan") or {}
    lines = [
        "# Purchase Research Report",
        "",
        f"**Purchase type:** {artifact.get('purchase_type')}",
        f"**Item or trip:** {artifact.get('item_description') or 'Not specified'}",
        f"**Recommendation:** {artifact.get('recommended_action')}",
        f"**Confidence:** {artifact.get('confidence')}",
        "",
        "## Executive Summary",
        str(artifact.get("executive_summary") or ""),
        "",
        "## Rationale",
        str(artifact.get("recommendation_rationale") or ""),
        "",
        "## Purchase Decision Frame",
        f"- Goal: {intake_plan.get('normalized_goal') or 'Not specified'}",
        f"- Criteria: {', '.join(intake_plan.get('decision_criteria') or []) or 'Not specified'}",
        f"- Unknowns: {', '.join(intake_plan.get('unknowns') or []) or 'None recorded.'}",
        "",
        "## Deterministic Evidence",
        f"- Documents reviewed: {evidence.get('deterministic', {}).get('document_count', 0)}",
        f"- Public sources observed: {evidence.get('deterministic', {}).get('public_source_count', 0)}",
        f"- Observed prices: {evidence.get('deterministic', {}).get('observed_price_values') or 'Unknown'}",
        "",
        "## Risk Flags",
    ]
    lines.extend(f"- {item}" for item in artifact.get("risk_flags") or ["None recorded by deterministic checks."])
    lines.extend(["", "## Evidence Gaps"])
    lines.extend(f"- {item}" for item in artifact.get("evidence_gaps") or ["None recorded."])
    lines.extend(["", "## Sources"])
    lines.extend(f"- `{item}`" for item in artifact.get("source_refs") or ["No source references recorded."])
    lines.extend(["", "## Next Steps"])
    lines.extend(f"- {item}" for item in artifact.get("next_steps") or [])
    lines.extend(["", "## Review Boundary"])
    lines.extend(f"- Do not: {item}" for item in (artifact.get("review_boundary") or {}).get("blocked_actions") or BLOCKED_ACTIONS)
    lines.append("")
    return "\n".join(lines)


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
    llm_config = resolved_config.get("llm") if isinstance(resolved_config.get("llm"), dict) else {}
    llm_mode = str(llm_config.get("mode") or "live").lower()
    llm = get_actor_llm_client(resolved_config, llm_client)
    context = create_runtime_context(BLUEPRINT_ID, resolved_config, runtime_inputs, input_source)
    context.start()
    try:
        folder = resolve_input_folder(resolved_config, runtime_inputs, root)
        documents, document_warnings = load_input_documents(folder, resolved_config)
        knowledge = load_purchase_knowledge(root)
        intake_plan = ask_llm_for_intake(llm, runtime_inputs, documents, knowledge)
        context.event(
            "purchase_intake_completed",
            {
                "category": intake_plan.get("category"),
                "criteria_count": len(intake_plan.get("decision_criteria") or []),
                "research_question_count": len(intake_plan.get("research_questions") or []),
                "unknown_count": len(intake_plan.get("unknowns") or []),
            },
        )
        rag = prepare_purchase_rag(resolved_config, root, knowledge, documents, context.run_id)
        research_queries = build_public_queries(runtime_inputs, intake_plan)
        rag_query = " ".join(research_queries)
        local_retrieval = retrieve_purchase_rag_context(rag_query, rag, knowledge, documents, max_chars=int((resolved_config.get("knowledge_rag") or {}).get("max_context_chars", 6000)))
        rag["context"] = local_retrieval["context"]
        rag["citations"] = local_retrieval["citations"]
        rag["chunks"] = local_retrieval["chunks"]
        if local_retrieval.get("warning"):
            rag.setdefault("warnings", []).append(local_retrieval["warning"])
        rag.pop("_rag_config", None)
        context.event("inputs_loaded", {"purchase_type": runtime_inputs["purchase_type"], "document_count": len(documents), "input_folder": str(folder) if folder else None})
        context.event("knowledge_rag_prepared", {"status": rag.get("status"), "citations": rag.get("citations", []), "user_documents_indexed": len(rag.get("user_documents_indexed") or [])})
        sources, web_warnings = research_public_sources(research_queries, resolved_config, quick_test=llm_mode in {"fake", "mock"} or bool((resolved_config.get("execution") or {}).get("quick_test")))
        context.event("public_research_completed", {"source_count": len(sources), "warning_count": len(web_warnings)})
        evidence = deterministic_evidence(runtime_inputs, documents, sources)
        deterministic = deterministic_recommendation(evidence, sources)
        recommendation = ask_llm_for_recommendation(llm, runtime_inputs, evidence, rag, deterministic)
        actor_state: dict[str, Any] = {}
        actor_findings = run_actor_reviews(
            config=resolved_config,
            llm=llm,
            actor_ids=list(resolve_actor_specs(resolved_config).keys()),
            state=actor_state,
            task=load_prompt("purchase-review-task.md"),
            context={"inputs": runtime_inputs, "intake_plan": intake_plan, "evidence": evidence, "recommendation": recommendation, "rag": rag, "sources": sources},
            event_sink=context,
        )
        warnings = [*document_warnings, *rag.get("warnings", []), *web_warnings]
        final = build_final_artifact(runtime_inputs, evidence, recommendation, rag, sources, warnings, documents, actor_findings, context.run_id, intake_plan=intake_plan)
        result = {
            "identity": {"blueprint_id": BLUEPRINT_ID, "name": BLUEPRINT_NAME, "run_id": context.run_id},
            "blueprint": BLUEPRINT_ID,
            "name": BLUEPRINT_NAME,
            "category": CATEGORY,
            "description": "A source-grounded co-worker for researching and comparing purchases across property, vehicles, travel, rentals, and custom categories.",
            "run": {"run_id": context.run_id, "run_dir": str(context.run_dir) if context.run_dir else None, "status": "completed"},
            "architecture": architecture_contract(resolved_config, input_source),
            "config": resolved_config,
            "inputs": runtime_inputs,
            "intake_plan": intake_plan,
            "input_source": input_source,
            "runtime_features": ["local and user-document RAG", "privacy-safe public web research", "bounded specialist reviews", "deterministic evidence checks", "human review gate"],
            "knowledge_rag": rag,
            "research_sources": sources,
            "evidence": evidence,
            "recommendation": recommendation,
            "final_artifact": final,
            "artifacts": [{"artifact_id": "final_artifact", "type": "final_artifact", "path": "final_artifact.json", "schema_version": "mn.blueprint.final_artifact.v1", "source_refs": ["inputs.json", "events.jsonl", "result.json"]}],
            "llm": llm_usage(llm),
        }
        final["llm_usage"] = result["llm"]
        output_files = write_user_outputs(final, result, resolved_config, runtime_inputs)
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


def main(argv: list[str] | None = None) -> None:
    run_blueprint_cli(run_blueprint, argv, description="Run the Purchase Research Assistant.", default_blueprint_id=BLUEPRINT_ID)


if __name__ == "__main__":
    main()
