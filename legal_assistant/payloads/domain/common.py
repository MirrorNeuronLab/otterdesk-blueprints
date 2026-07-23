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
from mn_sdk.blueprint_support import source_manifest

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
_SOURCE_MANIFEST = source_manifest(__file__)
_AGENT_REGISTRY = (_SOURCE_MANIFEST.get("agents") or {}).get("registry") or {}
AGENT_IDS = tuple(str(agent_id) for agent_id in _AGENT_REGISTRY)
HEAVY_MODEL_STEPS = {
    "contract_playbook_comparator",
    "legal_review_auditor",
    "legal_reporter",
}
DEFAULT_LLM_REVIEW_AGENTS = tuple(
    str(agent_id)
    for agent_id in (_SOURCE_MANIFEST.get("agentic_research") or {}).get("agent_ids") or []
)
BLOCKED_ACTIONS = list(
    (((_SOURCE_MANIFEST.get("workflow") or {}).get("policy") or {}).get("human") or {}).get("blocked_actions")
    or []
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
PROMPTS = PromptLibrary.from_script(__file__, parents_up=1)
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
