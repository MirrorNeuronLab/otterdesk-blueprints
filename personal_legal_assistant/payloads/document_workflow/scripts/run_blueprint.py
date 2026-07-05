#!/usr/bin/env python3.11
from __future__ import annotations

import argparse
import copy
import json
import os
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from mn_blueprint_support import start_agent_beacon_thread
except Exception:  # pragma: no cover - optional runtime support
    def start_agent_beacon_thread(message: str | None = None) -> None:
        return None


BLUEPRINT_ID = "personal_legal_assistant"
BLUEPRINT_NAME = "Personal Legal Assistant"
OUTPUT_TYPE = "personal_legal_assistant_report"
RECOMMENDED_ACTION = "attorney_and_human_review_required_before_legal_payment_or_contract_action"
SUPPORTED_SUFFIXES = {".pdf", ".png", ".jpg", ".jpeg", ".txt", ".json", ".csv", ".md"}
TEXT_SUFFIXES = {".txt", ".json", ".csv", ".md"}
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
    "personal_legal_reporter",
]
HEAVY_MODEL_STEPS = {
    "contract_playbook_comparator",
    "legal_review_auditor",
    "personal_legal_reporter",
}
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
}


class DeterministicLLM:
    provider = "fake"
    model = "deterministic-personal-legal-assistant"

    def __init__(self) -> None:
        self.calls = 0
        self.fallback_calls = 0
        self.prompts: list[dict[str, str]] = []

    def generate_json(self, *, system_prompt: str, user_prompt: str, fallback: dict[str, Any]) -> dict[str, Any]:
        self.calls += 1
        self.fallback_calls += 1
        self.prompts.append({"system": system_prompt, "user": user_prompt})
        response = copy.deepcopy(fallback)
        response.setdefault("provider", self.provider)
        response.setdefault("model", self.model)
        response.setdefault("summary", "Deterministic personal legal review completed from local evidence.")
        response.setdefault("confidence", 0.72)
        return response


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
    record = {"type": event_type, "timestamp": utc_now_iso(), "payload": redact_value(payload)}
    with (run_dir / "events.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True, default=str) + "\n")


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


def blueprint_dir() -> Path:
    return Path(__file__).resolve().parents[3]


def default_config_path() -> Path:
    return blueprint_dir() / "config" / "default.json"


def load_resolved_config(config: dict[str, Any] | None = None, config_json: str | None = None) -> dict[str, Any]:
    resolved = read_json(default_config_path())
    env_path = os.environ.get("MN_BLUEPRINT_CONFIG_PATH")
    if env_path:
        resolved = deep_merge(resolved, read_json(Path(env_path).expanduser()))
    env_json = config_json or os.environ.get("MN_BLUEPRINT_CONFIG_JSON")
    if env_json:
        decoded = json.loads(env_json)
        if isinstance(decoded, dict):
            resolved = deep_merge(resolved, decoded)
    if config:
        resolved = deep_merge(resolved, config)
    return resolved


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
    interesting = {"document_folder", "input_folder", "output_folder", "field_profile", "matter_profile", "review_policy"}
    if interesting & set(value):
        return copy.deepcopy(value)
    for key in ("payload", "input", "body", "data", "message", "content"):
        found = find_payload(value.get(key))
        if found:
            return found
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


def expand_path(raw: Any, *, root: Path | None = None) -> Path:
    value = str(raw or "").strip() or "."
    path = Path(value).expanduser()
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


def read_document_text(path: Path) -> tuple[str, bool, list[str]]:
    if path.suffix.lower() in TEXT_SUFFIXES:
        try:
            return path.read_text(encoding="utf-8", errors="ignore"), False, []
        except Exception as exc:
            return "", False, [f"Could not read text: {exc}"]
    if path.suffix.lower() in SUPPORTED_SUFFIXES:
        return "", True, ["OCR or PDF text extraction is required before trusting this source."]
    return "", False, ["Unsupported file type skipped."]


def load_documents(folder: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if not folder.exists():
        return records
    for path in sorted(folder.rglob("*")):
        if path.is_dir() or path.name.startswith("."):
            continue
        if path.suffix.lower() not in SUPPORTED_SUFFIXES:
            continue
        text, ocr_required, warnings = read_document_text(path)
        document_type = classify_document(text, path.name)
        records.append(
            {
                "path": str(path),
                "filename": path.name,
                "document_type": document_type,
                "text": redact_value(text),
                "ocr_required": ocr_required,
                "extraction_method": "embedded_text" if text else "ocr_required_placeholder",
                "warnings": warnings,
                "metadata": {"size_bytes": path.stat().st_size},
            }
        )
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
        "schema_version": "mn.blueprint.personal_legal.invoice_bill_extraction.v1",
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
                        "clause_type": field,
                        "text": snippet,
                        "confidence": 0.78,
                        "review_notes": ["Attorney review required before relying on this classification."],
                    }
                )
    clause_types = sorted({clause["clause_type"] for clause in clauses})
    return {
        "schema_version": "mn.blueprint.personal_legal.contract_clause_review.v1",
        "contract_count": len(contract_records(records)),
        "clause_count": len(clauses),
        "clause_types": clause_types,
        "clauses": clauses,
        "playbook_comparison": compare_to_playbook(clause_types),
        "review_required": True,
    }


def compare_to_playbook(clause_types: list[str]) -> dict[str, Any]:
    required = {"governing_law", "assignment", "termination", "liability"}
    present = set(clause_types)
    missing = sorted(required - present)
    deviations = []
    if "liability" in present:
        deviations.append("Confirm liability cap, exclusions, and indirect damages language with counsel.")
    if "assignment" in present:
        deviations.append("Check whether assignment restrictions affect transfers, affiliates, or change-of-control events.")
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


def model_profiles_used(config: dict[str, Any]) -> dict[str, dict[str, str]]:
    agents = (config.get("llm") or {}).get("agents") or {}
    configs = (config.get("llm") or {}).get("configs") or {}
    result = {}
    for step in WORKFLOW_STEPS:
        llm_config = str((agents.get(step) or {}).get("llm_config") or "primary")
        model = str((configs.get(llm_config) or {}).get("model") or (config.get("llm") or {}).get("model") or "unknown")
        result[step] = {"llm_config": llm_config, "model": model}
    return result


def llm_generate(llm: Any, *, actor_id: str, fallback: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    if llm is None:
        llm = DeterministicLLM()
    if hasattr(llm, "generate_json"):
        return llm.generate_json(
            system_prompt=f"You are {actor_id} in a review-only personal legal assistant.",
            user_prompt=json.dumps(redact_value(context), sort_keys=True, default=str)[:6000],
            fallback=fallback,
        )
    return fallback


def run_actor_reviews(config: dict[str, Any], llm_client: Any | None, context: dict[str, Any]) -> dict[str, Any]:
    llm = llm_client or DeterministicLLM()
    actor_findings: dict[str, Any] = {}
    for actor_id, spec in ((config.get("llm") or {}).get("agents") or {}).items():
        fallback = {
            "actor_id": actor_id,
            "role": spec.get("role") or actor_id,
            "llm_config": spec.get("llm_config") or "primary",
            "summary": f"{spec.get('role') or actor_id} reviewed the local evidence packet.",
            "confidence": 0.72,
            "findings": [
                "Keep the packet review-only.",
                "Preserve source references for every extracted value.",
                "Escalate legal, payment, signature, or external-sharing actions for human approval.",
            ],
        }
        actor_findings[actor_id] = llm_generate(llm, actor_id=actor_id, fallback=fallback, context=context)
    return actor_findings


def llm_usage(llm_client: Any | None, actor_findings: dict[str, Any]) -> dict[str, Any]:
    return {
        "provider": getattr(llm_client, "provider", "fake"),
        "model": getattr(llm_client, "model", "deterministic-personal-legal-assistant"),
        "calls": int(getattr(llm_client, "calls", len(actor_findings))),
        "fallback_calls": int(getattr(llm_client, "fallback_calls", 0)),
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
        "# Personal Legal Assistant Report",
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
        "generated_at": utc_now_iso(),
    }
    write_json(output_folder / "final_artifact.json", final_artifact)
    write_json(output_folder / "invoice_bill_extraction.json", final_artifact["invoice_bill_extraction"])
    write_json(output_folder / "contract_clause_review.json", final_artifact["contract_clause_review"])
    write_json(output_folder / "legal_issue_register.json", final_artifact["legal_issue_register"])
    write_json(output_folder / "action_ledger.json", action_ledger)
    write_json(output_folder / "artifact_quality.json", artifact_quality)
    write_json(output_folder / "run_health.json", run_health)
    write_text(output_folder / "personal_legal_report.md", build_markdown(final_artifact))
    for name, value in (
        ("action_ledger.json", action_ledger),
        ("artifact_quality.json", artifact_quality),
        ("run_health.json", run_health),
    ):
        write_json(run_dir / name, value)
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
    output_folder = expand_path(payload.get("output_folder") or (resolved_config.get("outputs") or {}).get("folder_path") or "~/Downloads/personal_legal_assistant")
    run_dir = (Path(runs_root).expanduser() if runs_root else output_folder / "runs") / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    write_json(run_dir / "run.json", {"run_id": run_id, "blueprint_id": BLUEPRINT_ID, "status": "running", "started_at": utc_now_iso()})
    write_json(run_dir / "config.json", resolved_config)
    write_json(run_dir / "inputs.json", {"payload": payload, "document_folder": str(document_folder), "dataset_inputs": DATASET_INPUTS})
    append_event(run_dir, "blueprint_phase_started", {"phase": "loading_inputs", "component": BLUEPRINT_ID})
    append_event(run_dir, "blueprint_phase_completed", {"phase": "loading_inputs", "component": BLUEPRINT_ID})
    append_event(run_dir, "blueprint_phase_started", {"phase": "running_worker", "component": BLUEPRINT_ID})

    records = load_documents(document_folder)
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
    }
    actor_findings = run_actor_reviews(resolved_config, llm_client, actor_context)
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
        "source_refs": ["inputs.json", "events.jsonl", "result.json", "invoice_bill_extraction.json", "contract_clause_review.json"],
        "dataset_inputs": DATASET_INPUTS,
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
        "model_profiles_used": model_profiles_used(resolved_config),
        "actor_findings": actor_findings,
        "llm_usage": llm_usage(llm_client, actor_findings),
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
    for name in ("result.json", "final_artifact.json", "action_ledger.json", "artifact_quality.json", "run_health.json"):
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
