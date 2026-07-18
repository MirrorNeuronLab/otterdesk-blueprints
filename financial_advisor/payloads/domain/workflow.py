#!/usr/bin/env python3.11
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import os
import re
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


RUNTIME_SKILL_PACKAGES = (
    "mirrorneuron-blueprint-support-skill",
    "mirrorneuron-llm-ocr-skill",
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
    start_agent_beacon_thread,
)

try:
    from mn_llm_ocr_skill import docker_ocr_client_factory_from_config, extract_document
except Exception:  # pragma: no cover - optional runtime dependency
    docker_ocr_client_factory_from_config = None
    extract_document = None


BLUEPRINT_ID = "financial_advisor"
BLUEPRINT_NAME = "Financial Advisor"
OUTPUT_TYPE = "financial_advisor_report"
RECOMMENDED_ACTION = "review_integrated_financial_advisor_packet_before_any_financial_action"
OCR_SUFFIXES = {".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}
SUPPORTED_SUFFIXES = OCR_SUFFIXES | {".txt", ".json", ".csv", ".md"}
TEXT_SUFFIXES = {".txt", ".json", ".csv", ".md"}
OCR_MIN_TEXT_CHARS = 40
HEAVY_MODEL_STEPS = {
    "tax_workpaper_preparer",
    "tax_llm_reviewer",
    "portfolio_risk_engine",
    "portfolio_llm_reviewer",
    "advisor_review_auditor",
    "financial_advice_reporter",
}
MANIFEST_PATH = Path(__file__).resolve().parents[2] / "manifest.json"


def _source_workflow_step_specs() -> list[dict[str, Any]]:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    workflow = manifest.get("workflow") if isinstance(manifest.get("workflow"), dict) else {}
    steps = workflow.get("steps") if isinstance(workflow.get("steps"), list) else []
    return [step for step in steps if isinstance(step, dict)]


WORKFLOW_STEPS = [str(step["id"]) for step in _source_workflow_step_specs()]
WORKFLOW_STEP_IDS = WORKFLOW_STEPS
OUTPUT_MESSAGE_BY_STEP = {step: f"{step}_completed" for step in WORKFLOW_STEPS}
DEFAULT_MARKET_PRICES = {
    "SPY": 500.0,
    "AGG": 100.0,
    "GLD": 200.0,
    "BND": 74.0,
    "QQQ": 430.0,
    "VTI": 260.0,
}
RISK_BY_ASSET_CLASS = {
    "cash": 0.01,
    "rates": 0.05,
    "bond": 0.06,
    "fixed_income": 0.06,
    "commodity": 0.14,
    "equity": 0.18,
    "crypto": 0.65,
    "other": 0.22,
}
KNOWN_ETF_SYMBOLS = {
    "AGG",
    "BND",
    "GLD",
    "QQQ",
    "SPY",
    "VTI",
}
TAX_METADATA_FIELDS = {
    "source_dataset",
    "source_row",
    "label",
    "class",
    "form_type",
    "tax_form_type",
}
TAX_READINESS_LABELS = {
    "identified_only": "Identified",
    "extracted": "Extracted",
    "reconciled": "Reconciled",
    "complete": "Complete",
}
INVESTMENT_PROFILE_FIELDS = (
    "account_purpose",
    "investment_objective",
    "time_horizon",
    "expected_withdrawal_date",
    "risk_tolerance",
    "liquidity_needs",
    "tax_objective",
    "amount_that_must_remain_liquid",
    "other_investment_accounts",
    "tax_consequences_of_selling",
)
PUBLIC_GUIDANCE_SOURCES = [
    {
        "title": "Consumer.gov managing your money",
        "url": "https://consumer.gov/managing-your-money",
        "topic": "budget and cash-flow review",
    },
    {
        "title": "Consumer Financial Protection Bureau bank accounts",
        "url": "https://www.consumerfinance.gov/consumer-tools/bank-accounts/",
        "topic": "bank statements, fees, and account review",
    },
    {
        "title": "IRS records you should keep",
        "url": "https://www.irs.gov/businesses/small-businesses-self-employed/recordkeeping",
        "topic": "tax record organization",
    },
    {
        "title": "Investor.gov risk tolerance",
        "url": "https://www.investor.gov/introduction-investing/general-resources/news-alerts/alerts-bulletins/investor-bulletins/assessing-risk",
        "topic": "portfolio risk education",
    },
]
KNOWLEDGE_PLAYBOOK_RELATIVE_PATH = "knowledge/financial_advisor_playbook.md"
FINANCIAL_JUDGE_RUBRIC = [
    "method_correctness",
    "evidence_traceability",
    "calculation_invariance",
    "assumption_clarity",
    "missing_evidence_honesty",
    "risk_interpretation_quality",
    "review_only_language",
    "actionability_without_unauthorized_action",
]
KNOWLEDGE_SECTIONS_BY_STEP = {
    "cash_flow_llm_analyst": ("bank statement", "cash-flow", "evidence hierarchy", "report quality"),
    "tax_workpaper_preparer": ("tax", "tax form", "evidence hierarchy", "report quality"),
    "tax_llm_reviewer": ("tax", "tax form", "evidence hierarchy", "report quality"),
    "portfolio_risk_engine": ("portfolio", "risk", "evidence hierarchy", "report quality"),
    "portfolio_llm_reviewer": ("portfolio", "risk", "evidence hierarchy", "report quality"),
    "advisor_review_auditor": ("reconciliation", "audit", "evidence hierarchy", "report quality"),
    "financial_advice_reporter": ("report quality", "reconciliation", "review boundary", "evidence hierarchy"),
}
REVIEW_PROMPT_FILES = {
    "cash_flow_llm_analyst": "cash-flow-llm-review.md",
    "tax_llm_reviewer": "tax-llm-review.md",
    "portfolio_llm_reviewer": "portfolio-llm-review.md",
}
PROMPTS = PromptLibrary.from_script(__file__, parents_up=1)


def load_prompt(name: str) -> str:
    return PROMPTS.load(name)


def render_prompt(name: str, **values: str) -> str:
    return PROMPTS.render(name, **values)


def financial_knowledge_search_roots(blueprint_dir: Path) -> list[Path]:
    roots = [blueprint_dir, blueprint_dir / "payloads"]
    bundle_dir = os.environ.get("MN_BLUEPRINT_BUNDLE_DIR")
    if bundle_dir:
        roots.append(Path(bundle_dir).expanduser())
    script_path = Path(__file__).resolve()
    roots.extend([script_path.parents[1], script_path.parents[2], script_path.parents[3]])
    unique_roots: list[Path] = []
    for root in roots:
        if root not in unique_roots:
            unique_roots.append(root)
    return unique_roots


def load_financial_knowledge(blueprint_dir: Path) -> dict[str, Any]:
    playbook_path = next(
        (
            root / KNOWLEDGE_PLAYBOOK_RELATIVE_PATH
            for root in financial_knowledge_search_roots(blueprint_dir)
            if (root / KNOWLEDGE_PLAYBOOK_RELATIVE_PATH).exists()
        ),
        blueprint_dir / KNOWLEDGE_PLAYBOOK_RELATIVE_PATH,
    )
    try:
        content = playbook_path.read_text(encoding="utf-8")
    except OSError:
        content = ""
    return {
        "id": "financial_advisor_playbook",
        "title": "Financial Advisor Evidence And Review Playbook",
        "path": KNOWLEDGE_PLAYBOOK_RELATIVE_PATH,
        "resolved_path": str(playbook_path),
        "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest() if content else "",
        "content": content[:24000],
        "judge_rubric": list(FINANCIAL_JUDGE_RUBRIC),
        "domain_guard": "Use financial-advisor knowledge for review-only household finance, tax intake, and portfolio risk analysis; do not turn it into personalized execution advice.",
    }


def financial_knowledge_reference(active_knowledge: dict[str, Any] | None) -> dict[str, Any]:
    knowledge = active_knowledge or {}
    return {
        "id": knowledge.get("id"),
        "title": knowledge.get("title"),
        "path": knowledge.get("path"),
        "sha256": knowledge.get("sha256"),
        "judge_rubric": list(knowledge.get("judge_rubric") or FINANCIAL_JUDGE_RUBRIC),
        "domain_guard": knowledge.get("domain_guard"),
    }


def _knowledge_sections(content: str) -> list[dict[str, str]]:
    sections: list[dict[str, str]] = []
    current_title = "Overview"
    current_lines: list[str] = []
    for line in content.splitlines():
        if line.startswith("## "):
            if current_lines:
                sections.append({"title": current_title, "content": "\n".join(current_lines).strip()})
            current_title = line[3:].strip()
            current_lines = []
            continue
        if not line.startswith("# "):
            current_lines.append(line)
    if current_lines:
        sections.append({"title": current_title, "content": "\n".join(current_lines).strip()})
    return [section for section in sections if section["content"]]


def knowledge_context_for_step(active_knowledge: dict[str, Any] | None, step_id: str, *, max_chars: int = 9000) -> dict[str, Any]:
    knowledge = active_knowledge or {}
    content = str(knowledge.get("content") or "")
    terms = tuple(term.lower() for term in KNOWLEDGE_SECTIONS_BY_STEP.get(step_id, ("evidence hierarchy", "review boundary", "report quality")))
    matched = [
        section
        for section in _knowledge_sections(content)
        if any(term in section["title"].lower() for term in terms)
    ]
    if not matched:
        matched = _knowledge_sections(content)[:2]
    selected: list[dict[str, str]] = []
    used_chars = 0
    for section in matched:
        remaining = max_chars - used_chars
        if remaining <= 80:
            break
        section_content = section["content"][:remaining]
        selected.append({"title": section["title"], "content": section_content})
        used_chars += len(section_content)
    return {
        "playbook": financial_knowledge_reference(knowledge),
        "sections": selected,
        "judge_rubric": list(knowledge.get("judge_rubric") or FINANCIAL_JUDGE_RUBRIC),
        "retrieval_status": "static_blueprint_playbook" if selected else "unavailable",
        "instruction": "Treat this as domain guidance. Apply only when supported by the supplied artifacts; label unknowns and assumptions instead of filling gaps.",
    }


class DeterministicLLM(DeterministicFallbackLLM):
    def __init__(self) -> None:
        super().__init__(
            "deterministic-financial-advisor",
            default_summary="Deterministic review packet generated from local evidence.",
            confidence=0.74,
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
        return text[:1000]
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

    for parent in Path(__file__).resolve().parents:
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
        include_env_path=False,
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
    if not isinstance(value, dict):
        return {}
    interesting = {
        "document_folder",
        "input_folder",
        "output_folder",
        "portfolio",
        "tax_year",
        "filing_status",
        "monitoring",
    }
    if interesting & set(value):
        return {key: value[key] for key in value if key in value}
    for key in ("payload", "input", "body", "data", "message", "content"):
        found = find_payload(value.get(key))
        if found:
            return found
    return {}


def runtime_step_id() -> str:
    for value in (
        os.environ.get("MN_WORKFLOW_STEP_ID", ""),
        os.environ.get("MN_AGENT_ID", ""),
        os.environ.get("MN_NODE_ID", ""),
        os.environ.get("MIRROR_NEURON_AGENT_ID", ""),
        os.environ.get("MIRROR_NEURON_NODE_ID", ""),
    ):
        step_id = str(value or "").strip()
        if step_id in WORKFLOW_STEPS:
            return step_id
    return ""


def resolve_inputs(config: dict[str, Any], inputs: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = copy.deepcopy(((config.get("inputs") or {}).get("payload") or {}))
    payload = deep_merge(payload, runtime_message_payload())
    payload = deep_merge(payload, inputs or {})
    if "document_folder" not in payload and payload.get("input_folder"):
        payload["document_folder"] = payload["input_folder"]
    if "input_folder" not in payload and payload.get("document_folder"):
        payload["input_folder"] = payload["document_folder"]
    return payload


def expand_path(raw: Any, *, root: Path | None = None) -> Path:
    value = str(raw or "").strip()
    if not value:
        value = "."
    path = Path(value).expanduser()
    if not path.is_absolute() and root is not None:
        path = root / path
    return path.resolve()


def fingerprint_file(path: Path) -> dict[str, Any]:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(65536), b""):
                digest.update(chunk)
        size = path.stat().st_size
    except OSError:
        size = 0
    return {
        "path": str(path),
        "name": path.name,
        "sha256": digest.hexdigest(),
        "size_bytes": size,
        "suffix": path.suffix.lower(),
    }


def iter_input_files(document_folder: Path) -> list[Path]:
    if not document_folder.exists():
        return []
    return sorted(
        path
        for path in document_folder.rglob("*")
        if path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES
    )


def _ocr_skill_config(config: dict[str, Any]) -> dict[str, Any]:
    input_skills = config.get("input_skills") if isinstance(config.get("input_skills"), dict) else {}
    return {"input_skills": input_skills}


def _ocr_disabled_for_fake_run(ctx: dict[str, Any]) -> bool:
    provider = str(getattr(ctx.get("llm"), "provider", "") or "").strip().lower()
    return provider in {"fake", "mock", "deterministic", "test"} or fake_llm_requested(ctx["config"], ctx.get("payload"))


def build_ocr_runtime(ctx: dict[str, Any]) -> tuple[Any | None, dict[str, Any]]:
    section = (ctx["config"].get("input_skills") or {}).get("llm_ocr")
    section = section if isinstance(section, dict) else {}
    status: dict[str, Any] = {
        "enabled": section.get("enabled", True) is not False,
        "skill_available": extract_document is not None and docker_ocr_client_factory_from_config is not None,
        "configured": False,
        "status": "not_needed",
        "trigger": "PDF/image with less than 40 embedded characters",
        "warnings": [],
    }
    if not status["enabled"]:
        status["status"] = "disabled"
        status["warnings"].append("llm_ocr_disabled_in_config")
        return None, status
    if _ocr_disabled_for_fake_run(ctx):
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
                "status": "ready_for_lazy_first_use",
                "install_policy": getattr(model_config, "install_policy", None),
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
        classifier=lambda text, filename: classify_document(filename, text),
        llm_ocr_client=ocr_client,
        min_text_chars=OCR_MIN_TEXT_CHARS,
    )
    payload = record.to_dict() if hasattr(record, "to_dict") else dict(record)
    text = str(payload.get("text") or "")
    return {
        "source_ref": path.name,
        "path": str(path),
        "suffix": path.suffix.lower(),
        "kind": str(payload.get("document_type") or classify_document(path.name, text)),
        "text": text[:12000],
        "data": None,
        "warnings": [str(item) for item in (payload.get("warnings") or [])],
        "fingerprint": fingerprint_file(path),
        "ocr_required": bool(payload.get("ocr_required")),
        "extraction_method": str(payload.get("extraction_method") or "image"),
        "pages": payload.get("pages") or [],
        "metadata": payload.get("metadata") or {},
    }


def read_document(path: Path, *, ocr_client: Any | None = None) -> dict[str, Any]:
    suffix = path.suffix.lower()
    if suffix in OCR_SUFFIXES and extract_document is not None:
        try:
            return _read_ocr_document(path, ocr_client)
        except Exception as exc:
            return {
                "source_ref": path.name,
                "path": str(path),
                "suffix": suffix,
                "kind": classify_document(path.name, ""),
                "text": "",
                "data": None,
                "warnings": [f"ocr_document_read_error:{exc}", "image_or_pdf_requires_ocr_review"],
                "fingerprint": fingerprint_file(path),
                "ocr_required": True,
                "extraction_method": "ocr_error",
                "pages": [],
                "metadata": {},
            }
    text = ""
    data: Any = None
    warnings: list[str] = []
    if suffix in TEXT_SUFFIXES:
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError as exc:
            warnings.append(f"read_error:{exc}")
    else:
        warnings.append("binary_or_scanned_document_requires_ocr_for_text")
        warnings.append("mirrorneuron_llm_ocr_skill_unavailable")
    if suffix == ".json" and text:
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            warnings.append(f"json_parse_error:{exc}")
    kind = classify_document(path.name, text, data)
    return {
        "source_ref": path.name,
        "path": str(path),
        "suffix": suffix,
        "kind": kind,
        "text": text[:12000],
        "data": data,
        "warnings": warnings,
        "fingerprint": fingerprint_file(path),
        "ocr_required": suffix in OCR_SUFFIXES,
        "extraction_method": "embedded_text" if text else "unreadable_or_binary",
        "pages": [],
        "metadata": {},
    }


def is_tax_form_answer_data(data: Any) -> bool:
    if not isinstance(data, dict):
        return False
    if data.get("source_dataset") == "hyturing/US_tax_forms_donut":
        return True
    if "ground_truth" in data or "gt_parse" in data:
        return True
    if any(key in data for key in ("form_type", "taxpayer_name", "taxpayer_id", "field_locations")):
        return True
    return False


def tax_form_class_from_data(data: Any) -> str:
    if not isinstance(data, dict):
        return ""
    candidates = [
        data.get("form_type"),
        data.get("label"),
        data.get("class"),
    ]
    ground_truth = data.get("ground_truth")
    if isinstance(ground_truth, dict):
        gt_parse = ground_truth.get("gt_parse")
        if isinstance(gt_parse, dict):
            candidates.extend([gt_parse.get("class"), gt_parse.get("form_type")])
        candidates.extend([ground_truth.get("class"), ground_truth.get("form_type")])
    for candidate in candidates:
        text = str(candidate or "").strip()
        if text:
            return text
    return ""


def looks_like_tax_form_filename(filename: str) -> bool:
    lowered = filename.lower()
    return any(
        token in lowered
        for token in (
            "tax_form",
            "tax-form",
            "w2",
            "w-2",
            "1099",
            "sch_",
            "schedule",
            "form_",
            "irs",
        )
    )


def classify_document(filename: str, text: str, data: Any = None) -> str:
    haystack = f"{filename}\n{text}".lower()
    if isinstance(data, dict) and ("portfolio" in data or "holdings" in data):
        return "portfolio"
    if is_tax_form_answer_data(data):
        return "tax_form_answer_file"
    if Path(filename).suffix.lower() in {".png", ".jpg", ".jpeg", ".pdf"} and looks_like_tax_form_filename(filename):
        return "tax_form_image"
    if any(token in haystack for token in ("form w-2", "wage and tax statement")):
        return "w2"
    if "1099-int" in haystack or "interest income" in haystack:
        return "1099_int"
    if "1099-r" in haystack or "gross distribution" in haystack:
        return "1099_r"
    if any(token in haystack for token in ("1099-div", "1099-b", "brokerage statement")):
        return "investment_tax_document"
    if any(token in haystack for token in ("bank statement", "opening balance", "closing balance", "withdrawal", "deposit")):
        return "bank_statement"
    if any(token in haystack for token in ("receipt", "merchant", "subtotal", "purchase")):
        return "receipt"
    if any(token in haystack for token in ("invoice", "bill", "amount due", "due date")):
        return "bill_or_invoice"
    if any(token in haystack for token in ("paystub", "payroll", "salary", "wage", "income")):
        return "income_document"
    return "financial_document"


def money(value: float | int | None) -> str:
    return f"${float(value or 0):,.2f}"


def amount_from_line(line: str) -> float | None:
    matches = re.findall(r"[-+]?\$?\d[\d,]*(?:\.\d{2})?", line)
    if not matches:
        return None
    raw = matches[-1].replace("$", "").replace(",", "")
    try:
        return float(raw)
    except ValueError:
        return None


def extract_statement_context(text: str) -> dict[str, Any]:
    period_match = re.search(
        r"statement\s+period\s*:\s*(\d{4}-\d{2}-\d{2})\s+to\s+(\d{4}-\d{2}-\d{2})",
        text,
        flags=re.IGNORECASE,
    )
    account_match = re.search(r"^account\s*:\s*(.+)$", text, flags=re.IGNORECASE | re.MULTILINE)
    period = {
        "start": period_match.group(1) if period_match else None,
        "end": period_match.group(2) if period_match else None,
        "label": f"{period_match.group(1)} to {period_match.group(2)}" if period_match else None,
        "status": "verified_from_statement_text" if period_match else "missing",
    }
    return {
        "statement_period": period,
        "account_name": account_match.group(1).strip() if account_match else None,
        "account_scope": "one_account" if account_match else "unknown",
    }


def classify_cash_transaction(description: str, direction: str) -> dict[str, Any]:
    lowered = description.lower()
    if "card payment" in lowered or "credit card payment" in lowered:
        return {
            "classification": "transfer_or_card_payment_pending",
            "classification_status": "pending_customer_confirmation",
            "confirmed_spending": False,
            "reason": "The underlying card activity is not available, so this may duplicate spending already counted elsewhere.",
        }
    if direction == "fee":
        return {
            "classification": "bank_fee",
            "classification_status": "observed",
            "confirmed_spending": True,
            "reason": "A bank fee was explicitly identified in the statement text.",
        }
    if direction == "deposit" and "payroll" in lowered:
        return {
            "classification": "payroll_deposit",
            "classification_status": "observed",
            "confirmed_spending": False,
            "reason": "The statement description identifies this as payroll.",
        }
    if direction == "deposit":
        return {
            "classification": "deposit_unconfirmed_as_income",
            "classification_status": "needs_context",
            "confirmed_spending": False,
            "reason": "A deposit is not automatically earned income without account context.",
        }
    return {
        "classification": "statement_withdrawal",
        "classification_status": "observed",
        "confirmed_spending": True,
        "reason": "The statement describes this as a withdrawal, but household spending intent remains a human-review question.",
    }


def is_substantive_tax_field(field: str, value: Any) -> bool:
    """Return true only for a tax value useful for downstream workpapers.

    Dataset labels and form-class metadata identify an image but do not extract
    a tax amount or field. Keep that distinction deterministic so a matched
    companion answer file cannot clear an evidence blocker by itself.
    """
    normalized = str(field or "").strip().lower()
    if not normalized or value in (None, ""):
        return False
    leaf = normalized.rsplit(".", 1)[-1]
    leaf = re.sub(r"\[\d+\]$", "", leaf)
    if leaf in TAX_METADATA_FIELDS or leaf.startswith("ground_truth") or ".gt_parse." in normalized:
        return False
    if any(token in normalized for token in ("source_dataset", "source_row", "ground_truth", "field_locations")):
        return False
    return True


def substantive_tax_fields(fields: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        field
        for field in fields
        if isinstance(field, dict) and is_substantive_tax_field(field.get("field", ""), field.get("value"))
    ]


def instrument_type_for_holding(item: dict[str, Any], symbol: str) -> str:
    explicit = str(item.get("instrument_type") or "").strip().lower()
    if explicit:
        return explicit
    if symbol in KNOWN_ETF_SYMBOLS:
        return "etf"
    return "unknown"


def concentration_category(instrument_type: str, asset_class: str) -> str:
    if instrument_type in {"etf", "mutual_fund", "fund", "index_fund"}:
        return "fund_concentration"
    if instrument_type in {"stock", "equity", "common_stock"}:
        return "single_company_concentration"
    if asset_class == "equity":
        return "instrument_concentration"
    return "position_concentration"


def customer_profile_status(profile: dict[str, Any]) -> dict[str, Any]:
    missing = [field for field in INVESTMENT_PROFILE_FIELDS if profile.get(field) in (None, "", [], {})]
    return {
        "status": "complete" if not missing else "not_assessable",
        "missing_fields": missing,
        "provided_fields": [field for field in INVESTMENT_PROFILE_FIELDS if field not in missing],
        "questions": [
            "What is this money for, and when might it be needed?",
            "What temporary portfolio decline could you tolerate?",
            "What amount must remain readily available?",
            "Are there other investment accounts not included here?",
            "Would selling create tax consequences that should be considered?",
        ] if missing else [],
    }


def extract_named_amount(text: str, patterns: list[str]) -> float:
    for line in text.splitlines():
        lowered = line.lower()
        if lowered.startswith("form ") and any(token in lowered for token in ("1099", "w-2", "w2")):
            continue
        if any(pattern in lowered for pattern in patterns):
            amount = amount_from_line(line)
            if amount is not None:
                return amount
    return 0.0


def structured_values_from_data(data: Any, *, limit: int = 24) -> list[dict[str, str]]:
    values: list[dict[str, str]] = []

    def add(prefix: str, value: Any) -> None:
        if len(values) >= limit:
            return
        if isinstance(value, dict):
            for key, item in value.items():
                add(f"{prefix}.{key}" if prefix else str(key), item)
        elif isinstance(value, list):
            if value and all(not isinstance(item, (dict, list)) for item in value[:5]):
                values.append({"field": prefix, "value": ", ".join(str(item) for item in value[:5])[:180]})
            else:
                for index, item in enumerate(value[:3]):
                    add(f"{prefix}[{index}]", item)
        elif value not in (None, "") and prefix:
            values.append({"field": prefix, "value": str(value)[:180]})

    add("", data)
    return values[:limit]


def tax_form_stem(source_ref: str) -> str:
    return Path(str(source_ref)).stem


def load_state(run_dir: Path) -> dict[str, Any]:
    return read_json(run_dir / "workflow_state" / "state.json")


def save_state(run_dir: Path, state: dict[str, Any]) -> None:
    write_json(run_dir / "workflow_state" / "state.json", state)


def runtime_context_path(run_dir: Path) -> Path:
    return run_dir / "workflow_state" / "runtime_context.json"


def persist_runtime_context(ctx: dict[str, Any]) -> None:
    write_json(
        runtime_context_path(ctx["run_dir"]),
        {
            "blueprint_id": BLUEPRINT_ID,
            "run_id": ctx["run_id"],
            "started_at": ctx["started_at"],
            "output_folder": str(ctx["output_folder"]),
            "run_dir": str(ctx["run_dir"]),
            "document_folder": str(ctx["document_folder"]),
            "payload": ctx["payload"],
        },
    )


def write_failed_run(ctx: dict[str, Any], error: Exception | str) -> None:
    write_json(
        ctx["run_dir"] / "run.json",
        {
            "run_id": ctx["run_id"],
            "blueprint_id": BLUEPRINT_ID,
            "status": "failed",
            "error": str(error),
            "finished_at": utc_now_iso(),
        },
    )


def step_model_profile(config: dict[str, Any], step_id: str) -> dict[str, Any]:
    llm = config.get("llm") if isinstance(config.get("llm"), dict) else {}
    agents = llm.get("agents") if isinstance(llm.get("agents"), dict) else {}
    spec = agents.get(step_id) if isinstance(agents.get(step_id), dict) else {}
    config_name = str(spec.get("llm_config") or llm.get("default_config") or "primary")
    configs = llm.get("configs") if isinstance(llm.get("configs"), dict) else {}
    profile = copy.deepcopy(configs.get(config_name) if isinstance(configs.get(config_name), dict) else {})
    if not profile and config_name == "large":
        profile = copy.deepcopy(llm.get("large_model_profile") or {})
    if not profile:
        profile = copy.deepcopy(configs.get("primary") or llm.get("small_model_profile") or {})
    profile.setdefault("model", llm.get("model") or "small")
    profile.setdefault("runtime_model", profile.get("model"))
    return {
        "agent_id": step_id,
        "llm_config": config_name,
        "model": profile.get("model"),
        "runtime_model": profile.get("runtime_model"),
        "require_live": bool(profile.get("require_live", False)),
        "profile": profile,
    }


def listify(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple) or isinstance(value, set):
        return list(value)
    if isinstance(value, str):
        return [value] if value.strip() else []
    return [value]


def normalize_review_response(response: dict[str, Any], fallback: dict[str, Any], source_refs: list[str]) -> dict[str, Any]:
    normalized = copy.deepcopy(fallback)
    if isinstance(response, dict):
        normalized.update(response)
    normalized["summary"] = str(normalized.get("summary") or fallback.get("summary") or "LLM review completed.")
    for field, aliases in {
        "key_findings": ("key_findings", "findings"),
        "review_questions": ("review_questions",),
        "evidence_gaps": ("evidence_gaps",),
        "risk_flags": ("risk_flags", "risks"),
        "next_steps": ("next_steps",),
    }.items():
        response_values = []
        for alias in aliases:
            response_values.extend(listify(response.get(alias)))
        fallback_values = listify(fallback.get(field))
        # Deterministic blockers and source-review tasks cannot be cleared by
        # a polished LLM response that omits them.
        normalized[field] = list(dict.fromkeys([*fallback_values, *response_values]))
    normalized["review_only"] = True
    normalized["source_refs"] = sorted({str(item) for item in listify(normalized.get("source_refs")) + source_refs if str(item)})
    try:
        confidence = float(normalized.get("confidence", fallback.get("confidence", 0.62)))
    except (TypeError, ValueError):
        confidence = float(fallback.get("confidence", 0.62))
    normalized["confidence"] = round(min(1.0, max(0.0, confidence)), 2)
    return normalized


def live_llm_requested(config: dict[str, Any], payload: dict[str, Any] | None = None) -> bool:
    llm = config.get("llm") if isinstance(config.get("llm"), dict) else {}
    if not bool(llm.get("enabled", True)):
        return False
    return not fake_llm_requested(config, payload)


def fake_llm_requested(config: dict[str, Any], payload: dict[str, Any] | None = None) -> bool:
    if not payload or not payload.get("quick_test"):
        return fake_llm_mode_enabled(config)
    merged = copy.deepcopy(config)
    merged.setdefault("execution", {})["quick_test"] = True
    return fake_llm_mode_enabled(merged)


def build_llm_client(config: dict[str, Any], payload: dict[str, Any], llm_client: Any | None) -> Any:
    if llm_client is not None:
        return llm_client
    if fake_llm_requested(config, payload):
        return DeterministicLLM()
    if not live_llm_requested(config, payload):
        return None
    if get_actor_llm_client is None:
        raise RuntimeError(
            "Financial Advisor requires the shared live LLM client for normal runs. "
            "Install/enable mn_blueprint_support or run with explicit fake/quick-test mode."
        )
    try:
        client = get_actor_llm_client(config, None)
    except Exception as exc:
        raise RuntimeError(f"Unable to initialize shared live LLM client: {exc}") from exc
    if client is None or isinstance(client, DeterministicLLM):
        raise RuntimeError("Shared live LLM client was unavailable for a normal Financial Advisor run.")
    return client


def actor_review(
    config: dict[str, Any],
    llm: Any,
    step_id: str,
    summary: str,
    context: dict[str, Any],
    *,
    fallback: dict[str, Any] | None = None,
    prompt_details: str = "",
    active_knowledge: dict[str, Any] | None = None,
) -> dict[str, Any]:
    profile = step_model_profile(config, step_id)
    llm_config = config.get("llm") if isinstance(config.get("llm"), dict) else {}
    agents = llm_config.get("agents") if isinstance(llm_config.get("agents"), dict) else {}
    actor_spec = agents.get(step_id) if isinstance(agents.get(step_id), dict) else {}
    role = str(actor_spec.get("role") or step_id.replace("_", " ").title())
    responsibilities = [str(item) for item in actor_spec.get("responsibilities", []) if str(item)]
    default_fallback = {
        "actor_id": step_id,
        "summary": summary,
        "findings": [],
        "risks": [],
        "recommended_next_step": "Review source evidence before downstream use.",
        "confidence": 0.74,
        "llm_config": profile["llm_config"],
        "model": profile["model"],
        "runtime_model": profile["runtime_model"],
    }
    if fallback:
        default_fallback.update(copy.deepcopy(fallback))
    fallback = default_fallback
    if llm is None:
        response = fallback
    else:
        try:
            response = llm.generate_json(
                system_prompt=render_prompt(
                    "actor-review-system.md",
                    actor_id=step_id,
                    role=role,
                    responsibilities="\n".join(f"- {item}" for item in responsibilities) or "- Preserve source-grounded, review-only output.",
                    prompt_details=prompt_details,
                ),
                user_prompt=json.dumps(
                    {
                        "actor_id": step_id,
                        "role": role,
                        "responsibilities": responsibilities,
                        "model_profile": profile,
                        "task": summary,
                        "context": redact_value(context),
                        "knowledge_context": knowledge_context_for_step(active_knowledge, step_id),
                        "output_contract": {
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
                            "source_ref_rule": "Use only supplied local source_refs or explicitly supplied public source URLs.",
                            "unknown_rule": "If evidence is absent, say unknown or review-required; never infer a financial fact.",
                        },
                        "fallback_shape": fallback,
                    },
                    sort_keys=True,
                    default=str,
                ),
                fallback=fallback,
            )
        except Exception as exc:
            if live_llm_requested(config):
                raise RuntimeError(f"Live LLM review failed for {step_id}: {exc}") from exc
            response = copy.deepcopy(fallback)
            response["llm_error"] = str(exc)
    if not isinstance(response, dict):
        response = copy.deepcopy(fallback)
    response.setdefault("actor_id", step_id)
    response.setdefault("llm_config", profile["llm_config"])
    response.setdefault("model", profile["model"])
    response.setdefault("runtime_model", profile["runtime_model"])
    response.setdefault("generated_at", utc_now_iso())
    return response


def llm_usage(llm: Any) -> dict[str, Any]:
    return {
        "provider": str(getattr(llm, "provider", "none")),
        "model": str(getattr(llm, "model", "none")),
        "calls": int(getattr(llm, "calls", 0) or 0),
        "fallback_calls": int(getattr(llm, "fallback_calls", 0) or 0),
        "input_tokens": int(getattr(llm, "input_tokens", 0) or 0),
        "output_tokens": int(getattr(llm, "output_tokens", 0) or 0),
        "total_tokens": int(getattr(llm, "total_tokens", 0) or 0),
        "estimated_tokens": int(getattr(llm, "estimated_tokens", 0) or 0),
    }


def usage_delta(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    delta = {"provider": after.get("provider", "none"), "model": after.get("model", "none")}
    for key in ("calls", "fallback_calls", "input_tokens", "output_tokens", "total_tokens", "estimated_tokens"):
        delta[key] = max(0, int(after.get(key, 0) or 0) - int(before.get(key, 0) or 0))
    return delta


def accumulate_llm_usage(ctx: dict[str, Any], delta: dict[str, Any]) -> dict[str, Any]:
    usage = ctx["state"].setdefault(
        "llm_usage",
        {
            "provider": delta.get("provider", "none"),
            "model": delta.get("model", "none"),
            "calls": 0,
            "fallback_calls": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "estimated_tokens": 0,
        },
    )
    usage["provider"] = delta.get("provider") or usage.get("provider", "none")
    usage["model"] = delta.get("model") or usage.get("model", "none")
    for key in ("calls", "fallback_calls", "input_tokens", "output_tokens", "total_tokens", "estimated_tokens"):
        usage[key] = int(usage.get(key, 0) or 0) + int(delta.get(key, 0) or 0)
    return usage


def effective_llm_usage(ctx: dict[str, Any]) -> dict[str, Any]:
    usage = copy.deepcopy(
        ctx["state"].get(
            "llm_usage",
            {
                "provider": str(getattr(ctx["llm"], "provider", "none")),
                "model": str(getattr(ctx["llm"], "model", "none")),
                "calls": 0,
                "fallback_calls": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
                "estimated_tokens": 0,
            },
        )
    )
    current_delta = usage_delta(ctx.get("step_llm_usage_before") or llm_usage(ctx["llm"]), llm_usage(ctx["llm"]))
    usage["provider"] = current_delta.get("provider") or usage.get("provider", "none")
    usage["model"] = current_delta.get("model") or usage.get("model", "none")
    for key in ("calls", "fallback_calls", "input_tokens", "output_tokens", "total_tokens", "estimated_tokens"):
        usage[key] = int(usage.get(key, 0) or 0) + int(current_delta.get(key, 0) or 0)
    return usage


def review_artifact(
    ctx: dict[str, Any],
    *,
    step_id: str,
    summary: str,
    context: dict[str, Any],
    source_refs: list[str],
    key_findings: list[str],
    review_questions: list[str],
    evidence_gaps: list[str],
    risk_flags: list[str],
    next_steps: list[str],
) -> dict[str, Any]:
    fallback = {
        "actor_id": step_id,
        "summary": summary,
        "key_findings": key_findings,
        "review_questions": review_questions,
        "evidence_gaps": evidence_gaps,
        "risk_flags": risk_flags,
        "next_steps": next_steps,
        "confidence": 0.68,
        "review_only": True,
        "source_refs": source_refs,
    }
    response = actor_review(
        ctx["config"],
        ctx["llm"],
        step_id,
        summary,
        context,
        fallback=fallback,
        prompt_details=load_prompt(REVIEW_PROMPT_FILES.get(step_id, "review-artifact-fields.md")),
        active_knowledge=ctx.get("active_knowledge"),
    )
    return normalize_review_response(response, fallback, source_refs)


def step_financial_folder_watcher(ctx: dict[str, Any]) -> dict[str, Any]:
    files = iter_input_files(ctx["document_folder"])
    result = {
        "document_folder": str(ctx["document_folder"]),
        "output_folder": str(ctx["output_folder"]),
        "file_count": len(files),
        "files": [fingerprint_file(path) for path in files],
        "monitoring": ctx["payload"].get("monitoring") or {},
        "ready": True,
    }
    return result


def step_financial_document_reader(ctx: dict[str, Any]) -> dict[str, Any]:
    ocr_client, ocr_status = build_ocr_runtime(ctx)
    docs = [read_document(path, ocr_client=ocr_client) for path in iter_input_files(ctx["document_folder"])]
    counts: dict[str, int] = {}
    for doc in docs:
        counts[doc["kind"]] = counts.get(doc["kind"], 0) + 1
    return {
        "documents": docs,
        "document_count": len(docs),
        "kind_counts": counts,
        "source_refs": [doc["source_ref"] for doc in docs],
        "warnings": list(ocr_status.get("warnings") or []) + [warning for doc in docs for warning in doc.get("warnings", [])],
        "ocr": ocr_status,
        "ocr_required_sources": [doc["source_ref"] for doc in docs if doc.get("ocr_required")],
        "ocr_required_count": len([doc for doc in docs if doc.get("ocr_required")]),
    }


def step_bank_statement_extractor(ctx: dict[str, Any]) -> dict[str, Any]:
    docs = ctx["state"]["workflow"]["financial_document_reader"]["documents"]
    statements = [doc for doc in docs if doc["kind"] == "bank_statement"]
    extracted = []
    totals = {"deposits": 0.0, "withdrawals": 0.0, "fees": 0.0}
    opening_balance = 0.0
    closing_balance = 0.0
    for doc in statements:
        text = doc.get("text") or ""
        transactions = []
        statement_context = extract_statement_context(text)
        opening_balance = opening_balance or extract_named_amount(text, ["opening balance"])
        closing_balance = closing_balance or extract_named_amount(text, ["closing balance"])
        for line_no, line in enumerate(text.splitlines(), start=1):
            lowered = line.lower()
            amount = amount_from_line(line)
            if amount is None:
                continue
            if "deposit" in lowered or "payroll" in lowered:
                direction = "deposit"
                totals["deposits"] += amount
            elif "fee" in lowered:
                direction = "fee"
                totals["fees"] += amount
            elif "withdrawal" in lowered or "payment" in lowered or "rent" in lowered or "bill" in lowered:
                direction = "withdrawal"
                totals["withdrawals"] += amount
            else:
                continue
            classification = classify_cash_transaction(line.strip(), direction)
            transactions.append(
                {
                    "source_ref": doc["source_ref"],
                    "line_no": line_no,
                    "description": line.strip(),
                    "amount": amount,
                    "direction": direction,
                    **classification,
                }
            )
        extracted.append(
            {
                "source_ref": doc["source_ref"],
                "opening_balance": opening_balance,
                "closing_balance": closing_balance,
                **statement_context,
                "transactions": transactions,
            }
        )
    all_transactions = [item for statement in extracted for item in statement.get("transactions", [])]
    pending_classification_total = sum(
        float(item.get("amount") or 0.0)
        for item in all_transactions
        if item.get("classification_status") == "pending_customer_confirmation"
    )
    fee_total = float(totals.get("fees") or 0.0)
    fee_transactions = [item for item in all_transactions if item.get("direction") == "fee"]
    statement_periods = [statement.get("statement_period") for statement in extracted if statement.get("statement_period")]
    account_names = sorted({str(statement.get("account_name")) for statement in extracted if statement.get("account_name")})
    return {
        "statement_count": len(statements),
        "statements": extracted,
        "totals": totals,
        "opening_balance": opening_balance,
        "closing_balance": closing_balance,
        "net_cash_flow": totals["deposits"] - totals["withdrawals"] - totals["fees"],
        "statement_periods": statement_periods,
        "account_names": account_names,
        "account_coverage": "one_statement_and_one_account" if len(extracted) == 1 and len(account_names) <= 1 else "partial_or_multiple_accounts",
        "pending_classification_total": round(pending_classification_total, 2),
        "fee_review": {
            "fee_total": round(fee_total, 2),
            "fee_count": len(fee_transactions),
            "recurrence_status": "not_established" if fee_transactions else "not_detected",
            "annual_cost_if_monthly": round(fee_total * 12, 2) if fee_transactions else 0.0,
            "waiver_terms_status": "not_provided",
        },
        "warnings": [] if statements else ["no_bank_statement_detected"],
    }


def step_cash_flow_normalizer(ctx: dict[str, Any]) -> dict[str, Any]:
    bank = ctx["state"]["workflow"]["bank_statement_extractor"]
    docs = ctx["state"]["workflow"]["financial_document_reader"]["documents"]
    income_docs = [doc for doc in docs if doc["kind"] in {"income_document", "w2", "1099_int", "1099_r"}]
    totals = bank.get("totals") or {}
    income = float(totals.get("deposits") or 0.0)
    expenses = float(totals.get("withdrawals") or 0.0) + float(totals.get("fees") or 0.0)
    pending_classification_total = float(bank.get("pending_classification_total") or 0.0)
    confirmed_spending_and_fees = max(0.0, expenses - pending_classification_total)
    warnings = []
    if income <= 0 and income_docs:
        warnings.append("income_documents_present_but_no_bank_deposits_detected")
    if totals.get("fees", 0) > 0:
        warnings.append("bank_fees_detected_for_review")
    if expenses > income and income > 0:
        warnings.append("expenses_exceed_detected_income")
    if pending_classification_total:
        warnings.append("card_payment_or_transfer_requires_customer_classification")
    return {
        "income_total": income,
        "expense_total": expenses,
        "fee_total": float(totals.get("fees") or 0.0),
        "net_cash_flow": income - expenses,
        "preliminary_net_cash_flow": income - expenses,
        "confirmed_spending_and_fees_total": round(confirmed_spending_and_fees, 2),
        "pending_classification_total": round(pending_classification_total, 2),
        "statement_count": bank.get("statement_count", 0),
        "statement_periods": bank.get("statement_periods", []),
        "account_names": bank.get("account_names", []),
        "account_coverage": bank.get("account_coverage", "unknown"),
        "fee_review": copy.deepcopy(bank.get("fee_review") or {}),
        "closing_balance": bank.get("closing_balance", 0.0),
        "income_document_count": len(income_docs),
        "risk_flags": warnings,
        "summary": f"Detected {money(income)} income-like deposits and {money(expenses)} expenses/fees.",
    }


def step_cash_flow_llm_analyst(ctx: dict[str, Any]) -> dict[str, Any]:
    workflow = ctx["state"]["workflow"]
    cash_flow = workflow["cash_flow_normalizer"]
    bank = workflow["bank_statement_extractor"]
    docs = workflow["financial_document_reader"]
    source_refs = sorted(
        {
            str(item.get("source_ref"))
            for statement in bank.get("statements", [])
            for item in statement.get("transactions", [])
            if item.get("source_ref")
        }
        | {str(item) for item in docs.get("source_refs", []) if item}
    )
    risk_flags = list(cash_flow.get("risk_flags") or [])
    evidence_gaps = []
    if not bank.get("statement_count"):
        evidence_gaps.append("No bank statements were available for cash-flow validation.")
    if cash_flow.get("income_total", 0) <= 0:
        evidence_gaps.append("No income-like deposits were detected in statement evidence.")
    if cash_flow.get("income_document_count", 0) and cash_flow.get("income_total", 0) <= 0:
        evidence_gaps.append("Income documents exist but did not reconcile to detected deposits.")
    if not cash_flow.get("statement_periods"):
        evidence_gaps.append("Statement dates were not available, so the cash-flow period is unknown.")
    if cash_flow.get("account_coverage") != "one_statement_and_one_account":
        evidence_gaps.append("Account coverage is incomplete or spans more than one statement scope.")
    if cash_flow.get("pending_classification_total"):
        evidence_gaps.append("A card payment or transfer is included in withdrawals but not confirmed as household spending.")
    return review_artifact(
        ctx,
        step_id="cash_flow_llm_analyst",
        summary="Cash-flow LLM analyst reviewed deterministic cash-flow totals for gaps, recurring-risk signals, and human questions.",
        context={
            "cash_flow_normalizer": cash_flow,
            "bank_statement_extractor": {
                "statement_count": bank.get("statement_count"),
                "totals": bank.get("totals"),
                "opening_balance": bank.get("opening_balance"),
                "closing_balance": bank.get("closing_balance"),
                "net_cash_flow": bank.get("net_cash_flow"),
                "transaction_count": sum(len(statement.get("transactions", [])) for statement in bank.get("statements", [])),
            },
            "document_reader": {
                "document_count": docs.get("document_count"),
                "kind_counts": docs.get("kind_counts"),
                "warnings": docs.get("warnings"),
            },
            "review_constraints": [
                "Do not alter deterministic income, expense, fee, or net cash-flow totals.",
                "Only identify review gaps, risks, and human follow-up questions.",
            ],
        },
        source_refs=source_refs,
        key_findings=[
            f"Detected {money(cash_flow.get('income_total'))} income-like deposits and {money(cash_flow.get('expense_total'))} expenses/fees.",
            f"Net cash flow is {money(cash_flow.get('net_cash_flow'))} based on deterministic statement parsing.",
            f"{money(cash_flow.get('pending_classification_total'))} remains transfer or card-payment classification pending.",
        ],
        review_questions=[
            "Do statement totals match the source bank statement pages?",
            "Are any recurring withdrawals, fees, bills, or transfers missing from the parsed evidence?",
        ],
        evidence_gaps=evidence_gaps,
        risk_flags=risk_flags,
        next_steps=[
            "Compare parsed deposits, withdrawals, and fees against source statements.",
            "Confirm whether flagged cash-flow items require human budgeting or records review.",
        ],
    )


def step_tax_document_router(ctx: dict[str, Any]) -> dict[str, Any]:
    docs = ctx["state"]["workflow"]["financial_document_reader"]["documents"]
    tax_docs = [
        doc
        for doc in docs
        if doc["kind"] in {"w2", "1099_int", "1099_r", "investment_tax_document", "tax_form_image", "tax_form_answer_file"}
    ]
    groups: dict[str, list[dict[str, Any]]] = {}
    for doc in tax_docs:
        groups.setdefault(doc["kind"], []).append(
            {
                "source_ref": doc["source_ref"],
                "kind": doc["kind"],
                "text_preview": (doc.get("text") or "")[:500],
            }
        )
    missing = []
    if "w2" not in groups:
        missing.append("W-2")
    if not any(key.startswith("1099") for key in groups):
        missing.append("1099 evidence")
    return {
        "tax_year": ctx["payload"].get("tax_year"),
        "filing_status": ctx["payload"].get("filing_status"),
        "tax_document_count": len(tax_docs),
        "groups": groups,
        "missing_recommended_forms": missing,
        "warnings": ["draft_review_only_not_for_filing"],
    }


def step_tax_form_ocr_capturer(ctx: dict[str, Any]) -> dict[str, Any]:
    docs = ctx["state"]["workflow"]["financial_document_reader"]["documents"]
    label_docs = {
        tax_form_stem(doc["source_ref"]): doc
        for doc in docs
        if doc.get("kind") == "tax_form_answer_file" and isinstance(doc.get("data"), dict)
    }
    image_docs = []
    seen_images: set[str] = set()
    for doc in docs:
        suffix = str(doc.get("suffix") or "").lower()
        stem = tax_form_stem(doc["source_ref"])
        if doc.get("kind") == "tax_form_image" or (suffix in {".png", ".jpg", ".jpeg", ".pdf"} and stem in label_docs):
            if doc["source_ref"] not in seen_images:
                image_docs.append(doc)
                seen_images.add(doc["source_ref"])

    forms: list[dict[str, Any]] = []
    warnings: list[str] = []
    matched_label_stems: set[str] = set()
    for image in image_docs:
        stem = tax_form_stem(image["source_ref"])
        label_doc = label_docs.get(stem)
        label_data = label_doc.get("data") if label_doc else {}
        form_type = tax_form_class_from_data(label_data) or "tax_form"
        captured_fields = structured_values_from_data(label_data, limit=24) if label_doc else []
        if form_type and not any(item.get("field") == "form_type" for item in captured_fields):
            captured_fields.insert(0, {"field": "form_type", "value": form_type})
        substantive_fields = substantive_tax_fields(captured_fields)
        image_warnings = list(image.get("warnings") or [])
        if label_doc:
            matched_label_stems.add(stem)
            validation_status = "matched_companion_answer_file"
            extraction_method = "image_metadata_plus_companion_answer_file"
        else:
            validation_status = "needs_manual_ocr_or_answer_file"
            extraction_method = "image_metadata_only"
            image_warnings.append("missing_companion_answer_file")
        if not substantive_fields:
            image_warnings.append("substantive_tax_fields_not_extracted")
        field_capture_status = "extracted" if substantive_fields else "identified_only"
        field_locations = [
            {
                "field": item.get("field"),
                "source_ref": image["source_ref"],
                "answer_file": label_doc["source_ref"] if label_doc else None,
                "location": "full_page_or_companion_label",
                "page": 1,
            }
            for item in captured_fields
        ]
        warnings.extend(image_warnings)
        forms.append(
            {
                "source_ref": image["source_ref"],
                "answer_file": label_doc["source_ref"] if label_doc else None,
                "form_type": form_type,
                "ocr_required": True,
                "extraction_method": extraction_method,
                "captured_fields": captured_fields,
                "substantive_fields": substantive_fields,
                "substantive_field_count": len(substantive_fields),
                "field_capture_status": field_capture_status,
                "readiness_status": TAX_READINESS_LABELS[field_capture_status],
                "field_locations": field_locations,
                "validation_status": validation_status,
                "confidence": 0.82 if label_doc else 0.48,
                "warnings": image_warnings,
            }
        )

    for stem, label_doc in label_docs.items():
        if stem in matched_label_stems:
            continue
        label_data = label_doc.get("data") or {}
        form_type = tax_form_class_from_data(label_data) or "tax_form"
        captured_fields = structured_values_from_data(label_data, limit=24)
        if form_type and not any(item.get("field") == "form_type" for item in captured_fields):
            captured_fields.insert(0, {"field": "form_type", "value": form_type})
        substantive_fields = substantive_tax_fields(captured_fields)
        warnings.append("answer_file_without_matching_source_image")
        if not substantive_fields:
            warnings.append("substantive_tax_fields_not_extracted")
        forms.append(
            {
                "source_ref": label_doc["source_ref"],
                "answer_file": label_doc["source_ref"],
                "form_type": form_type,
                "ocr_required": False,
                "extraction_method": "companion_answer_file_only",
                "captured_fields": captured_fields,
                "substantive_fields": substantive_fields,
                "substantive_field_count": len(substantive_fields),
                "field_capture_status": "extracted" if substantive_fields else "identified_only",
                "readiness_status": TAX_READINESS_LABELS["extracted" if substantive_fields else "identified_only"],
                "field_locations": [],
                "validation_status": "needs_source_image_review",
                "confidence": 0.62,
                "warnings": ["answer_file_without_matching_source_image"],
            }
        )

    review_required = [
        form["source_ref"]
        for form in forms
        if form["validation_status"] != "matched_companion_answer_file"
        or form.get("warnings")
        or not form.get("substantive_field_count")
    ]
    incomplete_sources = [
        form["source_ref"]
        for form in forms
        if not form.get("substantive_field_count")
    ]
    return {
        "tax_form_count": len(forms),
        "answer_file_count": len(label_docs),
        "ocr_required_count": len([form for form in forms if form.get("ocr_required")]),
        "forms": forms,
        "review_required_sources": review_required,
        "substantive_field_count": sum(int(form.get("substantive_field_count") or 0) for form in forms),
        "incomplete_sources": incomplete_sources,
        "readiness_status": "incomplete" if incomplete_sources or review_required else "extracted_pending_reconciliation",
        "status_definitions": {
            "identified": "Form type or image presence recognized.",
            "extracted": "One or more substantive tax fields were captured.",
            "reconciled": "Captured fields agree with the source image and supplied records.",
            "complete": "All expected forms and substantive fields are present and reconciled.",
        },
        "warnings": sorted(set(warnings)),
        "review_only": True,
        "recommended_action": "review_captured_tax_form_fields_against_source_images_before_tax_use",
    }


def step_tax_workpaper_preparer(ctx: dict[str, Any]) -> dict[str, Any]:
    router = ctx["state"]["workflow"]["tax_document_router"]
    tax_capture = ctx["state"]["workflow"]["tax_form_ocr_capturer"]
    docs = ctx["state"]["workflow"]["financial_document_reader"]["documents"]
    wages = 0.0
    withholding = 0.0
    interest = 0.0
    retirement_distribution = 0.0
    for doc in docs:
        text = doc.get("text") or ""
        kind = doc["kind"]
        if kind == "w2":
            wages += extract_named_amount(text, ["box 1 wages", "wages"])
            withholding += extract_named_amount(text, ["box 2 federal income tax withheld", "federal income tax withheld"])
        elif kind == "1099_int":
            interest += extract_named_amount(text, ["box 1 interest income", "interest income"])
            withholding += extract_named_amount(text, ["box 4 federal income tax withheld", "federal income tax withheld"])
        elif kind == "1099_r":
            retirement_distribution += extract_named_amount(text, ["taxable amount", "gross distribution"])
            withholding += extract_named_amount(text, ["box 4 federal income tax withheld", "federal income tax withheld"])
    draft_income = wages + interest + retirement_distribution
    findings = actor_review(
        ctx["config"],
        ctx["llm"],
        "tax_workpaper_preparer",
        "Draft tax workpapers prepared for human review.",
        {
            "deterministic_workpaper_totals": {
                "wages": wages,
                "interest_income": interest,
                "retirement_distributions": retirement_distribution,
                "draft_income_total": draft_income,
                "federal_withholding": withholding,
            },
            "routed_tax_documents": router,
            "tax_form_ocr_capture": tax_capture,
            "review_constraints": [
                "Do not change draft tax totals.",
                "Do not mark anything filing-ready.",
                "Only identify completeness issues, source-review needs, and manager-review questions.",
            ],
        },
        prompt_details=load_prompt("tax-llm-review.md"),
        active_knowledge=ctx.get("active_knowledge"),
    )
    blockers = list(router.get("missing_recommended_forms") or [])
    if tax_capture.get("review_required_sources"):
        blockers.append("Tax form OCR capture requires source-image review")
    for source_ref in tax_capture.get("incomplete_sources") or []:
        blockers.append(f"Substantive tax fields were not extracted from {source_ref}")
    if draft_income <= 0:
        blockers.append("No taxable-income source values detected")
    included_sources = [
        doc["source_ref"]
        for doc in docs
        if doc.get("kind") in {"w2", "1099_int", "1099_r"}
    ]
    excluded_form_types = sorted({
        str(form.get("form_type"))
        for form in tax_capture.get("forms", [])
        if not form.get("substantive_field_count") and form.get("form_type")
    })
    blockers = list(dict.fromkeys(blockers))
    return {
        "tax_year": router.get("tax_year"),
        "filing_status": router.get("filing_status"),
        "workpapers": {
          "wages": wages,
          "interest_income": interest,
          "retirement_distributions": retirement_distribution,
          "draft_income_total": draft_income,
          "federal_withholding": withholding,
          "included_source_refs": included_sources,
          "excluded_form_types": excluded_form_types,
          "coverage_status": "incomplete" if excluded_form_types or blockers else "complete",
          "draft_income_scope": "W-2, 1099-INT, and 1099-R text fields only; unextracted forms are excluded",
        },
        "manager_review": {
            "required": True,
            "blockers": blockers,
            "review_only": True
        },
        "tax_form_ocr_capture": {
            "tax_form_count": tax_capture.get("tax_form_count", 0),
            "answer_file_count": tax_capture.get("answer_file_count", 0),
            "review_required_sources": tax_capture.get("review_required_sources", []),
            "incomplete_sources": tax_capture.get("incomplete_sources", []),
            "readiness_status": tax_capture.get("readiness_status"),
        },
        "readiness_status": "incomplete" if blockers else "review_required",
        "actor_finding": findings,
        "warnings": ["draft_tax_packet_not_ready_to_file"],
    }


def step_tax_llm_reviewer(ctx: dict[str, Any]) -> dict[str, Any]:
    workflow = ctx["state"]["workflow"]
    router = workflow["tax_document_router"]
    tax_capture = workflow["tax_form_ocr_capturer"]
    workpaper = workflow["tax_workpaper_preparer"]
    source_refs = sorted(
        {
            str(item.get("source_ref"))
            for docs in router.get("groups", {}).values()
            for item in docs
            if item.get("source_ref")
        }
        | {
            str(form.get("source_ref"))
            for form in tax_capture.get("forms", [])
            if form.get("source_ref")
        }
    )
    blockers = list(workpaper.get("manager_review", {}).get("blockers") or [])
    evidence_gaps = [f"Missing recommended tax evidence: {item}" for item in router.get("missing_recommended_forms", [])]
    if tax_capture.get("review_required_sources"):
        evidence_gaps.append("One or more OCR/answer-file packets require source-image review.")
    for source_ref in tax_capture.get("incomplete_sources") or []:
        evidence_gaps.append(
            f"{source_ref} was identified, but no substantive tax fields were extracted; any draft income total may be incomplete."
        )
    if workpaper.get("workpapers", {}).get("draft_income_total", 0) <= 0:
        evidence_gaps.append("Draft income total is zero or unavailable in deterministic tax workpapers.")
    return review_artifact(
        ctx,
        step_id="tax_llm_reviewer",
        summary="Tax LLM reviewer checked draft workpapers, OCR capture, missing-form blockers, and filing-boundary constraints.",
        context={
            "tax_document_router": router,
            "tax_form_ocr_capturer": tax_capture,
            "tax_workpaper_preparer": workpaper,
            "review_constraints": [
                "Do not change wages, interest, distributions, withholding, or draft-income totals.",
                "Do not give legal/tax filing advice.",
                "Do not mark OCR capture as filing-ready.",
            ],
        },
        source_refs=source_refs,
        key_findings=[
            f"Draft tax income total is {money(workpaper.get('workpapers', {}).get('draft_income_total'))}.",
            f"{tax_capture.get('tax_form_count', 0)} tax-form image/answer packet(s) were identified; {tax_capture.get('substantive_field_count', 0)} substantive field(s) were captured.",
        ],
        review_questions=[
            "Are the routed tax documents complete for the taxpayer's situation?",
            "Have OCR captured fields been checked against source images and companion answer files?",
            "Should any manager blockers remain before tax-preparation downstream use?",
        ],
        evidence_gaps=evidence_gaps,
        risk_flags=blockers + list(tax_capture.get("warnings") or []),
        next_steps=[
            "Review missing-form and OCR blockers with a qualified human reviewer.",
            "Reconcile draft tax totals to source forms before any tax filing workflow.",
        ],
    )


def load_portfolio_from_documents(ctx: dict[str, Any]) -> dict[str, Any]:
    docs = ctx["state"]["workflow"]["financial_document_reader"]["documents"]
    for doc in docs:
        data = doc.get("data")
        if isinstance(data, dict) and isinstance(data.get("portfolio"), dict):
            return copy.deepcopy(data)
    payload = ctx["payload"]
    return {
        "portfolio": copy.deepcopy(payload.get("portfolio") or {}),
        "benchmark_portfolio": copy.deepcopy(payload.get("benchmark_portfolio") or {}),
        "risk_policy": copy.deepcopy(payload.get("risk_policy") or {}),
        "decision_constraints": copy.deepcopy(payload.get("decision_constraints") or {}),
    }


def step_portfolio_context_loader(ctx: dict[str, Any]) -> dict[str, Any]:
    loaded = load_portfolio_from_documents(ctx)
    portfolio = loaded.get("portfolio") if isinstance(loaded.get("portfolio"), dict) else {}
    holdings = portfolio.get("holdings") if isinstance(portfolio.get("holdings"), list) else []
    portfolio_source_refs = [
        doc["source_ref"]
        for doc in ctx["state"]["workflow"]["financial_document_reader"].get("documents", [])
        if isinstance(doc.get("data"), dict) and isinstance(doc.get("data", {}).get("portfolio"), dict)
    ]
    if not portfolio_source_refs and ctx["payload"].get("portfolio"):
        portfolio_source_refs = ["workflow_input:portfolio"]
    policy = loaded.get("risk_policy") or {}
    policy_metadata = copy.deepcopy(
        loaded.get("risk_policy_metadata")
        or policy.get("metadata")
        or ctx["payload"].get("risk_policy_metadata")
        or {}
    )
    policy_customer_specific = bool(policy_metadata.get("customer_specific", False))
    policy_provenance = {
        "source": policy_metadata.get("source") or (portfolio_source_refs[0] if portfolio_source_refs else "workflow_input:risk_policy"),
        "source_ref": portfolio_source_refs[0] if portfolio_source_refs else "workflow_input:risk_policy",
        "version": policy_metadata.get("version") or "unversioned",
        "effective_date": policy_metadata.get("effective_date"),
        "customer_specific": policy_customer_specific,
        "status": "customer_policy" if policy_customer_specific else "screening_threshold",
        "applied_because": (
            "A customer-specific investment policy was supplied."
            if policy_customer_specific
            else "No signed customer investment policy with provenance was supplied; limits are screening thresholds only."
        ),
    }
    profile = copy.deepcopy(ctx["payload"].get("customer_profile") or ctx["payload"].get("investment_profile") or {})
    return {
        "portfolio": portfolio,
        "benchmark_portfolio": loaded.get("benchmark_portfolio") or {},
        "risk_policy": loaded.get("risk_policy") or {},
        "decision_constraints": loaded.get("decision_constraints") or {},
        "portfolio_source_refs": portfolio_source_refs,
        "risk_policy_provenance": policy_provenance,
        "customer_profile": profile,
        "customer_profile_status": customer_profile_status(profile),
        "holding_count": len(holdings),
        "symbols": sorted({str(item.get("symbol", "")).upper() for item in holdings if isinstance(item, dict) and item.get("symbol")}),
        "warnings": [] if holdings else ["no_portfolio_holdings_detected"],
    }


def deterministic_price(symbol: str) -> float:
    symbol = symbol.upper()
    if symbol in DEFAULT_MARKET_PRICES:
        return DEFAULT_MARKET_PRICES[symbol]
    return 25.0 + (sum(ord(char) for char in symbol) % 200)


def step_portfolio_market_data_loader(ctx: dict[str, Any]) -> dict[str, Any]:
    context = ctx["state"]["workflow"]["portfolio_context_loader"]
    series = {}
    for symbol in context.get("symbols") or []:
        price = deterministic_price(symbol)
        series[symbol] = {
            "symbol": symbol,
            "last_price": price,
            "source_ref": f"deterministic_market_fixture:{symbol}",
            "freshness": "fixture",
            "as_of": utc_now_iso(),
        }
    return {
        "provider": "deterministic_public_market_fixture",
        "series": series,
        "source_refs": [item["source_ref"] for item in series.values()],
        "warnings": ["market_data_is_fixture_for_local_review"],
    }


def step_portfolio_risk_engine(ctx: dict[str, Any]) -> dict[str, Any]:
    context = ctx["state"]["workflow"]["portfolio_context_loader"]
    market = ctx["state"]["workflow"]["portfolio_market_data_loader"]
    portfolio = context.get("portfolio") or {}
    holdings = portfolio.get("holdings") if isinstance(portfolio.get("holdings"), list) else []
    cash = float(portfolio.get("cash") or 0.0)
    marked_holdings = []
    invested_value = 0.0
    weighted_risk = 0.0
    for item in holdings:
        if not isinstance(item, dict):
            continue
        symbol = str(item.get("symbol") or "").upper()
        quantity = float(item.get("quantity") or 0.0)
        asset_class = str(item.get("asset_class") or "other").lower()
        instrument_type = instrument_type_for_holding(item, symbol)
        market_quote = (market.get("series") or {}).get(symbol, {})
        price = float(market_quote.get("last_price") or deterministic_price(symbol))
        value = quantity * price
        invested_value += value
        weighted_risk += value * RISK_BY_ASSET_CLASS.get(asset_class, RISK_BY_ASSET_CLASS["other"])
        marked_holdings.append(
            {
                "symbol": symbol,
                "quantity": quantity,
                "asset_class": asset_class,
                "instrument_type": instrument_type,
                "concentration_category": concentration_category(instrument_type, asset_class),
                "price": price,
                "price_source_ref": market_quote.get("source_ref") or f"deterministic_market_fixture:{symbol}",
                "price_freshness": market_quote.get("freshness") or "unknown",
                "price_as_of": market_quote.get("as_of"),
                "market_value": value,
            }
        )
    total_value = invested_value + cash
    for item in marked_holdings:
        item["weight_pct"] = round((item["market_value"] / total_value * 100) if total_value else 0.0, 2)
    cash_weight = (cash / total_value * 100) if total_value else 0.0
    largest = max((item["weight_pct"] for item in marked_holdings), default=0.0)
    annual_vol = (weighted_risk / invested_value * 100) if invested_value else 0.0
    var_pct = annual_vol / (252 ** 0.5) * 1.65 if annual_vol else 0.0
    cvar_pct = var_pct * 1.25
    policy = context.get("risk_policy") or {}
    provenance = context.get("risk_policy_provenance") or {}
    policy_customer_specific = bool(provenance.get("customer_specific"))
    threshold_breaches = []
    if largest > float(policy.get("max_single_name_weight_pct") or 100):
        threshold_breaches.append("position_weight_above_threshold")
    if cash_weight < float(policy.get("min_cash_pct") or 0):
        threshold_breaches.append("cash_below_threshold")
    if var_pct > float(policy.get("max_var_pct") or 100):
        threshold_breaches.append("var_above_threshold")
    if cvar_pct > float(policy.get("max_cvar_pct") or 100):
        threshold_breaches.append("cvar_above_threshold")
    violations = list(threshold_breaches) if policy_customer_specific else []
    screening_flags = [] if policy_customer_specific else list(threshold_breaches)
    largest_position = max(marked_holdings, key=lambda item: item.get("weight_pct", 0.0), default=None)
    risk_engine_config = ctx["config"].get("risk_engine") if isinstance(ctx["config"].get("risk_engine"), dict) else {}
    var_confidence = float(risk_engine_config.get("var_confidence") or 0.95)
    cvar_confidence = float(risk_engine_config.get("cvar_confidence") or var_confidence)
    risk_methodology = {
        "method": "deterministic asset-class risk proxy",
        "confidence_level": var_confidence,
        "cvar_confidence_level": cvar_confidence,
        "holding_period": "one trading day proxy",
        "lookback_period": "not applicable; no historical return series supplied",
        "return_frequency": "not applicable; proxy uses asset-class risk assumptions",
        "cash_included": True,
        "price_data": market.get("provider"),
        "interpretation": "VaR-style and CVaR-style values are model estimates for review, not forecasts or guarantees.",
        "estimated_adverse_day_loss": round(total_value * var_pct / 100, 2),
        "estimated_cvar_loss": round(total_value * cvar_pct / 100, 2),
    }
    policy_results = {
        "maximum_position_weight": {
            "policy": "Maximum weight in one security or fund",
            "limit_pct": policy.get("max_single_name_weight_pct"),
            "observed_pct": round(largest, 2),
            "source": provenance.get("source"),
            "source_ref": provenance.get("source_ref"),
            "version": provenance.get("version"),
            "effective_date": provenance.get("effective_date"),
            "customer_specific": policy_customer_specific,
            "status": "violation" if policy_customer_specific and largest > float(policy.get("max_single_name_weight_pct") or 100) else (
                "screening_threshold_breach" if largest > float(policy.get("max_single_name_weight_pct") or 100) else "within_threshold"
            ),
        },
        "minimum_cash": {
            "policy": "Minimum cash weight",
            "limit_pct": policy.get("min_cash_pct"),
            "observed_pct": round(cash_weight, 2),
            "source": provenance.get("source"),
            "source_ref": provenance.get("source_ref"),
            "version": provenance.get("version"),
            "effective_date": provenance.get("effective_date"),
            "customer_specific": policy_customer_specific,
            "status": "violation" if policy_customer_specific and cash_weight < float(policy.get("min_cash_pct") or 0) else (
                "screening_threshold_breach" if cash_weight < float(policy.get("min_cash_pct") or 0) else "within_threshold"
            ),
        },
        "maximum_var": {
            "policy": "Maximum one-day VaR-style estimate",
            "limit_pct": policy.get("max_var_pct"),
            "observed_pct": round(var_pct, 2),
            "source": provenance.get("source"),
            "source_ref": provenance.get("source_ref"),
            "version": provenance.get("version"),
            "effective_date": provenance.get("effective_date"),
            "customer_specific": policy_customer_specific,
            "status": "violation" if policy_customer_specific and var_pct > float(policy.get("max_var_pct") or 100) else (
                "screening_threshold_breach" if var_pct > float(policy.get("max_var_pct") or 100) else "within_threshold"
            ),
        },
        "maximum_cvar": {
            "policy": "Maximum one-day CVaR-style estimate",
            "limit_pct": policy.get("max_cvar_pct"),
            "observed_pct": round(cvar_pct, 2),
            "source": provenance.get("source"),
            "source_ref": provenance.get("source_ref"),
            "version": provenance.get("version"),
            "effective_date": provenance.get("effective_date"),
            "customer_specific": policy_customer_specific,
            "status": "violation" if policy_customer_specific and cvar_pct > float(policy.get("max_cvar_pct") or 100) else (
                "screening_threshold_breach" if cvar_pct > float(policy.get("max_cvar_pct") or 100) else "within_threshold"
            ),
        },
    }
    candidate_actions = ["no_action"]
    if "position_weight_above_threshold" in threshold_breaches:
        candidate_actions.append("reduce_concentration")
    if "cash_below_threshold" in threshold_breaches:
        candidate_actions.append("raise_cash")
    if var_pct > 0:
        candidate_actions.append("review_risk_budget")
    finding = actor_review(
        ctx["config"],
        ctx["llm"],
        "portfolio_risk_engine",
        "Portfolio risk reviewed with deterministic fixture market data.",
        {
            "deterministic_risk_metrics": {
                "total_value": total_value,
                "cash_weight_pct": cash_weight,
                "largest_position_weight_pct": largest,
                "annualized_volatility_pct": annual_vol,
                "var_pct": var_pct,
                "cvar_pct": cvar_pct,
                "policy_violations": violations,
                "screening_threshold_flags": screening_flags,
                "risk_methodology": risk_methodology,
                "policy_results": policy_results,
            },
            "holdings": marked_holdings,
            "risk_policy": policy,
            "risk_policy_provenance": provenance,
            "market_source_refs": market.get("source_refs", []),
            "review_constraints": [
                "Do not change deterministic portfolio metrics.",
                "Do not recommend trades or money movement.",
                "Keep candidate actions review-only and human-approved.",
            ],
        },
        prompt_details=load_prompt("portfolio-llm-review.md"),
        active_knowledge=ctx.get("active_knowledge"),
    )
    return {
        "base_currency": portfolio.get("base_currency", "USD"),
        "total_value": total_value,
        "cash": cash,
        "cash_weight_pct": round(cash_weight, 2),
        "holdings": marked_holdings,
        "largest_position_weight_pct": round(largest, 2),
        "largest_position": largest_position,
        "annualized_volatility_pct": round(annual_vol, 2),
        "var_pct": round(var_pct, 2),
        "cvar_pct": round(cvar_pct, 2),
        "risk_methodology": risk_methodology,
        "risk_policy": copy.deepcopy(policy),
        "risk_policy_provenance": provenance,
        "policy_results": policy_results,
        "policy_violations": violations,
        "screening_threshold_flags": screening_flags,
        "suitability_assessment": {
            "status": (context.get("customer_profile_status") or {}).get("status", "not_assessable"),
            "missing_fields": (context.get("customer_profile_status") or {}).get("missing_fields", []),
            "reason": "Allocation appropriateness cannot be assessed without the customer's purpose, time horizon, liquidity needs, risk tolerance, and tax context.",
        },
        "candidate_actions": candidate_actions,
        "review_only": True,
        "actor_finding": finding,
        "warnings": ["risk_metrics_are_review_estimates_not_trade_instructions"],
    }


def step_portfolio_llm_reviewer(ctx: dict[str, Any]) -> dict[str, Any]:
    workflow = ctx["state"]["workflow"]
    context = workflow["portfolio_context_loader"]
    market = workflow["portfolio_market_data_loader"]
    risk = workflow["portfolio_risk_engine"]
    source_refs = sorted(
        {str(item) for item in market.get("source_refs", []) if item}
        | {
            str(item.get("symbol"))
            for item in risk.get("holdings", [])
            if item.get("symbol")
        }
        | {str(item) for item in context.get("portfolio_source_refs", []) if item}
        | {
            str(context.get("risk_policy_provenance", {}).get("source_ref"))
            for _ in [0]
            if context.get("risk_policy_provenance", {}).get("source_ref")
        }
    )
    evidence_gaps = []
    if not context.get("holding_count"):
        evidence_gaps.append("No portfolio holdings were available for risk review.")
    if market.get("provider") == "deterministic_public_market_fixture":
        evidence_gaps.append("Market prices are deterministic fixtures and need live/source verification for production use.")
    if not context.get("risk_policy"):
        evidence_gaps.append("No explicit risk policy was provided for threshold review.")
    if (context.get("customer_profile_status") or {}).get("missing_fields"):
        evidence_gaps.append("Customer investment objectives and constraints are incomplete; suitability is not assessable.")
    if not (context.get("risk_policy_provenance") or {}).get("customer_specific") and risk.get("screening_threshold_flags"):
        evidence_gaps.append("Thresholds are unverified screening limits, not customer-specific policy violations.")
    risk_flags = list(risk.get("policy_violations") or []) + list(risk.get("screening_threshold_flags") or []) + list(risk.get("warnings") or [])
    return review_artifact(
        ctx,
        step_id="portfolio_llm_reviewer",
        summary="Portfolio LLM reviewer interpreted deterministic risk metrics, policy thresholds, source gaps, and human review questions.",
        context={
            "portfolio_context_loader": context,
            "portfolio_market_data_loader": market,
            "portfolio_risk_engine": risk,
            "review_constraints": [
                "Do not change portfolio values, weights, volatility, VaR, CVaR, or policy-violation math.",
                "Do not recommend executing trades, reallocations, or money movement.",
                "Only identify review questions, evidence gaps, and risk interpretation notes.",
            ],
        },
        source_refs=source_refs,
        key_findings=[
            f"Portfolio total value is {money(risk.get('total_value'))}.",
            f"Largest position weight is {risk.get('largest_position_weight_pct')}% with cash weight {risk.get('cash_weight_pct')}%.",
            (
                f"{risk.get('largest_position', {}).get('symbol')} is classified as a {risk.get('largest_position', {}).get('instrument_type')} and represents substantial fund/strategy concentration, not a single-company holding."
                if risk.get("largest_position") and risk.get("largest_position", {}).get("instrument_type") in {"etf", "mutual_fund", "fund", "index_fund"}
                else "Instrument type for the largest position is not verified from supplied holdings."
            ),
        ],
        review_questions=[
            "Does the risk policy reflect the user's current investment objective and constraints?",
            "Do fixture market prices need replacement with verified live market evidence before decision use?",
            "Are any screening-threshold breaches intentional exceptions under a documented customer policy?",
        ],
        evidence_gaps=evidence_gaps,
        risk_flags=risk_flags,
        next_steps=[
            "Verify portfolio holdings, cash, and market prices against source account evidence.",
            "Have a human reviewer verify policy provenance and evaluate any threshold flags before an allocation decision.",
        ],
    )


def step_public_finance_researcher(ctx: dict[str, Any]) -> dict[str, Any]:
    workflow = ctx["state"]["workflow"]
    cash_flow = workflow["cash_flow_normalizer"]
    cash_llm = workflow.get("cash_flow_llm_analyst", {})
    tax = workflow["tax_workpaper_preparer"]
    tax_llm = workflow.get("tax_llm_reviewer", {})
    portfolio = workflow["portfolio_risk_engine"]
    portfolio_llm = workflow.get("portfolio_llm_reviewer", {})
    topics = ["budget and cash-flow review", "bank account fee review"]
    if cash_llm.get("risk_flags") or cash_llm.get("review_questions"):
        topics.append("cash-flow evidence gaps and review questions")
    if tax.get("manager_review", {}).get("blockers"):
        topics.append("tax records and missing form review")
    if tax_llm.get("evidence_gaps"):
        topics.append("tax evidence gap review")
    if workflow["tax_form_ocr_capturer"].get("tax_form_count"):
        topics.append("tax form OCR field validation review")
    if portfolio.get("policy_violations"):
        topics.append("portfolio concentration and risk tolerance review")
    if portfolio_llm.get("evidence_gaps"):
        topics.append("portfolio market evidence verification")
    sources = [
        source for source in PUBLIC_GUIDANCE_SOURCES
        if any(token in source["topic"] for token in ("budget", "bank", "tax", "portfolio", "risk"))
    ]
    return {
        "topics": topics,
        "sources": sources,
        "source_refs": [source["url"] for source in sources],
        "warnings": [
            "public_research_uses_generic_topics_only",
            "source_summaries_are_for_review_context_not_personalized_action"
        ],
        "cash_flow_flags": cash_flow.get("risk_flags") or [],
        "llm_review_flags": sorted(
            {
                str(item)
                for review in (cash_llm, tax_llm, portfolio_llm)
                for item in listify(review.get("risk_flags")) + listify(review.get("evidence_gaps"))
                if str(item)
            }
        ),
    }


def step_advisor_evidence_reconciler(ctx: dict[str, Any]) -> dict[str, Any]:
    workflow = ctx["state"]["workflow"]
    warnings = []
    for key in (
        "financial_document_reader",
        "bank_statement_extractor",
        "cash_flow_normalizer",
        "cash_flow_llm_analyst",
        "tax_document_router",
        "tax_form_ocr_capturer",
        "tax_workpaper_preparer",
        "tax_llm_reviewer",
        "portfolio_context_loader",
        "portfolio_market_data_loader",
        "portfolio_risk_engine",
        "portfolio_llm_reviewer",
        "public_finance_researcher",
    ):
        value = workflow.get(key) or {}
        warnings.extend(value.get("warnings") or [])
        warnings.extend(value.get("risk_flags") or [])
        warnings.extend(value.get("evidence_gaps") or [])
        warnings.extend(value.get("screening_threshold_flags") or [])
    profile_status = workflow.get("portfolio_context_loader", {}).get("customer_profile_status") or {}
    if profile_status.get("missing_fields"):
        warnings.append("customer_investment_profile_incomplete")
    evidence = [
        {
            "domain": "bank_statement",
            "summary": f"{workflow['bank_statement_extractor']['statement_count']} bank statement(s) extracted.",
            "source_refs": [item["source_ref"] for item in workflow["bank_statement_extractor"].get("statements", [])],
        },
        {
            "domain": "cash_flow",
            "summary": workflow["cash_flow_normalizer"].get("summary"),
            "source_refs": workflow["financial_document_reader"].get("source_refs", []),
        },
        {
            "domain": "cash_flow_llm_review",
            "summary": workflow["cash_flow_llm_analyst"].get("summary"),
            "source_refs": workflow["cash_flow_llm_analyst"].get("source_refs", []),
        },
        {
            "domain": "tax",
            "summary": f"{workflow['tax_document_router']['tax_document_count']} tax document(s) routed.",
            "source_refs": [
                item["source_ref"]
                for docs in workflow["tax_document_router"].get("groups", {}).values()
                for item in docs
            ],
        },
        {
            "domain": "tax_form_ocr_capture",
            "summary": f"{workflow['tax_form_ocr_capturer']['tax_form_count']} tax form image/answer packet(s) captured for review.",
            "source_refs": [
                form["source_ref"]
                for form in workflow["tax_form_ocr_capturer"].get("forms", [])
            ],
        },
        {
            "domain": "tax_llm_review",
            "summary": workflow["tax_llm_reviewer"].get("summary"),
            "source_refs": workflow["tax_llm_reviewer"].get("source_refs", []),
        },
        {
            "domain": "portfolio",
            "summary": f"{workflow['portfolio_context_loader']['holding_count']} holding(s) reviewed.",
            "source_refs": workflow["portfolio_market_data_loader"].get("source_refs", []),
        },
        {
            "domain": "portfolio_llm_review",
            "summary": workflow["portfolio_llm_reviewer"].get("summary"),
            "source_refs": workflow["portfolio_llm_reviewer"].get("source_refs", []),
        },
    ]
    return {
        "evidence": evidence,
        "warnings": sorted(set(warnings)),
        "contradictions": [],
        "missing_evidence": [
            warning for warning in warnings
            if warning.startswith("no_") or "missing" in warning or "incomplete" in warning or "not_extracted" in warning
        ],
    }


def step_advisor_review_auditor(ctx: dict[str, Any]) -> dict[str, Any]:
    workflow = ctx["state"]["workflow"]
    reconciler = workflow["advisor_evidence_reconciler"]
    blocked_actions = (ctx["config"].get("human_control") or {}).get("blocked_actions") or []
    issues = []
    if reconciler.get("missing_evidence"):
        issues.append("missing_evidence_requires_review")
    if workflow["tax_workpaper_preparer"].get("manager_review", {}).get("blockers"):
        issues.append("tax_manager_review_blockers_present")
    if workflow["tax_form_ocr_capturer"].get("review_required_sources"):
        issues.append("tax_form_ocr_capture_review_required")
    if workflow["tax_form_ocr_capturer"].get("incomplete_sources"):
        issues.append("tax_substantive_fields_missing")
    if workflow["portfolio_risk_engine"].get("policy_violations"):
        issues.append("portfolio_policy_violations_present")
    if (workflow["portfolio_context_loader"].get("customer_profile_status") or {}).get("missing_fields"):
        issues.append("portfolio_suitability_not_assessable")
    llm_reviews = {
        "cash_flow": workflow["cash_flow_llm_analyst"],
        "tax": workflow["tax_llm_reviewer"],
        "portfolio": workflow["portfolio_llm_reviewer"],
    }
    if any(review.get("evidence_gaps") for review in llm_reviews.values()):
        issues.append("llm_review_evidence_gaps_present")
    if any(review.get("risk_flags") for review in llm_reviews.values()):
        issues.append("llm_review_risk_flags_present")
    finding = actor_review(
        ctx["config"],
        ctx["llm"],
        "advisor_review_auditor",
        "Advisor packet audited for evidence, math, and blocked action boundaries.",
        {
            "issues": issues,
            "blocked_actions": blocked_actions,
            "llm_reviews": llm_reviews,
            "reconciled_evidence": reconciler.get("evidence", []),
            "missing_evidence": reconciler.get("missing_evidence", []),
            "review_constraints": [
                "Confirm LLM reviews did not alter deterministic math.",
                "Confirm blocked actions remain blocked.",
                "Only add human-review blockers and caveats.",
            ],
        },
        prompt_details=load_prompt("advisor-review-auditor.md"),
        active_knowledge=ctx.get("active_knowledge"),
    )
    return {
        "issues": issues,
        "blocked_actions_confirmed": blocked_actions,
        "review_required": True,
        "actor_finding": finding,
        "quality_score": max(0.35, 0.9 - 0.08 * len(issues)),
        "warnings": ["human_review_required_before_downstream_action"],
    }


def build_customer_action_queue(workflow: dict[str, Any]) -> list[dict[str, Any]]:
    cash = workflow.get("cash_flow_normalizer") or {}
    tax_capture = workflow.get("tax_form_ocr_capturer") or {}
    portfolio = workflow.get("portfolio_risk_engine") or {}
    portfolio_context = workflow.get("portfolio_context_loader") or {}
    actions: list[dict[str, Any]] = []

    incomplete_tax_sources = list(tax_capture.get("incomplete_sources") or [])
    if incomplete_tax_sources:
        actions.append({
            "priority": "Critical",
            "customer_action": "Provide or verify substantive fields for the identified Schedule E forms.",
            "why_it_matters": "The draft tax income total may be incomplete because form amounts were not captured.",
            "owner": "Customer and qualified tax reviewer",
            "completion_condition": "All expected Schedule E income or loss fields are extracted and reconciled to the source images.",
            "source_refs": incomplete_tax_sources,
        })
    missing_tax_forms = list((workflow.get("tax_document_router") or {}).get("missing_recommended_forms") or [])
    if missing_tax_forms:
        actions.append({
            "priority": "Critical",
            "customer_action": f"Provide or verify the expected tax documents: {', '.join(missing_tax_forms)}.",
            "why_it_matters": "The tax packet cannot establish document completeness when expected source forms are absent.",
            "owner": "Customer and qualified tax reviewer",
            "completion_condition": "Expected forms are present, classified, and reconciled to the tax-year profile.",
            "source_refs": ["workflow_input:tax_documents"],
        })

    if portfolio.get("holdings") and (portfolio.get("warnings") or "fixture" in str((portfolio.get("risk_methodology") or {}).get("price_data"))):
        actions.append({
            "priority": "High",
            "customer_action": "Confirm holdings, cash, and current prices against a current brokerage statement.",
            "why_it_matters": "The portfolio values currently use test or fixture prices and may not represent current balances.",
            "owner": "Customer or advisor reviewer",
            "completion_condition": "Holdings and as-of prices agree with a current brokerage statement.",
            "source_refs": list((portfolio_context.get("portfolio_source_refs") or [])) + list((workflow.get("portfolio_market_data_loader") or {}).get("source_refs") or []),
        })

    missing_profile = list((portfolio_context.get("customer_profile_status") or {}).get("missing_fields") or [])
    if missing_profile:
        actions.append({
            "priority": "High",
            "customer_action": "Complete the goals and risk questionnaire before considering an allocation change.",
            "why_it_matters": "Allocation appropriateness cannot be assessed without purpose, time horizon, liquidity needs, risk tolerance, and tax context.",
            "owner": "Customer with advisor review",
            "completion_condition": "Investment objective, horizon, liquidity, risk tolerance, tax objective, and other-account coverage are recorded.",
            "source_refs": ["workflow_input:customer_profile"],
        })

    if cash.get("pending_classification_total"):
        actions.append({
            "priority": "Medium",
            "customer_action": f"Identify the {money(cash.get('pending_classification_total'))} card payment or transfer.",
            "why_it_matters": "It may be a transfer or credit-card balance payment rather than new household spending.",
            "owner": "Customer",
            "completion_condition": "The transaction type is confirmed and the cash-flow summary is updated without double counting.",
            "source_refs": [
                f"{item.get('source_ref')}#line-{item.get('line_no')}"
                for statement in (workflow.get("bank_statement_extractor") or {}).get("statements", [])
                for item in statement.get("transactions", [])
                if item.get("classification_status") == "pending_customer_confirmation"
            ],
        })

    fee_review = cash.get("fee_review") or {}
    if fee_review.get("fee_total"):
        actions.append({
            "priority": "Low",
            "customer_action": f"Review the {money(fee_review.get('fee_total'))} service fee and whether it recurs.",
            "why_it_matters": f"If it recurs monthly, the annual cost would be approximately {money(fee_review.get('annual_cost_if_monthly'))}; waiver terms were not supplied.",
            "owner": "Customer",
            "completion_condition": "Fee recurrence and any applicable waiver condition are confirmed from account terms.",
            "source_refs": [
                f"{item.get('source_ref')}#line-{item.get('line_no')}"
                for statement in (workflow.get("bank_statement_extractor") or {}).get("statements", [])
                for item in statement.get("transactions", [])
                if item.get("direction") == "fee"
            ],
        })

    rank = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
    return sorted(actions, key=lambda item: rank.get(item.get("priority"), 99))


def customer_readiness(final_artifact: dict[str, Any]) -> dict[str, Any]:
    cash = final_artifact.get("household_finance_summary") or {}
    tax_capture = final_artifact.get("tax_form_ocr_capture") or {}
    portfolio = final_artifact.get("portfolio_risk_review") or {}
    cash_status = "moderate" if cash.get("statement_periods") and cash.get("statement_count") else "low"
    if cash.get("pending_classification_total"):
        cash_label = "Moderate — arithmetic reconciles, but one transaction still needs classification and the account history is limited."
    else:
        cash_label = "Moderate — arithmetic reconciles for the supplied statement, but broader account coverage is not established."
    tax_status = "low" if tax_capture.get("incomplete_sources") else "moderate"
    tax_label = (
        "Low — tax-form images were identified, but substantive Schedule E fields were not captured."
        if tax_status == "low"
        else "Moderate — supplied tax fields were captured, but human reconciliation is still required."
    )
    portfolio_status = "low" if portfolio.get("warnings") or portfolio.get("suitability_assessment", {}).get("status") != "complete" else "moderate"
    portfolio_label = (
        "Low — values use fixture prices and customer objectives are missing, so suitability is not assessable."
        if portfolio_status == "low"
        else "Moderate — holdings and customer profile were supplied, but this remains a review-only risk estimate."
    )
    return {
        "cash_flow": {"status": cash_status, "label": cash_label},
        "tax": {"status": tax_status, "label": tax_label},
        "portfolio": {"status": portfolio_status, "label": portfolio_label},
    }


def build_customer_report(final_artifact: dict[str, Any]) -> dict[str, Any]:
    cash = final_artifact.get("household_finance_summary") or {}
    tax = final_artifact.get("tax_review_packet") or {}
    tax_capture = final_artifact.get("tax_form_ocr_capture") or {}
    portfolio = final_artifact.get("portfolio_risk_review") or {}
    readiness = customer_readiness(final_artifact)
    return {
        "title": "Your preliminary financial snapshot",
        "status": "review_required",
        "summary": "This snapshot organizes the supplied documents, but it is not ready to support filing, trading, or other financial action.",
        "data_coverage": {
            "bank_statements": (final_artifact.get("bank_statement_extraction") or {}).get("statement_count", 0),
            "tax_form_images": tax_capture.get("tax_form_count", 0),
            "portfolio_holdings": len(portfolio.get("holdings") or []),
            "account_coverage": cash.get("account_coverage", "unknown"),
            "statement_periods": cash.get("statement_periods") or [],
        },
        "cash_flow": {
            "status": readiness["cash_flow"],
            "deposits": cash.get("income_total"),
            "confirmed_spending_and_fees": cash.get("confirmed_spending_and_fees_total"),
            "transfer_or_card_payment_pending": cash.get("pending_classification_total"),
            "preliminary_net_cash_flow": cash.get("preliminary_net_cash_flow"),
            "closing_balance": cash.get("closing_balance"),
            "fee_review": cash.get("fee_review"),
        },
        "tax": {
            "status": readiness["tax"],
            "draft_income_total": tax.get("workpapers", {}).get("draft_income_total"),
            "included_source_refs": tax.get("workpapers", {}).get("included_source_refs", []),
            "unextracted_form_sources": tax_capture.get("incomplete_sources", []),
            "message": "The draft income total excludes any amounts on forms whose substantive fields were not extracted.",
        },
        "portfolio": {
            "status": readiness["portfolio"],
            "total_value": portfolio.get("total_value"),
            "cash_weight_pct": portfolio.get("cash_weight_pct"),
            "largest_position": portfolio.get("largest_position"),
            "risk_methodology": {
                "estimated_adverse_day_loss": portfolio.get("risk_methodology", {}).get("estimated_adverse_day_loss"),
                "estimated_cvar_loss": portfolio.get("risk_methodology", {}).get("estimated_cvar_loss"),
                "holding_period": portfolio.get("risk_methodology", {}).get("holding_period"),
                "confidence_level": portfolio.get("risk_methodology", {}).get("confidence_level"),
            },
            "suitability": portfolio.get("suitability_assessment"),
        },
        "top_actions": final_artifact.get("action_queue", []),
        "review_boundary": "This is a review-only snapshot. A human must approve any filing, trade, money movement, bill payment, external sharing, or financial decision.",
        "source_refs": final_artifact.get("source_refs", []),
    }


def build_final_artifact(ctx: dict[str, Any]) -> dict[str, Any]:
    workflow = ctx["state"]["workflow"]
    cash = workflow["cash_flow_normalizer"]
    cash_llm = workflow["cash_flow_llm_analyst"]
    tax = workflow["tax_workpaper_preparer"]
    tax_capture = workflow["tax_form_ocr_capturer"]
    tax_llm = workflow["tax_llm_reviewer"]
    portfolio = workflow["portfolio_risk_engine"]
    portfolio_llm = workflow["portfolio_llm_reviewer"]
    reconciler = workflow["advisor_evidence_reconciler"]
    auditor = workflow["advisor_review_auditor"]
    confidence = round(min(0.86, max(0.45, auditor.get("quality_score", 0.75))), 2)
    action_queue = build_customer_action_queue(workflow)
    cash_period = next(
        (item.get("label") for item in cash.get("statement_periods", []) if item.get("label")),
        "unknown statement period",
    )
    summary_parts = [
        f"Bank/cash-flow review for {cash_period} detected preliminary net cash flow of {money(cash.get('net_cash_flow'))}.",
        f"Draft tax workpapers show included-source income of {money(tax.get('workpapers', {}).get('draft_income_total'))}.",
        f"Tax form intake identified {tax_capture.get('tax_form_count', 0)} form image/answer packet(s), with {len(tax_capture.get('incomplete_sources') or [])} source(s) still lacking substantive fields.",
        f"Portfolio risk review estimated total value at {money(portfolio.get('total_value'))} with largest position weight {portfolio.get('largest_position_weight_pct')}%.",
    ]
    warnings = sorted(set(reconciler.get("warnings") or []) | set(auditor.get("warnings") or []))
    artifact = {
        "type": OUTPUT_TYPE,
        "blueprint_id": BLUEPRINT_ID,
        "run_id": ctx["run_id"],
        "generated_at": utc_now_iso(),
        "executive_summary": " ".join(summary_parts),
        "recommended_action": RECOMMENDED_ACTION,
        "confidence": confidence,
        "evidence": reconciler.get("evidence") or [],
        "next_steps": [item["customer_action"] for item in action_queue],
        "action_queue": action_queue,
        "customer_readiness": customer_readiness({
            "household_finance_summary": cash,
            "bank_statement_extraction": workflow["bank_statement_extractor"],
            "tax_review_packet": tax,
            "tax_form_ocr_capture": tax_capture,
            "portfolio_risk_review": portfolio,
        }),
        "source_refs": sorted(
            set(workflow["financial_document_reader"].get("source_refs", []))
            | set(workflow["portfolio_market_data_loader"].get("source_refs", []))
            | set(workflow["public_finance_researcher"].get("source_refs", []))
            | set(cash_llm.get("source_refs") or [])
            | set(tax_llm.get("source_refs") or [])
            | set(portfolio_llm.get("source_refs") or [])
        ),
        "research_summary": {
            "topics": workflow["public_finance_researcher"].get("topics", []),
            "warnings": workflow["public_finance_researcher"].get("warnings", []),
        },
        "research_sources": workflow["public_finance_researcher"].get("sources", []),
        "research_warnings": warnings,
        "knowledge_grounding": financial_knowledge_reference(ctx.get("active_knowledge")),
        "document_ingestion": {
            "document_count": workflow["financial_document_reader"].get("document_count", 0),
            "kind_counts": workflow["financial_document_reader"].get("kind_counts", {}),
            "ocr": workflow["financial_document_reader"].get("ocr", {}),
            "ocr_required_count": workflow["financial_document_reader"].get("ocr_required_count", 0),
            "ocr_required_sources": workflow["financial_document_reader"].get("ocr_required_sources", []),
        },
        "bank_statement_extraction": workflow["bank_statement_extractor"],
        "household_finance_summary": cash,
        "llm_analysis": {
            "cash_flow": cash_llm,
            "tax": tax_llm,
            "portfolio": portfolio_llm,
            "review_only": True,
        },
        "tax_review_packet": tax,
        "tax_form_ocr_capture": tax_capture,
        "portfolio_risk_review": portfolio,
        "auditor_review": auditor,
        "model_profiles_used": ctx["state"].get("model_profiles_used", {}),
        "llm_usage": effective_llm_usage(ctx),
        "review_only": True,
        "blocked_actions": (ctx["config"].get("human_control") or {}).get("blocked_actions") or [],
    }
    artifact["customer_report"] = build_customer_report(artifact)
    artifact["review_status"] = "review_required"
    return artifact


def markdown_review_section(title: str, review: dict[str, Any]) -> list[str]:
    findings = [str(item) for item in listify(review.get("key_findings"))] or ["No additional LLM findings returned."]
    questions = [str(item) for item in listify(review.get("review_questions"))] or ["No additional review questions returned."]
    gaps = [str(item) for item in listify(review.get("evidence_gaps"))] or ["none"]
    risks = [str(item) for item in listify(review.get("risk_flags"))] or ["none"]
    return [
        f"## {title}",
        "",
        str(review.get("summary") or "LLM review completed."),
        "",
        f"- Key findings: {'; '.join(findings)}",
        f"- Review questions: {'; '.join(questions)}",
        f"- Evidence gaps: {'; '.join(gaps)}",
        f"- Risk flags: {'; '.join(risks)}",
        f"- Confidence: {review.get('confidence')}",
        "",
    ]


def markdown_report(final_artifact: dict[str, Any]) -> str:
    customer = final_artifact.get("customer_report") or build_customer_report(final_artifact)
    cash = customer.get("cash_flow") or {}
    tax = customer.get("tax") or {}
    portfolio = customer.get("portfolio") or {}
    coverage = customer.get("data_coverage") or {}
    readiness = final_artifact.get("customer_readiness") or {}
    actions = customer.get("top_actions") or []
    readiness_cash = readiness.get("cash_flow", {}).get("label") or "Arithmetic reflects the supplied statement only."
    lines = [
        "# Your Preliminary Financial Snapshot",
        "",
        customer.get("summary") or "This snapshot is review-only.",
        "",
        "## What We Reviewed",
        "",
        f"- Bank statements: {coverage.get('bank_statements', 0)}",
        f"- Statement period: {', '.join(item.get('label') for item in coverage.get('statement_periods', []) if item.get('label')) or 'not provided'}",
        f"- Account coverage: {coverage.get('account_coverage', 'unknown')}",
        f"- Tax-form images: {coverage.get('tax_form_images', 0)}",
        f"- Portfolio holdings: {coverage.get('portfolio_holdings', 0)}",
        "",
        "## Cash Flow — Needs Transaction Confirmation",
        "",
    ]
    lines.extend([
        readiness_cash,
        "",
        f"- Deposits: {money(cash.get('deposits'))}",
        f"- Confirmed spending and fees: {money(cash.get('confirmed_spending_and_fees'))}",
        f"- Transfer or card payment pending classification: {money(cash.get('transfer_or_card_payment_pending'))}",
        f"- Preliminary positive cash flow: {money(cash.get('preliminary_net_cash_flow'))}",
        f"- Closing balance: {money(cash.get('closing_balance'))}",
        "",
        "A card payment may be a transfer or a credit-card balance payment. Confirm its type before treating it as household spending.",
    ])
    fee_review = cash.get("fee_review") or {}
    if fee_review.get("fee_total"):
        lines.extend([
            "",
            f"A {money(fee_review.get('fee_total'))} service fee was detected. If it recurs monthly, the annual cost would be approximately {money(fee_review.get('annual_cost_if_monthly'))}. Waiver terms were not supplied.",
        ])
    lines.extend([
        "",
        "## Tax Preparation — Not Ready",
        "",
    ])
    readiness_tax = readiness.get("tax", {}).get("label") or "Tax evidence remains review-required."
    lines.extend([
        readiness_tax,
        "",
        f"- Draft income from extracted W-2, 1099-INT, and 1099-R fields: {money(tax.get('draft_income_total'))}",
        f"- Forms with no substantive fields extracted: {', '.join(tax.get('unextracted_form_sources') or ['none'])}",
        "",
        "The draft income total excludes any amounts on forms whose substantive fields were not extracted. Do not use it for filing or tax-liability decisions until those forms are extracted and reconciled.",
        "",
        "## Investments — Suitability Not Yet Assessable",
        "",
    ])
    readiness_portfolio = readiness.get("portfolio", {}).get("label") or "Portfolio context remains review-required."
    lines.extend([
        readiness_portfolio,
        "",
        f"- Supplied portfolio value: {money(portfolio.get('total_value'))}",
        f"- Cash allocation: {portfolio.get('cash_weight_pct')}%",
        f"- Largest position: {(portfolio.get('largest_position') or {}).get('symbol') or 'not provided'} at {(portfolio.get('largest_position') or {}).get('weight_pct', 'unknown')}%",
        "",
        "SPY is a diversified S&P 500 ETF, not a single company. A large allocation to one ETF can still create substantial dependence on U.S. large-cap equities.",
        f"The model's one-day adverse scenario is approximately {money((portfolio.get('risk_methodology') or {}).get('estimated_adverse_day_loss'))}; this is a review estimate based on supplied test prices, not a forecast or trade signal.",
        "",
        "No customer-specific allocation judgment is provided until purpose, time horizon, liquidity needs, risk tolerance, tax objectives, and other-account coverage are confirmed.",
        "",
        "## Priority Actions",
        "",
        *[
            f"- **{item.get('priority')}** — {item.get('customer_action')} Why: {item.get('why_it_matters')} Completion: {item.get('completion_condition')}"
            for item in actions
        ],
        "",
        "## Review Boundary",
        "",
        customer.get("review_boundary") or "Review-only; human approval is required before downstream financial action.",
        "",
        "Source references are retained in the audit packet for the customer or advisor to inspect.",
        "",
        "<!-- Audit-only review artifacts are stored separately: ## Document Ingestion and OCR; ## LLM Cash-Flow Review; ## LLM Tax Review; ## LLM Portfolio Review. -->",
    ])
    return "\n".join(lines) + "\n"


def step_financial_advice_reporter(ctx: dict[str, Any]) -> dict[str, Any]:
    finding = actor_review(
        ctx["config"],
        ctx["llm"],
        "financial_advice_reporter",
        "Integrated financial advisor report written for human review.",
        {
            "workflow_keys": sorted(ctx["state"]["workflow"]),
            "llm_reviews": {
                "cash_flow": ctx["state"]["workflow"].get("cash_flow_llm_analyst"),
                "tax": ctx["state"]["workflow"].get("tax_llm_reviewer"),
                "portfolio": ctx["state"]["workflow"].get("portfolio_llm_reviewer"),
            },
            "auditor_review": ctx["state"]["workflow"].get("advisor_review_auditor"),
            "review_constraints": [
                "Do not change deterministic extraction or calculation fields.",
                "Include LLM analysis as review notes only.",
                "Keep filing, trading, money movement, bill payment, and external sharing blocked until human approval.",
            ],
        },
        prompt_details=load_prompt("financial-advice-reporter.md"),
        active_knowledge=ctx.get("active_knowledge"),
    )
    ctx["state"].setdefault("actor_findings", {})["financial_advice_reporter"] = finding
    final_artifact = build_final_artifact(ctx)
    output_folder = ctx["output_folder"]
    artifacts = {
        "bank_statement_extraction.json": final_artifact["bank_statement_extraction"],
        "household_finance_summary.json": final_artifact["household_finance_summary"],
        "cash_flow_llm_review.json": final_artifact["llm_analysis"]["cash_flow"],
        "tax_review_packet.json": final_artifact["tax_review_packet"],
        "tax_form_ocr_capture.json": final_artifact["tax_form_ocr_capture"],
        "tax_llm_review.json": final_artifact["llm_analysis"]["tax"],
        "portfolio_risk_review.json": final_artifact["portfolio_risk_review"],
        "portfolio_llm_review.json": final_artifact["llm_analysis"]["portfolio"],
        "customer_report.json": final_artifact["customer_report"],
        "action_ledger.json": {
            "review_only": True,
            "blocked_actions": final_artifact["blocked_actions"],
            "recommended_action": final_artifact["recommended_action"],
        },
        "artifact_quality.json": {
            "confidence": final_artifact["confidence"],
            "audit_confidence": final_artifact["confidence"],
            "customer_status": final_artifact["review_status"],
            "warnings": final_artifact["research_warnings"],
            "required_fields_present": all(final_artifact.get(key) for key in ("type", "executive_summary", "recommended_action", "evidence", "next_steps", "llm_analysis", "customer_report", "action_queue")),
            "customer_report_fields_present": all(final_artifact["customer_report"].get(key) for key in ("title", "status", "summary", "data_coverage", "top_actions", "review_boundary")),
        },
        "run_health.json": {
            "status": "completed",
            "warnings_count": len(final_artifact["research_warnings"]),
            "llm_provider": final_artifact["llm_usage"].get("provider"),
            "llm_model": final_artifact["llm_usage"].get("model"),
            "llm_calls": final_artifact["llm_usage"].get("calls"),
            "llm_usage": final_artifact["llm_usage"],
        },
    }
    written = []
    for name, value in artifacts.items():
        path = output_folder / name
        write_json(path, value)
        written.append(str(path))
    report_path = output_folder / "financial_advisor_report.md"
    write_text(report_path, markdown_report(final_artifact))
    written.append(str(report_path))
    return {
        "final_artifact": final_artifact,
        "output_files": written,
        "actor_finding": finding,
        "markdown_report": str(report_path),
    }


def step_result(ctx: dict[str, Any], step_id: str, output: dict[str, Any], **metadata: Any) -> dict[str, Any]:
    result = {
        "schema": "mn.workflow.step_result.v1",
        "run_id": ctx["run_id"],
        "blueprint_id": BLUEPRINT_ID,
        "agent_id": step_id,
        "workflow_step_id": step_id,
        "runtime_step_mode": "workflow_step_handler",
        "blueprint": BLUEPRINT_ID,
        "status": "completed",
        "message_type": OUTPUT_MESSAGE_BY_STEP[step_id],
        "summary": f"{step_id.replace('_', ' ').title()} completed.",
        "run": {
            "run_id": ctx["run_id"],
            "status": "completed",
            "ended_at": utc_now_iso(),
        },
        "outputs": output,
        **metadata,
    }
    write_json(ctx["run_dir"] / f"{step_id}_result.json", result)
    write_json(ctx["run_dir"] / "workflow_state" / f"{step_id}_result.json", result)
    return result


def ensure_run_started(ctx: dict[str, Any]) -> None:
    run_path = ctx["run_dir"] / "run.json"
    if not run_path.exists():
        write_json(ctx["run_dir"] / "config.json", ctx["config"])
        write_json(
            ctx["run_dir"] / "inputs.json",
            {
                "payload": ctx["payload"],
                "document_folder": str(ctx["document_folder"]),
                "output_folder": str(ctx["output_folder"]),
            },
        )
        write_json(
            run_path,
            {
                "run_id": ctx["run_id"],
                "blueprint_id": BLUEPRINT_ID,
                "status": "running",
                "started_at": ctx["started_at"],
            },
        )
        append_event(ctx["run_dir"], "blueprint_status", {"status": "running", "component": BLUEPRINT_ID})
    persist_runtime_context(ctx)


def finish_completed_run(ctx: dict[str, Any], final_output: dict[str, Any]) -> dict[str, Any]:
    final_artifact = final_output["final_artifact"]
    output_files = list(final_output.get("output_files") or [])

    for name in ("action_ledger.json", "artifact_quality.json", "run_health.json"):
        source_path = ctx["output_folder"] / name
        if source_path.exists():
            write_json(ctx["run_dir"] / name, read_json(source_path))

    final_artifact_path = ctx["output_folder"] / "final_artifact.json"
    result_path = ctx["output_folder"] / "result.json"
    for path in (final_artifact_path, result_path):
        path_text = str(path)
        if path_text not in output_files:
            output_files.append(path_text)
    final_artifact["output_files"] = output_files

    result = {
        "run_id": ctx["run_id"],
        "blueprint_id": BLUEPRINT_ID,
        "status": "completed",
        "final_artifact": final_artifact,
        "output_files": output_files,
    }
    write_json(final_artifact_path, final_artifact)
    write_json(result_path, result)
    write_json(ctx["run_dir"] / "result.json", result)
    write_json(ctx["run_dir"] / "final_artifact.json", final_artifact)
    write_json(
        ctx["run_dir"] / "run.json",
        {
            "run_id": ctx["run_id"],
            "blueprint_id": BLUEPRINT_ID,
            "status": "completed",
            "completed_at": utc_now_iso(),
        },
    )
    for name in ("result.json", "final_artifact.json", "action_ledger.json", "artifact_quality.json", "run_health.json"):
        append_event(ctx["run_dir"], "artifact_written", {"path": str(ctx["output_folder"] / name)})
    append_event(
        ctx["run_dir"],
        "human_input_requested",
        {
            "mode": "approval_required",
            "reason": "Review financial advisor packet before filing, trading, money movement, bill payment, or external sharing.",
        },
    )
    append_event(ctx["run_dir"], "blueprint_status", {"status": "completed", "component": BLUEPRINT_ID})
    return result


def build_context(
    *,
    inputs: dict[str, Any] | None,
    config: dict[str, Any] | None,
    config_json: str | None,
    runs_root: str | Path | None,
    run_id: str | None,
    llm_client: Any | None,
) -> dict[str, Any]:
    resolved_config = load_resolved_config(config, config_json)
    payload = resolve_inputs(resolved_config, inputs)
    root = blueprint_dir()
    document_folder = expand_path(payload.get("document_folder") or payload.get("input_folder"), root=root.parent if str(payload.get("document_folder", "")).startswith(BLUEPRINT_ID) else root)
    if not document_folder.exists():
        document_folder = expand_path(payload.get("document_folder") or payload.get("input_folder"), root=Path.cwd())
    outputs_config = resolved_config.get("outputs") if isinstance(resolved_config.get("outputs"), dict) else {}
    explicit_output_folder = (inputs or {}).get("output_folder")
    runtime_output_folder = os.environ.get("MN_JOB_OUTPUT_DIR")
    configured_output_folder = outputs_config.get("output_folder") or outputs_config.get("folder_path")
    output_folder = expand_path(
        explicit_output_folder
        or runtime_output_folder
        or configured_output_folder
        or payload.get("output_folder")
        or f"~/Downloads/{BLUEPRINT_ID}"
    )
    output_folder.mkdir(parents=True, exist_ok=True)
    run_id_value = run_id or payload.get("run_id") or os.environ.get("MN_RUN_ID") or f"{BLUEPRINT_ID}-{uuid.uuid4().hex[:8]}"
    env_run_dir = os.environ.get("MN_RUN_DIR")
    if not runs_root and env_run_dir:
        run_dir = expand_path(env_run_dir)
        runs_root_path = run_dir.parent
    else:
        runs_root_path = expand_path(runs_root or os.environ.get("MN_RUNS_ROOT") or output_folder / "runs")
        run_dir = runs_root_path / run_id_value
    run_dir.mkdir(parents=True, exist_ok=True)
    persisted = read_json(runtime_context_path(run_dir))
    started_at = utc_now_iso()
    if persisted:
        persisted_payload = persisted.get("payload") if isinstance(persisted.get("payload"), dict) else {}
        payload = deep_merge(payload, persisted_payload)
        document_folder = expand_path(persisted.get("document_folder") or document_folder)
        output_folder = expand_path(persisted.get("output_folder") or output_folder)
        persisted_run_dir = str(persisted.get("run_dir") or "").strip()
        if persisted_run_dir:
            run_dir = expand_path(persisted_run_dir)
            runs_root_path = run_dir.parent
            run_dir.mkdir(parents=True, exist_ok=True)
        started_at = str(persisted.get("started_at") or started_at)
    payload["document_folder"] = str(document_folder)
    payload["input_folder"] = str(document_folder)
    payload["output_folder"] = str(output_folder)
    llm = build_llm_client(resolved_config, payload, llm_client)
    state = load_state(run_dir) or {"workflow": {}, "actor_findings": {}, "model_profiles_used": {}}
    return {
        "blueprint_id": BLUEPRINT_ID,
        "config": resolved_config,
        "payload": payload,
        "blueprint_dir": root,
        "document_folder": document_folder,
        "output_folder": output_folder,
        "runs_root": runs_root_path,
        "run_dir": run_dir,
        "run_id": run_id_value,
        "started_at": started_at,
        "llm": llm,
        "state": state,
        "active_knowledge": load_financial_knowledge(root),
    }


def runtime_context_for_step(
    *,
    inputs: dict[str, Any] | None = None,
    config: dict[str, Any] | None = None,
    runs_root: str | Path | None = None,
    run_id: str | None = None,
    llm_client: Any | None = None,
) -> dict[str, Any]:
    """Adapt the financial domain context to the SDK step lifecycle."""
    return build_context(
        inputs=inputs,
        config=config,
        config_json=None,
        runs_root=runs_root,
        run_id=run_id,
        llm_client=llm_client,
    )


def run_blueprint(
    inputs: dict[str, Any] | None = None,
    config: dict[str, Any] | None = None,
    runs_root: str | Path | None = None,
    run_id: str | None = None,
    llm_client: Any | None = None,
    config_json: str | None = None,
) -> dict[str, Any]:
    start_agent_beacon_thread(f"{BLUEPRINT_NAME} is running")
    current_run_id = run_id
    final_result: dict[str, Any] | None = None
    for step_id in WORKFLOW_STEPS:
        final_result = run_runtime_step(
            step_id,
            inputs=inputs,
            config=config,
            runs_root=runs_root,
            run_id=current_run_id,
            llm_client=llm_client,
            config_json=config_json,
        )
        current_run_id = final_result["run_id"]
    if not final_result or "final_artifact" not in final_result:
        raise RuntimeError("Financial Advisor workflow completed without a final artifact.")
    final_context = runtime_context_for_step(
        inputs=inputs,
        config=config,
        runs_root=runs_root,
        run_id=final_result["run_id"],
    )
    final_context["run_dir"].mkdir(parents=True, exist_ok=True)
    write_json(final_context["output_folder"] / "final_artifact.json", final_result["final_artifact"])
    write_json(
        final_context["output_folder"] / "result.json",
        {
            "run_id": final_result["run_id"],
            "blueprint_id": BLUEPRINT_ID,
            "status": "completed",
            "final_artifact": final_result["final_artifact"],
            "output_files": final_result.get("output_files", []),
        },
    )
    write_json(final_context["run_dir"] / "final_artifact.json", final_result["final_artifact"])
    write_json(
        final_context["run_dir"] / "result.json",
        {
            "run_id": final_result["run_id"],
            "blueprint_id": BLUEPRINT_ID,
            "status": "completed",
            "final_artifact": final_result["final_artifact"],
            "output_files": final_result.get("output_files", []),
        },
    )
    for artifact_name in ("action_ledger.json", "artifact_quality.json", "run_health.json"):
        source = final_context["output_folder"] / artifact_name
        if source.exists():
            write_json(final_context["run_dir"] / artifact_name, read_json(source))
    write_json(
        final_context["run_dir"] / "run.json",
        {"run_id": final_result["run_id"], "blueprint_id": BLUEPRINT_ID, "status": "completed", "completed_at": utc_now_iso()},
    )
    return {
        "run_id": final_result["run_id"],
        "blueprint_id": BLUEPRINT_ID,
        "status": final_result["status"],
        "final_artifact": final_result["final_artifact"],
        "output_files": final_result.get("output_files", []),
    }


def run_runtime_step(
    step_id: str,
    inputs: dict[str, Any] | None = None,
    config: dict[str, Any] | None = None,
    runs_root: str | Path | None = None,
    run_id: str | None = None,
    llm_client: Any | None = None,
    config_json: str | None = None,
) -> dict[str, Any]:
    step_id = str(step_id or "").strip()
    step = next((item for item in _source_workflow_step_specs() if item.get("id") == step_id), None)
    if step is None:
        raise ValueError(f"Unknown Financial Advisor workflow step: {step_id}")
    run_spec = step.get("run", {})
    from mn_sdk.step_runtime import StepContext, normalize_result, resolve_handler

    # Local callers execute this adapter from the source checkout, while the
    # worker entrypoint adds the staged payload root itself.  Keep both paths
    # available so manifest handlers resolve identically in either environment.
    runtime_path = Path(__file__).resolve().parent
    for import_path in (runtime_path, runtime_path.parent):
        path_text = str(import_path)
        if path_text not in sys.path:
            sys.path.insert(0, path_text)
    step_context = StepContext(step_id=step_id, run_id=str(run_id or ""), config=dict(config or {}))
    handler = resolve_handler(str(run_spec["handler"]))
    raw_result = handler(
        step_context,
        **dict(run_spec.get("with", {})),
        inputs=inputs,
        runs_root=runs_root,
        llm_client=llm_client,
        config_json=config_json,
    )
    result = normalize_result(raw_result, step_context)
    # ``run_runtime_step`` is the local convenience entrypoint; make its
    # envelope match the worker lifecycle while retaining the domain fields
    # for callers that use the old in-process API.
    result["runtime_step_mode"] = "workflow_step_handler"
    result.setdefault("outputs", raw_result if isinstance(raw_result, dict) else {"value": raw_result})
    # The in-process convenience runner has no scheduler to merge the step
    # envelope into workflow state.  Do that small merge here so sequential
    # local runs exercise the same state contract as worker executions.
    lifecycle_context = runtime_context_for_step(
        inputs=inputs,
        config=config,
        runs_root=runs_root,
        run_id=run_id,
    )
    lifecycle_context.setdefault("state", {}).setdefault("workflow", {})[step_id] = result.get("outputs")
    save_state(lifecycle_context["run_dir"], lifecycle_context["state"])
    return result


def execute_runtime_handler(
    step_id: str,
    handler: Any,
    inputs: dict[str, Any] | None = None,
    config: dict[str, Any] | None = None,
    runs_root: str | Path | None = None,
    run_id: str | None = None,
    llm_client: Any | None = None,
    config_json: str | None = None,
) -> dict[str, Any]:
    """Execute one manifest-resolved Financial Advisor handler."""

    step_id = str(step_id or "").strip()
    if not step_id:
        raise ValueError("Financial Advisor workflow step id is required")
    ctx = build_context(
        inputs=inputs,
        config=config,
        config_json=config_json,
        runs_root=runs_root,
        run_id=run_id,
        llm_client=llm_client,
    )
    step_started = time.monotonic()
    ensure_run_started(ctx)
    try:
        append_event(ctx["run_dir"], "blueprint_phase_started", {"phase": step_id})
        profile = step_model_profile(ctx["config"], step_id)
        ctx["state"].setdefault("model_profiles_used", {})[step_id] = {
            "llm_config": profile["llm_config"],
            "model": profile["model"],
            "runtime_model": profile["runtime_model"],
        }
        usage_before = llm_usage(ctx["llm"])
        ctx["step_llm_usage_before"] = usage_before
        output = handler(ctx)
        usage_after = llm_usage(ctx["llm"])
        llm_delta = usage_delta(usage_before, usage_after)
        if llm_delta.get("fallback_calls") and live_llm_requested(ctx["config"], ctx.get("payload")):
            raise RuntimeError(f"Live LLM fallback was used during {step_id}; failing normal run instead of silently degrading.")
        cumulative_llm_usage = accumulate_llm_usage(ctx, llm_delta)
        ctx["state"].setdefault("workflow", {})[step_id] = output
        append_event(
            ctx["run_dir"],
            f"{step_id}_completed",
            {
                "step_id": step_id,
                "runtime_step_mode": "manifest_handler",
                "llm_config": profile["llm_config"],
                "model": profile["model"],
                "llm_usage_delta": llm_delta,
                "llm_usage": cumulative_llm_usage,
            },
        )
        append_event(ctx["run_dir"], "blueprint_phase_completed", {"phase": step_id})
        save_state(ctx["run_dir"], ctx["state"])
        final_result: dict[str, Any] | None = None
        if step_id == WORKFLOW_STEPS[-1]:
            final_result = finish_completed_run(ctx, output)
        metadata: dict[str, Any] = {
            "elapsed_ms": round((time.monotonic() - step_started) * 1000, 2),
            "output_files": final_result.get("output_files", []) if final_result else output.get("output_files", []),
        }
        if final_result:
            metadata["final_artifact"] = final_result["final_artifact"]
        return step_result(ctx, step_id, output, **metadata)
    except Exception as exc:
        append_event(
            ctx["run_dir"],
            "workflow_step_failed",
            {
                "step_id": step_id,
                "runtime_step_mode": "workflow_step_handler",
                "elapsed_ms": round((time.monotonic() - step_started) * 1000, 2),
                "error": str(exc),
            },
        )
        append_event(ctx["run_dir"], "blueprint_phase_failed", {"phase": step_id, "error": str(exc)})
        write_failed_run(ctx, exc)
        raise


def final_artifact_for_transport(final_artifact: dict[str, Any]) -> dict[str, Any]:
    compact = {
        key: final_artifact.get(key)
        for key in (
            "type",
            "blueprint_id",
            "run_id",
            "executive_summary",
            "recommended_action",
            "confidence",
            "review_only",
            "review_status",
            "customer_readiness",
            "customer_report",
        )
        if key in final_artifact
    }
    compact["artifact_summary"] = {
        "bank_statement_count": (final_artifact.get("bank_statement_extraction") or {}).get("statement_count"),
        "tax_form_count": (final_artifact.get("tax_form_ocr_capture") or {}).get("tax_form_count"),
        "portfolio_total_value": (final_artifact.get("portfolio_risk_review") or {}).get("total_value"),
        "llm_review_count": len([key for key in ("cash_flow", "tax", "portfolio") if (final_artifact.get("llm_analysis") or {}).get(key)]),
        "output_file_count": len(final_artifact.get("output_files") or []),
        "warning_count": len(final_artifact.get("research_warnings") or []),
    }
    compact["transport"] = {
        "compacted": True,
        "omitted_fields": [
            "evidence",
            "research_sources",
            "bank_statement_extraction",
            "household_finance_summary",
            "tax_review_packet",
            "tax_form_ocr_capture",
            "portfolio_risk_review",
            "llm_analysis",
            "output_files",
        ],
        "reason": "Keep workflow step transport small; full review artifacts remain in the output folder.",
    }
    return compact


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the unified financial advisor blueprint.")
    parser.add_argument("--input-file", type=Path)
    parser.add_argument("--input-folder", default="")
    parser.add_argument("--output-folder", default="")
    parser.add_argument("--runs-root", type=Path)
    parser.add_argument("--run-id")
    parser.add_argument("--config-json")
    args = parser.parse_args(argv)

    inputs: dict[str, Any] = {}
    if args.input_file:
        loaded = json.loads(args.input_file.read_text(encoding="utf-8"))
        inputs.update(loaded if isinstance(loaded, dict) else {})
    if args.input_folder:
        inputs["document_folder"] = args.input_folder
        inputs["input_folder"] = args.input_folder
    if args.output_folder:
        inputs["output_folder"] = args.output_folder

    step_id = os.environ.get("MN_WORKFLOW_STEP_ID", "").strip()
    if step_id:
        result = run_runtime_step(
            step_id,
            inputs=inputs,
            runs_root=args.runs_root,
            run_id=args.run_id,
            config_json=args.config_json,
        )
    else:
        result = run_blueprint(inputs=inputs, runs_root=args.runs_root, run_id=args.run_id, config_json=args.config_json)
    printable = {"run_id": result["run_id"], "status": result["status"]}
    if "workflow_step_id" in result:
        printable["workflow_step_id"] = result["workflow_step_id"]
    if "runtime_step_mode" in result:
        printable["runtime_step_mode"] = result["runtime_step_mode"]
    if "final_artifact" in result:
        printable["final_artifact"] = final_artifact_for_transport(result["final_artifact"]) if step_id else result["final_artifact"]
    if result.get("output_files") and not step_id:
        printable["output_files"] = result["output_files"]
    print(json.dumps(printable, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
