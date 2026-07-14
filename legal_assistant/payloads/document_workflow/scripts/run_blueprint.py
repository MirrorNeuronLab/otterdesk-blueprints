#!/usr/bin/env python3.11
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


RUNTIME_SKILL_PACKAGES = (
    "mirrorneuron-blueprint-support-skill",
    "mirrorneuron-litellm-communicate-skill",
    "mirrorneuron-llm-ocr-skill",
    "mirrorneuron-rag-skill",
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

from mn_blueprint_support import (
    DeterministicFallbackLLM,
    PromptLibrary,
    append_event_jsonl,
    fake_llm_mode_enabled,
    get_actor_llm_client,
    load_resolved_config as load_shared_resolved_config,
    select_default_model,
    start_agent_beacon_thread,
)

try:
    from mn_llm_ocr_skill import docker_ocr_client_factory_from_config, extract_document
except Exception:  # pragma: no cover - optional runtime dependency
    docker_ocr_client_factory_from_config = None
    extract_document = None

try:
    from mn_rag_skill import build_rag_context, prepare_blueprint_knowledge_rag
except Exception:  # pragma: no cover - optional runtime dependency
    build_rag_context = None
    prepare_blueprint_knowledge_rag = None


BLUEPRINT_ID = "legal_assistant"
BLUEPRINT_NAME = "Legal Assistant"
OUTPUT_TYPE = "legal_assistant_report"
RECOMMENDED_ACTION = "attorney_and_human_review_required_before_legal_payment_or_contract_action"
OCR_SUFFIXES = {".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}
SUPPORTED_SUFFIXES = OCR_SUFFIXES | {".txt", ".json", ".csv", ".md"}
TEXT_SUFFIXES = {".txt", ".json", ".csv", ".md"}
OCR_MIN_TEXT_CHARS = 40
INVOICE_FIELDS = [
    "supplier_name",
    "customer_name",
    "invoice_id",
    "tax_id",
    "due_date",
    "total_amount",
    "line_items",
    "consumption_fields",
    "billing_period",
]
CLAUSE_FIELDS = [
    "governing_law",
    "change_of_control",
    "assignment",
    "indemnity",
    "termination",
    "audit_rights",
    "renewal",
    "exclusivity",
    "liability",
]
WORKFLOW_STEPS = [
    "legal_folder_watcher",
    "legal_document_reader",
    "invoice_bill_extractor",
    "payable_field_validator",
    "contract_clause_extractor",
    "contract_playbook_comparator",
    "legal_evidence_reconciler",
    "legal_review_auditor",
    "legal_reporter",
]
HEAVY_MODEL_STEPS = {
    "contract_playbook_comparator",
    "legal_review_auditor",
    "legal_reporter",
}
DEFAULT_LLM_REVIEW_AGENTS = (
    "invoice_bill_extractor",
    "payable_field_validator",
    "contract_clause_extractor",
    "contract_playbook_comparator",
    "legal_evidence_reconciler",
    "legal_review_auditor",
    "legal_reporter",
)
DATASET_INPUTS = {
    "invoice_bill_extraction": {
        "name": "IDSEM Dataset",
        "provider": "University of Las Palmas de Gran Canaria on Zenodo",
        "url": "https://zenodo.org/records/6373179",
        "note": "Public electricity bill PDFs and JSON labels. Bundled samples are small local fixtures for smoke runs.",
    },
    "contract_clause_review": {
        "name": "Contract Understanding Atticus Dataset (CUAD) v1",
        "provider": "The Atticus Project",
        "url": "https://zenodo.org/records/4595826",
        "alternate_url": "https://huggingface.co/datasets/theatticusproject/cuad",
        "license": "CC BY 4.0",
        "note": "Public commercial contract corpus and clause labels. Bundled samples are small local fixtures for smoke runs.",
    },
    "real_public_contract_terms": {
        "name": "FAR 52.212-4 Contract Terms and Conditions—Commercial Products and Commercial Services",
        "provider": "U.S. General Services Administration, Acquisition.gov",
        "url": "https://www.acquisition.gov/far/52.212-4",
        "download_url": "https://www.acquisition.gov/node/31867/printable/pdf",
        "source_version": "FAC 2026-01; effective 2026-03-13",
        "license_note": "U.S. government regulatory text; verify current version before production use.",
    },
}
PROMPTS = PromptLibrary.from_script(__file__, parents_up=2)
REVIEW_PROMPT_FILES = {
    "legal_folder_watcher": "document-intake-review.md",
    "legal_document_reader": "document-intake-review.md",
    "invoice_bill_extractor": "invoice-bill-review.md",
    "payable_field_validator": "invoice-bill-review.md",
    "contract_clause_extractor": "contract-clause-review.md",
    "contract_playbook_comparator": "contract-clause-review.md",
    "legal_evidence_reconciler": "legal-evidence-reconciler.md",
    "legal_review_auditor": "legal-review-auditor.md",
    "legal_reporter": "legal-report-reporter.md",
}


def load_prompt(name: str) -> str:
    return PROMPTS.load(name)


def render_prompt(name: str, **values: str) -> str:
    return PROMPTS.render(name, **values)


def load_legal_knowledge(blueprint_root: Path) -> dict[str, Any]:
    playbook_path = blueprint_root / "knowledge" / "legal_playbook.md"
    content = playbook_path.read_text(encoding="utf-8") if playbook_path.exists() else ""
    return {
        "id": "legal_assistant_playbook",
        "title": "Legal Assistant Evidence And Review Playbook",
        "path": str(playbook_path),
        "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest() if content else "",
        "content": content[:12000],
        "judge_rubric": [
            "clause_or_field_accuracy",
            "evidence_traceability",
            "deterministic_output_invariance",
            "assumption_clarity",
            "missing_evidence_honesty",
            "privacy_and_privilege_handling",
            "review_only_language",
            "actionability_without_unauthorized_action",
        ],
        "grounding_rule": "Use the playbook as a review taxonomy and safety boundary, never as governing law or a substitute for qualified counsel.",
    }


LEGAL_RAG_QUERIES = {
    "legal_folder_watcher": "legal document intake source traceability privacy and supported evidence",
    "legal_document_reader": "OCR status document classification and source quality for legal review",
    "invoice_bill_extractor": "invoice fields payment terms totals source references and payable blockers",
    "payable_field_validator": "invoice validation missing fields arithmetic consistency and payment controls",
    "contract_clause_extractor": "contract clause taxonomy source snippets defined terms and cross references",
    "contract_playbook_comparator": "contract playbook comparison missing clauses indemnity termination liability assignment and review questions",
    "legal_evidence_reconciler": "legal evidence reconciliation contradictions source hierarchy issue ownership and confidence",
    "legal_review_auditor": "legal review audit privacy privilege deterministic invariance and blocked actions",
    "legal_reporter": "legal report quality evidence traceability bounded next steps and review-only language",
}
LEGAL_RAG_RUN_QUERY = (
    "legal invoice and contract review evidence hierarchy, clause taxonomy, playbook comparison, "
    "privacy and privilege, reconciliation, and human approval boundaries"
)


def prepare_legal_rag(config: dict[str, Any], blueprint_root: Path, knowledge: dict[str, Any]) -> dict[str, Any]:
    knowledge_config = config.get("knowledge_rag") if isinstance(config.get("knowledge_rag"), dict) else {}
    if prepare_blueprint_knowledge_rag is None:
        return {
            "enabled": bool(knowledge_config.get("enabled")),
            "status": "skill_unavailable",
            "warnings": ["mirrorneuron-rag-skill is unavailable; bundled playbook context remains available."],
            "config": knowledge_config,
        }
    try:
        return prepare_blueprint_knowledge_rag(
            blueprint_id=BLUEPRINT_ID,
            blueprint_dir=blueprint_root,
            config={"knowledge_rag": knowledge_config},
            active_knowledge=knowledge,
        )
    except Exception as exc:  # pragma: no cover - depends on local embedding runtime
        return {
            "enabled": bool(knowledge_config.get("enabled")),
            "status": "knowledge_rag_failed",
            "warnings": [{"kind": "knowledge_rag", "message": "RAG preparation failed; bundled playbook context remains available.", "error": str(exc)}],
            "config": knowledge_config,
        }


def legal_knowledge_context_for_actor(
    knowledge: dict[str, Any],
    rag_state: dict[str, Any],
    actor_id: str,
) -> dict[str, Any]:
    query = LEGAL_RAG_QUERIES.get(actor_id, "legal contract review evidence and human approval boundaries")
    base = {
        "id": knowledge.get("id"),
        "title": knowledge.get("title"),
        "path": knowledge.get("path"),
        "sha256": knowledge.get("sha256"),
        "judge_rubric": list(knowledge.get("judge_rubric") or []),
        "grounding_rule": knowledge.get("grounding_rule"),
        "rag_status": rag_state.get("status") or "not_started",
        "rag_warnings": list(rag_state.get("warnings") or []),
        "query": query,
        "context": "",
        "citations": [],
        "chunks": [],
    }
    rag_config = rag_state.get("_rag_config") if isinstance(rag_state, dict) else None
    if build_rag_context is not None and rag_state.get("status") == "ready" and rag_config is not None:
        try:
            retrieved = rag_state.get("_shared_retrieval")
            if not isinstance(retrieved, dict):
                retrieved = build_rag_context(
                    LEGAL_RAG_RUN_QUERY,
                    rag_config,
                    max_chars=int((rag_state.get("config") or {}).get("max_context_chars") or 4500),
                )
                rag_state["_shared_retrieval"] = retrieved
            if retrieved.get("error"):
                raise RuntimeError(str(retrieved["error"]))
            base.update(
                {
                    "context": retrieved.get("context") or "",
                    "citations": retrieved.get("citations") or [],
                    "chunks": retrieved.get("chunks") or [],
                    "backend": retrieved.get("backend"),
                    "embedding_model": retrieved.get("embedding_model"),
                }
            )
            return base
        except Exception as exc:  # pragma: no cover - depends on local embedding runtime
            rag_state["_shared_retrieval"] = {"error": str(exc)}
            base["rag_status"] = "knowledge_rag_failed"
            base.setdefault("rag_warnings", []).append({"kind": "knowledge_rag", "message": "Actor retrieval failed; bundled playbook context remains available.", "error": str(exc)})
    base["context"] = knowledge.get("content") or ""
    return base


class DeterministicLLM(DeterministicFallbackLLM):
    def __init__(self) -> None:
        super().__init__(
            "deterministic-legal-assistant",
            default_summary="Deterministic legal review completed from local evidence.",
            confidence=0.72,
        )


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    return value if isinstance(value, dict) else {}


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=False, default=str) + "\n", encoding="utf-8")


def write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def append_event(run_dir: Path, event_type: str, payload: dict[str, Any]) -> None:
    append_event_jsonl(run_dir, event_type, redact_value(payload))


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def redact_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): redact_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact_value(item) for item in value[:50]]
    if isinstance(value, str):
        text = re.sub(r"\b\d{3}[- ]?\d{2}[- ]?\d{4}\b", "[REDACTED-SSN]", value)
        text = re.sub(r"\b(?:\d[ -]*?){13,19}\b", "[REDACTED-CARD]", text)
        text = re.sub(r"\b\d{9,18}\b", "[REDACTED-ID]", text)
        text = re.sub(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "[REDACTED-EMAIL]", text)
        return text[:1200]
    return value


def _script_blueprint_root() -> Path:
    script_path = Path(__file__).resolve()
    if len(script_path.parents) > 3 and script_path.parents[2].name == "payloads":
        return script_path.parents[3]
    if len(script_path.parents) > 2:
        return script_path.parents[2]
    return script_path.parent


def default_config_path() -> Path:
    configured_path = os.environ.get("MN_BLUEPRINT_CONFIG_PATH")
    if configured_path:
        candidate = Path(configured_path).expanduser()
        if candidate.exists():
            return candidate

    bundle_dir = os.environ.get("MN_BLUEPRINT_BUNDLE_DIR")
    if bundle_dir:
        candidate = Path(bundle_dir).expanduser() / "config" / "default.json"
        if candidate.exists():
            return candidate

    script_path = Path(__file__).resolve()
    for parent in script_path.parents:
        candidate = parent / "config" / "default.json"
        if candidate.exists():
            return candidate
    return _script_blueprint_root() / "config" / "default.json"


def blueprint_dir() -> Path:
    return default_config_path().parents[1]


def load_resolved_config(config: dict[str, Any] | None = None, config_json: str | None = None) -> dict[str, Any]:
    resolved_default_path = default_config_path()
    if not resolved_default_path.exists():
        embedded_config = config_json or os.environ.get("MN_BLUEPRINT_CONFIG_JSON")
        if embedded_config:
            decoded = json.loads(embedded_config)
            if isinstance(decoded, dict):
                return deep_merge(decoded, config or {})
    return load_shared_resolved_config(
        resolved_default_path,
        overlay=config,
        config_json=config_json,
    )


def runtime_message_payload() -> dict[str, Any]:
    for env_name in ("MN_WORKFLOW_INPUT_JSON", "MN_INPUT_JSON", "MN_MESSAGE_JSON"):
        raw = os.environ.get(env_name)
        if not raw:
            continue
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            continue
        payload = find_payload(value)
        if payload:
            return payload
    return {}


def find_payload(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        interesting = {"document_folder", "input_folder", "output_folder", "field_profile", "matter_profile", "review_policy"}
        if interesting & set(value):
            return copy.deepcopy(value)
        for key in ("kwargs", "payload", "input", "body", "data", "message", "content"):
            found = find_payload(value.get(key))
            if found:
                return found
        for nested in value.values():
            found = find_payload(nested)
            if found:
                return found
    elif isinstance(value, list):
        for nested in value:
            found = find_payload(nested)
            if found:
                return found
    elif isinstance(value, str) and value.strip().startswith(("{", "[")):
        try:
            return find_payload(json.loads(value))
        except json.JSONDecodeError:
            return {}
    return {}


def resolve_inputs(config: dict[str, Any], inputs: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = copy.deepcopy(((config.get("inputs") or {}).get("payload") or {}))
    payload = deep_merge(payload, runtime_message_payload())
    payload = deep_merge(payload, inputs or {})
    if "document_folder" not in payload and payload.get("input_folder"):
        payload["document_folder"] = payload["input_folder"]
    if "input_folder" not in payload and payload.get("document_folder"):
        payload["input_folder"] = payload["document_folder"]
    return payload


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
    names = [
        os.environ.get("SUDO_USER"),
        os.environ.get("LOGNAME"),
        os.environ.get("USER"),
    ]
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


def resolve_output_folder(
    payload: dict[str, Any],
    resolved_config: dict[str, Any],
    inputs: dict[str, Any] | None = None,
) -> Path:
    runtime_output_folder = os.environ.get("MN_JOB_OUTPUT_DIR")
    if runtime_output_folder:
        return expand_runtime_path(runtime_output_folder)
    explicit_output_folder = (inputs or {}).get("output_folder")
    if explicit_output_folder:
        return expand_runtime_path(explicit_output_folder)
    outputs_config = resolved_config.get("outputs") if isinstance(resolved_config.get("outputs"), dict) else {}
    configured_output_folder = outputs_config.get("output_folder") or outputs_config.get("folder_path")
    configured_target = payload.get("output_folder") or configured_output_folder
    if configured_target:
        return expand_runtime_path(configured_target)
    return expand_runtime_path(f"outputs/{BLUEPRINT_ID}")


def resolve_run_dir(output_folder: Path, run_id: str, runs_root: str | Path | None = None) -> Path:
    if not runs_root:
        env_run_dir = os.environ.get("MN_RUN_DIR")
        if env_run_dir:
            return expand_runtime_path(env_run_dir)
    resolved_runs_root = runs_root or os.environ.get("MN_RUNS_ROOT")
    if resolved_runs_root:
        return expand_runtime_path(resolved_runs_root) / run_id
    return output_folder / "runs" / run_id


def expand_path(raw: Any, *, root: Path | None = None) -> Path:
    value = str(raw or "").strip() or "."
    path = expand_runtime_path(value)
    if not path.is_absolute() and root is not None:
        if path.parts and path.parts[0] == root.name:
            path = root.parent / path
        else:
            path = root / path
    return path.resolve()


def classify_document(text: str, filename: str) -> str:
    lower_name = filename.lower()
    if lower_name in {"readme.md", "sample_dataset_manifest.json"}:
        return "supporting_document"
    haystack = f"{filename}\n{text}".lower()
    invoice_score = sum(1 for token in ("invoice", "supplier", "vendor", "total", "amount due", "meter", "billing") if token in haystack)
    contract_score = sum(1 for token in ("agreement", "contract", "clause", "governing law", "indemn", "liability", "termination") if token in haystack)
    if invoice_score > contract_score and invoice_score:
        return "invoice_or_bill"
    if contract_score:
        return "contract_or_clause_source"
    if filename.lower().endswith(".json"):
        return "structured_json"
    return "supporting_document"


def fake_llm_requested(config: dict[str, Any], payload: dict[str, Any] | None = None) -> bool:
    if not payload or not payload.get("quick_test"):
        return fake_llm_mode_enabled(config)
    merged = copy.deepcopy(config)
    merged.setdefault("execution", {})["quick_test"] = True
    return fake_llm_mode_enabled(merged)


def _ocr_skill_config(config: dict[str, Any]) -> dict[str, Any]:
    input_skills = config.get("input_skills") if isinstance(config.get("input_skills"), dict) else {}
    return {"input_skills": input_skills}


def build_ocr_runtime(ctx: dict[str, Any]) -> tuple[Any | None, dict[str, Any]]:
    section = (ctx["config"].get("input_skills") or {}).get("llm_ocr")
    section = section if isinstance(section, dict) else {}
    install_policy = str(section.get("install_policy") or "on_first_required_document")
    status: dict[str, Any] = {
        "enabled": section.get("enabled", True) is not False,
        "skill_available": extract_document is not None and docker_ocr_client_factory_from_config is not None,
        "configured": False,
        "status": "not_needed",
        "install_policy": install_policy,
        "trigger": f"PDF/image with less than {OCR_MIN_TEXT_CHARS} embedded characters",
        "source_model": "lightonai/LightOnOCR-2-1B",
        "warnings": [],
    }
    if not status["enabled"]:
        status["status"] = "disabled"
        status["warnings"].append("llm_ocr_disabled_in_config")
        return None, status
    if fake_llm_requested(ctx["config"], ctx.get("payload")):
        status["status"] = "disabled_for_fake_or_quick_test"
        status["warnings"].append("llm_ocr_skipped_for_explicit_fake_or_quick_test")
        return None, status
    if not status["skill_available"]:
        status["status"] = "skill_unavailable"
        status["warnings"].append("mirrorneuron_llm_ocr_skill_unavailable")
        return None, status
    try:
        factory = docker_ocr_client_factory_from_config(_ocr_skill_config(ctx["config"]))
        if factory is None:
            status["status"] = "disabled_by_skill_config"
            status["warnings"].append("llm_ocr_factory_disabled")
            return None, status
        client = factory()
        model_config = getattr(client, "config", None)
        status.update(
            {
                "configured": True,
                "status": "ready_for_runtime_managed_first_use" if install_policy == "runtime" else "ready_for_lazy_first_use",
                "runtime_model": getattr(model_config, "model", None),
                "backend": getattr(model_config, "backend", None),
                "expected_accelerator": getattr(model_config, "expected_accelerator", None),
            }
        )
        return client, status
    except Exception as exc:  # pragma: no cover - depends on local OCR runtime
        status["status"] = "configuration_failed"
        status["warnings"].append(f"llm_ocr_configuration_failed:{exc}")
        return None, status


def _read_ocr_document(path: Path, ocr_client: Any | None) -> dict[str, Any]:
    record = extract_document(
        path,
        classifier=lambda text, filename: classify_document(text, filename),
        llm_ocr_client=ocr_client,
        min_text_chars=OCR_MIN_TEXT_CHARS,
    )
    payload = record.to_dict() if hasattr(record, "to_dict") else dict(record)
    text = str(payload.get("text") or "")
    return {
        "path": str(path),
        "filename": path.name,
        "document_type": str(payload.get("document_type") or classify_document(text, path.name)),
        "text": redact_value(text),
        "ocr_required": bool(payload.get("ocr_required")),
        "extraction_method": str(payload.get("extraction_method") or "ocr_skill"),
        "warnings": [str(item) for item in (payload.get("warnings") or [])],
        "metadata": {"size_bytes": path.stat().st_size, **(payload.get("metadata") or {})},
        "pages": payload.get("pages") or [],
    }


def read_document(path: Path, *, ocr_client: Any | None = None) -> dict[str, Any]:
    suffix = path.suffix.lower()
    if suffix in OCR_SUFFIXES and extract_document is not None:
        try:
            return _read_ocr_document(path, ocr_client)
        except Exception as exc:
            return {
                "path": str(path),
                "filename": path.name,
                "document_type": classify_document("", path.name),
                "text": "",
                "ocr_required": True,
                "extraction_method": "ocr_error",
                "warnings": [f"ocr_document_read_error:{exc}", "image_or_pdf_requires_ocr_review"],
                "metadata": {"size_bytes": path.stat().st_size},
                "pages": [],
            }
    if suffix in TEXT_SUFFIXES:
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
            return {
                "path": str(path),
                "filename": path.name,
                "document_type": classify_document(text, path.name),
                "text": redact_value(text),
                "ocr_required": False,
                "extraction_method": "embedded_text",
                "warnings": [],
                "metadata": {"size_bytes": path.stat().st_size},
                "pages": [],
            }
        except Exception as exc:
            return {
                "path": str(path),
                "filename": path.name,
                "document_type": "supporting_document",
                "text": "",
                "ocr_required": False,
                "extraction_method": "read_error",
                "warnings": [f"Could not read text: {exc}"],
                "metadata": {"size_bytes": path.stat().st_size},
                "pages": [],
            }
    return {
        "path": str(path),
        "filename": path.name,
        "document_type": classify_document("", path.name),
        "text": "",
        "ocr_required": suffix in OCR_SUFFIXES,
        "extraction_method": "unreadable_or_binary" if suffix in OCR_SUFFIXES else "unsupported",
        "warnings": (
            ["binary_or_scanned_document_requires_ocr_for_text", "mirrorneuron_llm_ocr_skill_unavailable"]
            if suffix in OCR_SUFFIXES
            else ["Unsupported file type skipped."]
        ),
        "metadata": {"size_bytes": path.stat().st_size},
        "pages": [],
    }


def load_documents(folder: Path, *, ocr_client: Any | None = None) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if not folder.exists():
        return records
    for path in sorted(folder.rglob("*")):
        if path.is_dir() or path.name.startswith("."):
            continue
        if path.suffix.lower() not in SUPPORTED_SUFFIXES:
            continue
        records.append(read_document(path, ocr_client=ocr_client))
    return records


def structured_values_from_text(text: str, *, limit: int = 20) -> list[dict[str, str]]:
    if not text or not text.lstrip().startswith(("{", "[")):
        return []
    try:
        decoded = json.loads(text)
    except Exception:
        return []
    values: list[dict[str, str]] = []

    def add(prefix: str, value: Any) -> None:
        if len(values) >= limit:
            return
        if isinstance(value, dict):
            for key, item in value.items():
                add(f"{prefix}.{key}" if prefix else str(key), item)
        elif isinstance(value, list):
            if value and all(not isinstance(item, (dict, list)) for item in value[:5]):
                values.append({"field": prefix, "value": ", ".join(str(item) for item in value[:5])[:200]})
            else:
                for index, item in enumerate(value[:4]):
                    add(f"{prefix}[{index}]", item)
        elif value not in (None, ""):
            values.append({"field": prefix, "value": str(value)[:200]})

    add("", decoded)
    return values[:limit]


def flatten_json(text: str) -> dict[str, Any]:
    if not text.lstrip().startswith(("{", "[")):
        return {}
    try:
        decoded = json.loads(text)
    except Exception:
        return {}
    flat: dict[str, Any] = {}

    def add(prefix: str, value: Any) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                add(f"{prefix}.{key}" if prefix else str(key), item)
        elif isinstance(value, list):
            flat[prefix] = value
            for index, item in enumerate(value[:4]):
                add(f"{prefix}[{index}]", item)
        else:
            flat[prefix] = value

    add("", decoded)
    return flat


def find_amount(text: str) -> float | None:
    patterns = [
        r"(?:total_amount|total amount|amount due|balance due|total)\s*[:=]?\s*\$?\s*([0-9,]+(?:\.[0-9]{2})?)",
        r"\$\s*([0-9,]+(?:\.[0-9]{2})?)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return float(match.group(1).replace(",", ""))
    return None


def extract_named_value(text: str, names: list[str]) -> str:
    for name in names:
        pattern = rf"{re.escape(name)}\s*[:=]\s*([^\n\r,;]+)"
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return ""


def invoice_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [record for record in records if record.get("document_type") == "invoice_or_bill"]


def contract_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [record for record in records if record.get("document_type") == "contract_or_clause_source"]


def extract_invoice_bill_packet(records: list[dict[str, Any]]) -> dict[str, Any]:
    invoices = []
    total_amount = 0.0
    for record in invoice_records(records):
        text = str(record.get("text") or "")
        flat = flatten_json(text)
        amount = flat.get("total_amount") or flat.get("invoice.total_amount") or find_amount(text)
        try:
            numeric_amount = float(str(amount).replace("$", "").replace(",", "")) if amount not in (None, "") else None
        except ValueError:
            numeric_amount = None
        if numeric_amount is not None:
            total_amount += numeric_amount
        invoice = {
            "source": record.get("filename"),
            "supplier_name": flat.get("supplier_name") or extract_named_value(text, ["supplier_name", "supplier", "vendor"]),
            "customer_name": flat.get("customer_name") or extract_named_value(text, ["customer_name", "customer", "bill_to"]),
            "invoice_id": flat.get("invoice_id") or extract_named_value(text, ["invoice_id", "invoice number", "invoice"]),
            "tax_id": flat.get("tax_id") or extract_named_value(text, ["tax_id", "tax id"]),
            "due_date": flat.get("due_date") or extract_named_value(text, ["due_date", "due date"]),
            "total_amount": numeric_amount,
            "billing_period": flat.get("billing_period") or extract_named_value(text, ["billing_period", "billing period"]),
            "line_items": flat.get("line_items") or [],
            "consumption_fields": flat.get("consumption_fields") or {},
            "warnings": record.get("warnings") or [],
        }
        invoices.append(invoice)
    return {
        "schema_version": "mn.blueprint.legal_assistant.invoice_bill_extraction.v1",
        "invoice_count": len(invoices),
        "invoices": invoices,
        "totals": {"total_amount": round(total_amount, 2)},
        "missing_fields": missing_invoice_fields(invoices),
        "review_required": True,
    }


def missing_invoice_fields(invoices: list[dict[str, Any]]) -> list[dict[str, Any]]:
    missing = []
    for invoice in invoices:
        absent = [field for field in ("supplier_name", "invoice_id", "due_date", "total_amount") if not invoice.get(field)]
        if absent:
            missing.append({"source": invoice.get("source"), "fields": absent})
    return missing


def snippet_around(text: str, keyword: str, width: int = 220) -> str:
    lowered = text.lower()
    index = lowered.find(keyword.lower())
    if index < 0:
        return ""
    start = max(0, index - width // 3)
    end = min(len(text), index + width)
    return " ".join(text[start:end].split())


def clause_locator(record: dict[str, Any], keyword: str) -> str:
    pages = record.get("pages") if isinstance(record.get("pages"), list) else []
    for index, page in enumerate(pages, start=1):
        if isinstance(page, dict):
            page_text = str(page.get("text") or page.get("content") or "")
            page_number = page.get("page_number") or page.get("page") or index
        else:
            page_text = str(page or "")
            page_number = index
        if keyword.lower() in page_text.lower():
            return f"page {page_number}"
    return f"document-level keyword match: {keyword}"


def extract_contract_clause_packet(records: list[dict[str, Any]]) -> dict[str, Any]:
    clauses = []
    for record in contract_records(records):
        text = str(record.get("text") or "")
        for field in CLAUSE_FIELDS:
            keyword = field.replace("_", " ")
            snippet = snippet_around(text, keyword)
            if not snippet and field == "liability":
                snippet = snippet_around(text, "limitation of liability")
            if not snippet and field == "indemnity":
                snippet = snippet_around(text, "indemn")
            if snippet:
                clauses.append(
                    {
                        "source": record.get("filename"),
                        "source_ref": record.get("filename"),
                        "clause_type": field,
                        "status": "present",
                        "locator": clause_locator(record, keyword),
                        "text": snippet,
                        "observed_language": snippet,
                        "confidence": 0.78,
                        "review_notes": ["Attorney review required before relying on this classification."],
                    }
                )
    clause_types = sorted({clause["clause_type"] for clause in clauses})
    return {
        "schema_version": "mn.blueprint.legal_assistant.contract_clause_review.v1",
        "contract_count": len(contract_records(records)),
        "clause_count": len(clauses),
        "clause_types": clause_types,
        "clauses": clauses,
        "playbook_comparison": compare_to_playbook(clause_types),
        "review_required": True,
    }


def compare_to_playbook(clause_types: list[str]) -> dict[str, Any]:
    required = {"governing_law", "assignment", "indemnity", "termination", "liability"}
    present = set(clause_types)
    missing = sorted(required - present)
    deviations = []
    if "liability" in present:
        deviations.append("Confirm liability cap, exclusions, and indirect damages language with counsel.")
    if "assignment" in present:
        deviations.append("Check whether assignment restrictions affect transfers, affiliates, or change-of-control events.")
    if "indemnity" in present:
        deviations.append("Confirm indemnity scope, covered claims, defense control, exclusions, and survival with counsel.")
    if "termination" in present:
        deviations.append("Check termination triggers, cure periods, payment consequences, and post-termination obligations.")
    return {
        "required_clause_types": sorted(required),
        "present_required_clause_types": sorted(required & present),
        "missing_required_clause_types": missing,
        "deviations": deviations,
        "status": "needs_attorney_review" if missing or deviations else "review_ready",
    }


def summarize_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    evidence = []
    for record in records[:30]:
        text = str(record.get("text") or "")
        preview = " ".join(text.split())[:500]
        evidence.append(
            {
                "source": record.get("filename"),
                "document_type": record.get("document_type"),
                "text_preview": preview,
                "structured_values": structured_values_from_text(text),
                "ocr_required": bool(record.get("ocr_required")),
                "extraction_method": record.get("extraction_method"),
                "warnings": record.get("warnings") or [],
            }
        )
    if not evidence:
        evidence.append(
            {
                "source": "examples/sample_inputs",
                "document_type": "missing_input",
                "text_preview": "No readable documents were found. Add invoice, bill, contract, or clause files and rerun.",
                "structured_values": [],
                "ocr_required": False,
                "extraction_method": "no_input",
                "warnings": ["No local documents were available."],
            }
        )
    return evidence


def record_warnings(records: list[dict[str, Any]]) -> list[str]:
    warnings: list[str] = []
    for record in records:
        for warning in record.get("warnings") or []:
            text = str(warning)
            if text and text not in warnings:
                warnings.append(text)
    return warnings


def issue_register(
    records: list[dict[str, Any]],
    invoice_packet: dict[str, Any],
    clause_packet: dict[str, Any],
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for item in invoice_packet.get("missing_fields") or []:
        issues.append(
            {
                "area": "invoice_bill_extraction",
                "severity": "medium",
                "source": item.get("source"),
                "issue": f"Missing payable fields: {', '.join(item.get('fields') or [])}",
                "review_owner": "human_ap_or_legal_reviewer",
            }
        )
    for missing in clause_packet.get("playbook_comparison", {}).get("missing_required_clause_types") or []:
        issues.append(
            {
                "area": "contract_clause_review",
                "severity": "high",
                "source": "contract packet",
                "issue": f"Required clause type not found: {missing}",
                "review_owner": "attorney",
            }
        )
    for record in records:
        if record.get("ocr_required"):
            issues.append(
                {
                    "area": "document_intake",
                    "severity": "medium",
                    "source": record.get("filename"),
                    "issue": "OCR is required before relying on this source.",
                    "review_owner": "document_reviewer",
                }
            )
    return issues


def effective_llm_config_name(
    config: dict[str, Any],
    actor_id: str,
    runtime_selection: dict[str, Any] | None = None,
) -> str:
    llm = config.get("llm") if isinstance(config.get("llm"), dict) else {}
    agents = llm.get("agents") if isinstance(llm.get("agents"), dict) else {}
    agent = agents.get(actor_id) if isinstance(agents.get(actor_id), dict) else {}
    profile_name = str(agent.get("llm_config") or llm.get("default_config") or "primary")

    # Heavy actors are authored with the medium/Nemotron profile, but a local
    # Mac may only advertise the small Gemma runtime. In that case the heavy
    # profile's strict JSON contract is not compatible with the selected model;
    # use the existing small-model contract instead of forcing strict parsing.
    if profile_name == "large" and str((runtime_selection or {}).get("selected_model") or "").lower() == "small":
        return "primary"
    return profile_name


def model_profiles_used(
    config: dict[str, Any],
    runtime_selection: dict[str, Any] | None = None,
) -> dict[str, dict[str, str]]:
    agents = (config.get("llm") or {}).get("agents") or {}
    configs = (config.get("llm") or {}).get("configs") or {}
    result = {}
    for step in WORKFLOW_STEPS:
        llm_config = effective_llm_config_name(config, step, runtime_selection)
        model = str((configs.get(llm_config) or {}).get("model") or (config.get("llm") or {}).get("model") or "unknown")
        result[step] = {"llm_config": llm_config, "model": model}
    return result


def llm_profile_config(
    config: dict[str, Any],
    actor_id: str,
    runtime_selection: dict[str, Any] | None = None,
) -> dict[str, Any]:
    llm = config.get("llm") if isinstance(config.get("llm"), dict) else {}
    profile_name = effective_llm_config_name(config, actor_id, runtime_selection)
    profiles = llm.get("configs") if isinstance(llm.get("configs"), dict) else {}
    profile = profiles.get(profile_name)
    return profile if isinstance(profile, dict) else {}


def configured_llm_review_agents(config: dict[str, Any]) -> list[str]:
    """Return only actors that need live reasoning after deterministic intake.

    Folder watching and document reading are deterministic stages in this
    blueprint. Calling the LLM again for those stages duplicated work and
    made a normal run exceed the declared runtime and token budgets.
    """
    llm = config.get("llm") if isinstance(config.get("llm"), dict) else {}
    configured = llm.get("review_agents")
    if isinstance(configured, list) and configured:
        candidates = [str(item) for item in configured if str(item)]
    else:
        candidates = list(DEFAULT_LLM_REVIEW_AGENTS)
    agents = llm.get("agents") if isinstance(llm.get("agents"), dict) else {}
    return [actor_id for actor_id in candidates if actor_id in agents]


def build_llm_client(config: dict[str, Any], payload: dict[str, Any], llm_client: Any | None) -> Any:
    if llm_client is not None:
        return llm_client
    if fake_llm_requested(config, payload):
        return DeterministicLLM()
    if get_actor_llm_client is None:
        raise RuntimeError(
            "Legal Assistant requires the shared live LLM client for normal runs. "
            "Install/enable mirrorneuron-litellm-communicate-skill or run with explicit fake/quick-test mode."
        )
    selection = select_default_model(config)
    try:
        client = get_actor_llm_client(config, None)
    except Exception as exc:
        raise RuntimeError(f"Unable to initialize shared live LLM client: {exc}") from exc
    if client is None or str(getattr(client, "provider", "")).lower() in {"fake", "mock", "deterministic", "test"}:
        raise RuntimeError("Shared live LLM client was unavailable for a normal Legal Assistant run.")
    setattr(client, "runtime_selection", selection)
    llm_config = config.get("llm") if isinstance(config.get("llm"), dict) else {}
    profile_name = str(os.environ.get("MN_LLM_CONFIG") or llm_config.get("default_config") or "primary")
    profiles = llm_config.get("configs") if isinstance(llm_config.get("configs"), dict) else {}
    profile = profiles.get(profile_name) if isinstance(profiles.get(profile_name), dict) else profiles.get("primary")
    if isinstance(profile, dict):
        for attribute, key in (
            ("timeout_seconds", "timeout_seconds"),
            ("max_tokens", "max_tokens"),
            ("num_retries", "num_retries"),
            ("retry_backoff_seconds", "retry_backoff_seconds"),
        ):
            if key in profile and hasattr(client, attribute):
                setattr(client, attribute, profile[key])
        if hasattr(client, "strict"):
            setattr(client, "strict", bool(profile.get("strict_json", False)))
    return client


def llm_generate(
    config: dict[str, Any],
    llm: Any,
    *,
    actor_id: str,
    actor_spec: dict[str, Any],
    fallback: dict[str, Any],
    context: dict[str, Any],
    knowledge_context: dict[str, Any],
) -> dict[str, Any]:
    if llm is None:
        llm = DeterministicLLM()
    runtime_selection = getattr(llm, "runtime_selection", {})
    profile = model_profiles_used(config, runtime_selection).get(actor_id) or {}
    role = str(actor_spec.get("role") or actor_id.replace("_", " ").title())
    responsibilities = [str(item) for item in actor_spec.get("responsibilities") or [] if str(item)]
    prompt_details = load_prompt(REVIEW_PROMPT_FILES.get(actor_id, "review-artifact-fields.md"))
    output_contract = {
        "required_fields": [
            "summary",
            "key_findings",
            "review_questions",
            "evidence_gaps",
            "risk_flags",
            "next_steps",
            "confidence",
            "review_only",
            "source_refs",
        ],
        "optional_analysis_fields": [
            "clause_findings",
            "issue_findings",
            "deterministic_checks",
            "analysis_scope",
        ],
        "field_shapes": {
            "clause_findings": [
                "clause_type",
                "status",
                "source_ref",
                "locator",
                "observed_language",
                "affected_party",
                "bounded_implication",
                "uncertainty",
                "attorney_question",
            ],
            "issue_findings": [
                "area",
                "severity",
                "source_refs",
                "issue",
                "owner",
                "evidence_needed",
            ],
        },
        "source_ref_rule": "Use only supplied local source refs or the bundled legal playbook reference.",
        "unknown_rule": "If evidence is absent, say unknown, not found, ambiguous, or review required; never infer a legal or payable fact.",
    }
    if hasattr(llm, "generate_json"):
        profile_config = llm_profile_config(config, actor_id, runtime_selection)
        previous_values: dict[str, Any] = {}
        for attribute, key in (
            ("timeout_seconds", "timeout_seconds"),
            ("max_tokens", "max_tokens"),
            ("num_retries", "num_retries"),
            ("retry_backoff_seconds", "retry_backoff_seconds"),
        ):
            if key in profile_config and hasattr(llm, attribute):
                previous_values[attribute] = getattr(llm, attribute)
                setattr(llm, attribute, profile_config[key])
        if hasattr(llm, "strict") and "strict_json" in profile_config:
            previous_values["strict"] = getattr(llm, "strict")
            setattr(llm, "strict", bool(profile_config["strict_json"]))
        try:
            response = llm.generate_json(
                system_prompt=render_prompt(
                    "actor-review-system.md",
                    actor_id=actor_id,
                    role=role,
                    responsibilities="\n".join(f"- {item}" for item in responsibilities) or "- Preserve source-grounded, review-only output.",
                    prompt_details=prompt_details,
                ),
                user_prompt=json.dumps(
                    {
                        "actor_id": actor_id,
                        "role": role,
                        "responsibilities": responsibilities,
                        "model_profile": profile,
                        "context": redact_value(context),
                        "knowledge_context": knowledge_context,
                        "output_contract": output_contract,
                        "fallback_shape": fallback,
                    },
                    sort_keys=True,
                    default=str,
                )[:9000],
                fallback=fallback,
            )
            return response if isinstance(response, dict) else fallback
        finally:
            for attribute, value in previous_values.items():
                setattr(llm, attribute, value)
    return fallback


def run_actor_reviews(
    config: dict[str, Any],
    llm_client: Any | None,
    context: dict[str, Any],
    knowledge_context: dict[str, Any],
    rag_state: dict[str, Any],
) -> dict[str, Any]:
    llm = llm_client or DeterministicLLM()
    actor_findings: dict[str, Any] = {}
    agents = (config.get("llm") or {}).get("agents") or {}
    for actor_id in configured_llm_review_agents(config):
        spec = agents[actor_id]
        fallback = {
            "actor_id": actor_id,
            "role": spec.get("role") or actor_id,
            "llm_config": spec.get("llm_config") or "primary",
            "summary": f"{spec.get('role') or actor_id} reviewed the local evidence packet.",
            "key_findings": [],
            "review_questions": [],
            "evidence_gaps": [],
            "risk_flags": [],
            "next_steps": ["Review supplied source evidence before downstream use."],
            "confidence": 0.72,
            "review_only": True,
            "source_refs": [],
            "analysis_scope": ["source-grounded review only"],
            "clause_findings": [],
            "issue_findings": [],
            "deterministic_checks": [],
            "findings": [
                "Keep the packet review-only.",
                "Preserve source references for every extracted value.",
                "Escalate legal, payment, signature, or external-sharing actions for human approval.",
            ],
        }
        actor_knowledge = legal_knowledge_context_for_actor(knowledge_context, rag_state, actor_id)
        finding = llm_generate(
            config,
            llm,
            actor_id=actor_id,
            actor_spec=spec,
            fallback=fallback,
            context=context,
            knowledge_context=actor_knowledge,
        )
        finding.setdefault(
            "knowledge_context",
            {
                "status": actor_knowledge.get("rag_status"),
                "query": actor_knowledge.get("query"),
                "citations": actor_knowledge.get("citations") or [],
                "path": actor_knowledge.get("path"),
                "sha256": actor_knowledge.get("sha256"),
            },
        )
        actor_findings[actor_id] = finding
    return actor_findings


def llm_usage(llm_client: Any | None, actor_findings: dict[str, Any]) -> dict[str, Any]:
    return {
        "provider": getattr(llm_client, "provider", "fake"),
        "model": getattr(llm_client, "model", "deterministic-legal-assistant"),
        "calls": int(getattr(llm_client, "calls", len(actor_findings))),
        "fallback_calls": int(getattr(llm_client, "fallback_calls", 0)),
        "input_tokens": int(getattr(llm_client, "input_tokens", 0) or 0),
        "output_tokens": int(getattr(llm_client, "output_tokens", 0) or 0),
        "total_tokens": int(getattr(llm_client, "total_tokens", 0) or 0),
        "estimated_tokens": int(getattr(llm_client, "estimated_tokens", 0) or 0),
        "runtime_selection": getattr(llm_client, "runtime_selection", {}),
    }


def next_steps(issue_count: int) -> list[str]:
    steps = [
        "Review invoice amounts, due dates, supplier details, and contract clauses against the source files.",
        "Ask an attorney to confirm clause classifications, missing terms, privilege concerns, and playbook deviations.",
        "Approve, revise, or reject the packet before any payment, ERP, signature, counterparty, or external-sharing action.",
    ]
    if issue_count:
        steps.insert(0, f"Resolve {issue_count} issue-register item(s) before downstream use.")
    return steps


def blocked_actions() -> list[str]:
    return [
        "send_legal_advice",
        "approve_or_sign_contract",
        "redline_contract_as_final",
        "post_invoice_to_erp",
        "submit_payment_instruction",
        "email_vendor_or_counterparty_without_review",
        "share_privileged_or_private_documents_externally",
    ]


def build_markdown(final_artifact: dict[str, Any]) -> str:
    lines = [
        "# Legal Assistant Report",
        "",
        f"**Status:** {final_artifact.get('status')}",
        f"**Recommended action:** {final_artifact.get('recommended_action')}",
        f"**Confidence:** {final_artifact.get('confidence')}",
        "",
        "## Executive Summary",
        str(final_artifact.get("executive_summary") or ""),
        "",
        "## Invoice And Bill Review",
    ]
    invoice_packet = final_artifact.get("invoice_bill_extraction") or {}
    lines.append(f"- Invoices or bills detected: {invoice_packet.get('invoice_count', 0)}")
    lines.append(f"- Total extracted amount: {invoice_packet.get('totals', {}).get('total_amount', 0)}")
    for invoice in invoice_packet.get("invoices") or []:
        lines.append(f"- {invoice.get('source')}: {invoice.get('supplier_name') or 'Unknown supplier'} / {invoice.get('total_amount')}")
    lines.extend(["", "## Contract Clause Review"])
    clause_packet = final_artifact.get("contract_clause_review") or {}
    lines.append(f"- Contracts detected: {clause_packet.get('contract_count', 0)}")
    lines.append(f"- Clauses detected: {clause_packet.get('clause_count', 0)}")
    for clause in (clause_packet.get("clauses") or [])[:10]:
        lines.append(f"- {clause.get('clause_type')}: {clause.get('source')}")
    lines.extend(["", "## Issue Register"])
    for issue in final_artifact.get("legal_issue_register") or []:
        lines.append(f"- [{issue.get('severity')}] {issue.get('area')}: {issue.get('issue')}")
    ingestion = final_artifact.get("document_ingestion") or {}
    rag = (final_artifact.get("knowledge_reference") or {}).get("rag") or {}
    lines.extend(
        [
            "",
            "## OCR And RAG",
            f"- OCR status: {(ingestion.get('ocr') or {}).get('status', 'not reported')}",
            f"- OCR runtime model: {(ingestion.get('ocr') or {}).get('runtime_model') or 'selected automatically by the OCR skill'}",
            f"- OCR-required sources: {', '.join(ingestion.get('ocr_required_sources') or ['none'])}",
            f"- Knowledge RAG status: {rag.get('status', 'not reported')}",
            f"- Knowledge RAG warnings: {len(rag.get('warnings') or [])}",
        ]
    )
    lines.extend(["", "## Deep LLM Review"])
    for actor_id, finding in (final_artifact.get("actor_findings") or {}).items():
        if not isinstance(finding, dict):
            continue
        lines.extend(
            [
                f"### {finding.get('role') or actor_id}",
                str(finding.get("summary") or "No LLM summary returned."),
                f"- Findings: {'; '.join(str(item) for item in (finding.get('key_findings') or finding.get('findings') or [])[:5]) or 'none'}",
                f"- Review questions: {'; '.join(str(item) for item in (finding.get('review_questions') or [])[:5]) or 'none'}",
                f"- Evidence gaps: {'; '.join(str(item) for item in (finding.get('evidence_gaps') or [])[:5]) or 'none'}",
                f"- Risk flags: {'; '.join(str(item) for item in (finding.get('risk_flags') or [])[:5]) or 'none'}",
                f"- Confidence: {finding.get('confidence')}",
                f"- Source refs: {', '.join(str(item) for item in (finding.get('source_refs') or [])[:8]) or 'none'}",
                "",
            ]
        )
    lines.extend(["", "## Evidence Highlights"])
    for item in (final_artifact.get("evidence") or [])[:10]:
        preview = str(item.get("text_preview") or "").replace("\n", " ").strip()
        if len(preview) > 220:
            preview = preview[:217] + "..."
        lines.append(f"- **{item.get('source')}** ({item.get('document_type')}): {preview or 'No text preview available.'}")
    lines.extend(["", "## Review Boundary"])
    for action in blocked_actions():
        lines.append(f"- {action}")
    lines.extend(["", "## Source References"])
    for ref in final_artifact.get("source_refs") or []:
        lines.append(f"- `{ref}`")
    return "\n".join(lines) + "\n"


def write_outputs(
    *,
    final_artifact: dict[str, Any],
    output_folder: Path,
    run_dir: Path,
    run_id: str,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    output_folder.mkdir(parents=True, exist_ok=True)
    warnings = final_artifact.get("quality_summary", {}).get("warnings") or []
    action_ledger = {
        "schema_version": "mn.blueprint.action_ledger.v1",
        "blueprint_id": BLUEPRINT_ID,
        "run_id": run_id,
        "review_only": True,
        "actions": [
            {"step": "load_inputs", "status": "completed", "source_refs": ["inputs.json"]},
            {"step": "extract_invoice_bill_fields", "status": "completed"},
            {"step": "extract_contract_clauses", "status": "completed"},
            {"step": "write_integrated_report", "status": "completed", "output_folder": str(output_folder)},
        ],
        "blocked_actions": blocked_actions(),
    }
    artifact_quality = {
        "schema_version": "mn.blueprint.artifact_quality.v1",
        "blueprint_id": BLUEPRINT_ID,
        "run_id": run_id,
        "status": "usable_with_review" if final_artifact.get("document_count") else "needs_input",
        "checks": [
            {"name": "has_evidence", "ok": bool(final_artifact.get("evidence"))},
            {"name": "has_invoice_or_contract_artifact", "ok": bool(final_artifact.get("invoice_bill_extraction") or final_artifact.get("contract_clause_review"))},
            {"name": "review_boundary_present", "ok": True},
            {"name": "deep_llm_review_present", "ok": bool(final_artifact.get("legal_deep_review", {}).get("actors"))},
            {"name": "writes_user_download_folder", "ok": True},
        ],
        "warning_count": len(warnings),
        "warnings": warnings[:20],
        "issue_count": len(final_artifact.get("legal_issue_register") or []),
    }
    run_health = {
        "schema_version": "mn.blueprint.run_health.v1",
        "blueprint_id": BLUEPRINT_ID,
        "run_id": run_id,
        "status": "completed",
        "warning_count": len(warnings),
        "failure_count": 0,
        "output_folder": str(output_folder),
        "run_store": str(run_dir),
        "llm_provider": (final_artifact.get("llm_usage") or {}).get("provider"),
        "llm_model": (final_artifact.get("llm_usage") or {}).get("model"),
        "llm_calls": (final_artifact.get("llm_usage") or {}).get("calls"),
        "ocr_status": ((final_artifact.get("document_ingestion") or {}).get("ocr") or {}).get("status"),
        "rag_status": ((final_artifact.get("knowledge_reference") or {}).get("rag") or {}).get("status"),
        "generated_at": utc_now_iso(),
    }
    write_json(output_folder / "final_artifact.json", final_artifact)
    write_json(output_folder / "invoice_bill_extraction.json", final_artifact["invoice_bill_extraction"])
    write_json(output_folder / "contract_clause_review.json", final_artifact["contract_clause_review"])
    write_json(output_folder / "legal_issue_register.json", final_artifact["legal_issue_register"])
    write_json(output_folder / "legal_deep_review.json", final_artifact["legal_deep_review"])
    write_json(output_folder / "action_ledger.json", action_ledger)
    write_json(output_folder / "artifact_quality.json", artifact_quality)
    write_json(output_folder / "run_health.json", run_health)
    write_text(output_folder / "legal_assistant_report.md", build_markdown(final_artifact))
    for name, value in (
        ("action_ledger.json", action_ledger),
        ("artifact_quality.json", artifact_quality),
        ("run_health.json", run_health),
    ):
        write_json(run_dir / name, value)
    write_json(run_dir / "legal_deep_review.json", final_artifact["legal_deep_review"])
    return action_ledger, artifact_quality, run_health


def run_blueprint(
    inputs: dict[str, Any] | None = None,
    config: dict[str, Any] | None = None,
    runs_root: str | Path | None = None,
    run_id: str | None = None,
    llm_client: Any | None = None,
) -> dict[str, Any]:
    start_agent_beacon_thread(f"{BLUEPRINT_NAME} is running")
    root = blueprint_dir()
    resolved_config = load_resolved_config(config)
    payload = resolve_inputs(resolved_config, inputs)
    run_id = run_id or str(payload.get("run_id") or f"{BLUEPRINT_ID}-{uuid.uuid4().hex[:8]}")
    document_folder = expand_path(payload.get("document_folder") or payload.get("input_folder") or "examples/sample_inputs", root=root)
    output_folder = resolve_output_folder(payload, resolved_config, inputs)
    run_dir = resolve_run_dir(output_folder, run_id, runs_root)
    run_dir.mkdir(parents=True, exist_ok=True)

    llm = build_llm_client(resolved_config, payload, llm_client)
    runtime_context = {"config": resolved_config, "payload": payload, "llm": llm}
    ocr_client, ocr_status = build_ocr_runtime(runtime_context)
    knowledge_context = load_legal_knowledge(root)
    rag_state = prepare_legal_rag(resolved_config, root, knowledge_context)

    write_json(run_dir / "run.json", {"run_id": run_id, "blueprint_id": BLUEPRINT_ID, "status": "running", "started_at": utc_now_iso()})
    write_json(run_dir / "config.json", resolved_config)
    write_json(run_dir / "inputs.json", {"payload": payload, "document_folder": str(document_folder), "dataset_inputs": DATASET_INPUTS})
    append_event(run_dir, "blueprint_phase_started", {"phase": "loading_inputs", "component": BLUEPRINT_ID})
    append_event(run_dir, "blueprint_phase_completed", {"phase": "loading_inputs", "component": BLUEPRINT_ID})
    append_event(run_dir, "blueprint_phase_started", {"phase": "running_worker", "component": BLUEPRINT_ID})

    records = load_documents(document_folder, ocr_client=ocr_client)
    evidence = summarize_records(records)
    invoice_packet = extract_invoice_bill_packet(records)
    clause_packet = extract_contract_clause_packet(records)
    issues = issue_register(records, invoice_packet, clause_packet)
    warnings = record_warnings(records)
    confidence = 0.35 if not records else 0.58 if warnings or issues else 0.78
    status = "needs_input" if not records else "review_ready_with_issues" if warnings or issues else "review_ready"
    actor_context = {
        "document_count": len(records),
        "invoice_packet": invoice_packet,
        "clause_packet": clause_packet,
        "issue_count": len(issues),
        "evidence": evidence[:8],
        "review_policy": payload.get("review_policy") or {},
        "document_ingestion": {
            "ocr": ocr_status,
            "ocr_required_sources": [record.get("filename") for record in records if record.get("ocr_required")],
            "source_refs": [record.get("filename") for record in records],
        },
        "knowledge_rag": {
            "status": rag_state.get("status"),
            "warnings": rag_state.get("warnings") or [],
        },
    }
    actor_findings = run_actor_reviews(resolved_config, llm, actor_context, knowledge_context, rag_state)
    rag_public = {key: value for key, value in rag_state.items() if not str(key).startswith("_")}
    source_refs = ["inputs.json", "events.jsonl", "result.json", "invoice_bill_extraction.json", "contract_clause_review.json"]
    source_refs.extend(sorted({str(record.get("filename")) for record in records if record.get("filename")}))
    final_artifact = {
        "type": OUTPUT_TYPE,
        "title": f"{BLUEPRINT_NAME} Review Packet",
        "status": status,
        "executive_summary": (
            f"{BLUEPRINT_NAME} processed {len(records)} local document record(s), "
            f"found {invoice_packet['invoice_count']} invoice/bill packet(s), "
            f"and extracted {clause_packet['clause_count']} contract clause candidate(s)."
        ),
        "recommended_action": RECOMMENDED_ACTION,
        "confidence": confidence,
        "evidence": evidence,
        "next_steps": next_steps(len(issues)),
        "source_refs": source_refs,
        "dataset_inputs": DATASET_INPUTS,
        "knowledge_reference": {
            "id": knowledge_context.get("id"),
            "path": knowledge_context.get("path"),
            "sha256": knowledge_context.get("sha256"),
            "rag": rag_public,
        },
        "field_profile": {"invoice_fields": INVOICE_FIELDS, "clause_fields": CLAUSE_FIELDS},
        "document_count": len(records),
        "document_summary": {
            "document_count": len(records),
            "invoice_or_bill_count": len(invoice_records(records)),
            "contract_or_clause_count": len(contract_records(records)),
            "ocr_required_count": len([record for record in records if record.get("ocr_required")]),
            "warning_count": len(warnings),
            "document_types": sorted({str(record.get("document_type")) for record in records}),
        },
        "document_ingestion": {
            "ocr": ocr_status,
            "ocr_required_count": len([record for record in records if record.get("ocr_required")]),
            "ocr_required_sources": [record.get("filename") for record in records if record.get("ocr_required")],
        },
        "invoice_bill_extraction": invoice_packet,
        "contract_clause_review": clause_packet,
        "legal_issue_register": issues,
        "quality_summary": {
            "real_values_present": bool(records),
            "evidence_preview_count": len(evidence),
            "warnings": warnings[:10],
            "issue_count": len(issues),
        },
        "review_boundary": {"review_only": True, "blocked_actions": blocked_actions()},
        "model_profiles_used": model_profiles_used(resolved_config, getattr(llm, "runtime_selection", {})),
        "legal_deep_review": {
            "actors": actor_findings,
            "review_only": True,
            "rag_status": rag_public,
        },
        "actor_findings": actor_findings,
        "llm_usage": llm_usage(llm, actor_findings),
        "generated_at": utc_now_iso(),
    }
    action_ledger, artifact_quality, run_health = write_outputs(
        final_artifact=final_artifact,
        output_folder=output_folder,
        run_dir=run_dir,
        run_id=run_id,
    )
    result = {
        "run_id": run_id,
        "blueprint_id": BLUEPRINT_ID,
        "status": "completed",
        "records": records,
        "final_artifact": final_artifact,
        "action_ledger": action_ledger,
        "artifact_quality": artifact_quality,
        "run_health": run_health,
    }
    append_event(run_dir, "blueprint_phase_completed", {"phase": "running_worker", "component": BLUEPRINT_ID})
    append_event(run_dir, "human_input_requested", {"mode": "approval_required", "reason": "Review legal and payable findings before downstream use."})
    append_event(run_dir, "blueprint_phase_started", {"phase": "writing_artifacts", "component": BLUEPRINT_ID})
    write_json(run_dir / "result.json", result)
    write_json(run_dir / "final_artifact.json", final_artifact)
    for name in ("result.json", "final_artifact.json", "action_ledger.json", "artifact_quality.json", "run_health.json", "legal_deep_review.json"):
        append_event(run_dir, "artifact_written", {"path": name})
    append_event(run_dir, "blueprint_phase_completed", {"phase": "writing_artifacts", "component": BLUEPRINT_ID})
    append_event(run_dir, "blueprint_phase_completed", {"phase": "completed", "component": BLUEPRINT_ID})
    write_json(run_dir / "run.json", {"run_id": run_id, "blueprint_id": BLUEPRINT_ID, "status": "completed", "completed_at": utc_now_iso()})
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=BLUEPRINT_NAME)
    parser.add_argument("--input-folder", default="")
    parser.add_argument("--output-folder", default="")
    parser.add_argument("--runs-root", default="")
    parser.add_argument("--run-id", default="")
    parser.add_argument("--config-json", default="")
    args = parser.parse_args()
    inputs: dict[str, Any] = {}
    if args.input_folder:
        inputs["document_folder"] = args.input_folder
        inputs["input_folder"] = args.input_folder
    if args.output_folder:
        inputs["output_folder"] = args.output_folder
    config = json.loads(args.config_json) if args.config_json else None
    result = run_blueprint(inputs=inputs, config=config, runs_root=args.runs_root or None, run_id=args.run_id or None)
    print(json.dumps({"run_id": result["run_id"], "status": result["status"], "final_artifact": result["final_artifact"]}, indent=2, default=str))


if __name__ == "__main__":
    main()
