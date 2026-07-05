#!/usr/bin/env python3.11
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from mn_blueprint_support import start_agent_beacon_thread
except Exception:  # pragma: no cover - optional runtime support
    def start_agent_beacon_thread(message: str | None = None) -> None:
        return None


BLUEPRINT_ID = "financial_advisor"
BLUEPRINT_NAME = "Financial Advisor"
OUTPUT_TYPE = "financial_advisor_report"
RECOMMENDED_ACTION = "review_integrated_financial_advisor_packet_before_any_financial_action"
SUPPORTED_SUFFIXES = {".pdf", ".png", ".jpg", ".jpeg", ".txt", ".json", ".csv", ".md"}
TEXT_SUFFIXES = {".txt", ".json", ".csv", ".md"}
HEAVY_MODEL_STEPS = {
    "tax_workpaper_preparer",
    "portfolio_risk_engine",
    "advisor_review_auditor",
    "financial_advice_reporter",
}
WORKFLOW_STEPS = [
    "financial_folder_watcher",
    "financial_document_reader",
    "bank_statement_extractor",
    "cash_flow_normalizer",
    "tax_document_router",
    "tax_form_ocr_capturer",
    "tax_workpaper_preparer",
    "portfolio_context_loader",
    "portfolio_market_data_loader",
    "portfolio_risk_engine",
    "public_finance_researcher",
    "advisor_evidence_reconciler",
    "advisor_review_auditor",
    "financial_advice_reporter",
]
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


class DeterministicLLM:
    provider = "fake"
    model = "deterministic-financial-advisor"

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
        response.setdefault("confidence", 0.74)
        response.setdefault("summary", "Deterministic review packet generated from local evidence.")
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
        return text[:1000]
    return value


def default_config_path() -> Path:
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "config" / "default.json"
        if candidate.exists():
            return candidate
    return Path(__file__).resolve().parents[3] / "config" / "default.json"


def blueprint_dir() -> Path:
    return default_config_path().parents[1]


def load_resolved_config(config: dict[str, Any] | None = None, config_json: str | None = None) -> dict[str, Any]:
    resolved = read_json(default_config_path())
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


def read_document(path: Path) -> dict[str, Any]:
    suffix = path.suffix.lower()
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
    profile.setdefault("model", llm.get("model") or "gemma4:e2b")
    profile.setdefault("runtime_model", profile.get("model"))
    return {
        "agent_id": step_id,
        "llm_config": config_name,
        "model": profile.get("model"),
        "runtime_model": profile.get("runtime_model"),
        "require_live": bool(profile.get("require_live", False)),
        "profile": profile,
    }


def actor_review(config: dict[str, Any], llm: Any, step_id: str, summary: str, context: dict[str, Any]) -> dict[str, Any]:
    profile = step_model_profile(config, step_id)
    fallback = {
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
    if llm is None:
        response = fallback
    else:
        try:
            response = llm.generate_json(
                system_prompt=(
                    "Return compact JSON for a review-only financial advisor actor. "
                    "Do not recommend filing, trading, moving money, paying bills, or external sharing."
                ),
                user_prompt=json.dumps(
                    {
                        "actor_id": step_id,
                        "model_profile": profile,
                        "context": redact_value(context),
                        "fallback_shape": fallback,
                    },
                    sort_keys=True,
                    default=str,
                ),
                fallback=fallback,
            )
        except Exception as exc:
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
    }


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
    docs = [read_document(path) for path in iter_input_files(ctx["document_folder"])]
    counts: dict[str, int] = {}
    for doc in docs:
        counts[doc["kind"]] = counts.get(doc["kind"], 0) + 1
    return {
        "documents": docs,
        "document_count": len(docs),
        "kind_counts": counts,
        "source_refs": [doc["source_ref"] for doc in docs],
        "warnings": [warning for doc in docs for warning in doc.get("warnings", [])],
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
            transactions.append(
                {
                    "source_ref": doc["source_ref"],
                    "line_no": line_no,
                    "description": line.strip(),
                    "amount": amount,
                    "direction": direction,
                }
            )
        extracted.append(
            {
                "source_ref": doc["source_ref"],
                "opening_balance": opening_balance,
                "closing_balance": closing_balance,
                "transactions": transactions,
            }
        )
    return {
        "statement_count": len(statements),
        "statements": extracted,
        "totals": totals,
        "opening_balance": opening_balance,
        "closing_balance": closing_balance,
        "net_cash_flow": totals["deposits"] - totals["withdrawals"] - totals["fees"],
        "warnings": [] if statements else ["no_bank_statement_detected"],
    }


def step_cash_flow_normalizer(ctx: dict[str, Any]) -> dict[str, Any]:
    bank = ctx["state"]["workflow"]["bank_statement_extractor"]
    docs = ctx["state"]["workflow"]["financial_document_reader"]["documents"]
    income_docs = [doc for doc in docs if doc["kind"] in {"income_document", "w2", "1099_int", "1099_r"}]
    totals = bank.get("totals") or {}
    income = float(totals.get("deposits") or 0.0)
    expenses = float(totals.get("withdrawals") or 0.0) + float(totals.get("fees") or 0.0)
    warnings = []
    if income <= 0 and income_docs:
        warnings.append("income_documents_present_but_no_bank_deposits_detected")
    if totals.get("fees", 0) > 0:
        warnings.append("bank_fees_detected_for_review")
    if expenses > income and income > 0:
        warnings.append("expenses_exceed_detected_income")
    return {
        "income_total": income,
        "expense_total": expenses,
        "fee_total": float(totals.get("fees") or 0.0),
        "net_cash_flow": income - expenses,
        "closing_balance": bank.get("closing_balance", 0.0),
        "income_document_count": len(income_docs),
        "risk_flags": warnings,
        "summary": f"Detected {money(income)} income-like deposits and {money(expenses)} expenses/fees.",
    }


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
        image_warnings = list(image.get("warnings") or [])
        if label_doc:
            matched_label_stems.add(stem)
            validation_status = "matched_companion_answer_file"
            extraction_method = "image_metadata_plus_companion_answer_file"
        else:
            validation_status = "needs_manual_ocr_or_answer_file"
            extraction_method = "image_metadata_only"
            image_warnings.append("missing_companion_answer_file")
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
        warnings.append("answer_file_without_matching_source_image")
        forms.append(
            {
                "source_ref": label_doc["source_ref"],
                "answer_file": label_doc["source_ref"],
                "form_type": form_type,
                "ocr_required": False,
                "extraction_method": "companion_answer_file_only",
                "captured_fields": captured_fields,
                "field_locations": [],
                "validation_status": "needs_source_image_review",
                "confidence": 0.62,
                "warnings": ["answer_file_without_matching_source_image"],
            }
        )

    review_required = [
        form["source_ref"]
        for form in forms
        if form["validation_status"] != "matched_companion_answer_file" or form.get("warnings")
    ]
    return {
        "tax_form_count": len(forms),
        "answer_file_count": len(label_docs),
        "ocr_required_count": len([form for form in forms if form.get("ocr_required")]),
        "forms": forms,
        "review_required_sources": review_required,
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
        {"draft_income": draft_income, "missing": router.get("missing_recommended_forms")},
    )
    blockers = list(router.get("missing_recommended_forms") or [])
    if tax_capture.get("review_required_sources"):
        blockers.append("Tax form OCR capture requires source-image review")
    if draft_income <= 0:
        blockers.append("No taxable-income source values detected")
    return {
        "tax_year": router.get("tax_year"),
        "filing_status": router.get("filing_status"),
        "workpapers": {
          "wages": wages,
          "interest_income": interest,
          "retirement_distributions": retirement_distribution,
          "draft_income_total": draft_income,
          "federal_withholding": withholding
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
        },
        "actor_finding": findings,
        "warnings": ["draft_tax_packet_not_ready_to_file"],
    }


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
    return {
        "portfolio": portfolio,
        "benchmark_portfolio": loaded.get("benchmark_portfolio") or {},
        "risk_policy": loaded.get("risk_policy") or {},
        "decision_constraints": loaded.get("decision_constraints") or {},
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
        price = float((market.get("series") or {}).get(symbol, {}).get("last_price") or deterministic_price(symbol))
        value = quantity * price
        invested_value += value
        weighted_risk += value * RISK_BY_ASSET_CLASS.get(asset_class, RISK_BY_ASSET_CLASS["other"])
        marked_holdings.append(
            {
                "symbol": symbol,
                "quantity": quantity,
                "asset_class": asset_class,
                "price": price,
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
    violations = []
    if largest > float(policy.get("max_single_name_weight_pct") or 100):
        violations.append("single_name_concentration")
    if cash_weight < float(policy.get("min_cash_pct") or 0):
        violations.append("cash_below_policy")
    if var_pct > float(policy.get("max_var_pct") or 100):
        violations.append("var_above_policy")
    if cvar_pct > float(policy.get("max_cvar_pct") or 100):
        violations.append("cvar_above_policy")
    candidate_actions = ["no_action"]
    if "single_name_concentration" in violations:
        candidate_actions.append("reduce_concentration")
    if "cash_below_policy" in violations:
        candidate_actions.append("raise_cash")
    if var_pct > 0:
        candidate_actions.append("review_risk_budget")
    finding = actor_review(
        ctx["config"],
        ctx["llm"],
        "portfolio_risk_engine",
        "Portfolio risk reviewed with deterministic fixture market data.",
        {"violations": violations, "var_pct": var_pct, "cash_weight_pct": cash_weight},
    )
    return {
        "base_currency": portfolio.get("base_currency", "USD"),
        "total_value": total_value,
        "cash": cash,
        "cash_weight_pct": round(cash_weight, 2),
        "holdings": marked_holdings,
        "largest_position_weight_pct": round(largest, 2),
        "annualized_volatility_pct": round(annual_vol, 2),
        "var_pct": round(var_pct, 2),
        "cvar_pct": round(cvar_pct, 2),
        "policy_violations": violations,
        "candidate_actions": candidate_actions,
        "review_only": True,
        "actor_finding": finding,
        "warnings": ["risk_metrics_are_review_estimates_not_trade_instructions"],
    }


def step_public_finance_researcher(ctx: dict[str, Any]) -> dict[str, Any]:
    cash_flow = ctx["state"]["workflow"]["cash_flow_normalizer"]
    tax = ctx["state"]["workflow"]["tax_workpaper_preparer"]
    portfolio = ctx["state"]["workflow"]["portfolio_risk_engine"]
    topics = ["budget and cash-flow review", "bank account fee review"]
    if tax.get("manager_review", {}).get("blockers"):
        topics.append("tax records and missing form review")
    if ctx["state"]["workflow"]["tax_form_ocr_capturer"].get("tax_form_count"):
        topics.append("tax form OCR field validation review")
    if portfolio.get("policy_violations"):
        topics.append("portfolio concentration and risk tolerance review")
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
    }


def step_advisor_evidence_reconciler(ctx: dict[str, Any]) -> dict[str, Any]:
    workflow = ctx["state"]["workflow"]
    warnings = []
    for key in (
        "financial_document_reader",
        "bank_statement_extractor",
        "cash_flow_normalizer",
        "tax_document_router",
        "tax_form_ocr_capturer",
        "tax_workpaper_preparer",
        "portfolio_context_loader",
        "portfolio_market_data_loader",
        "portfolio_risk_engine",
        "public_finance_researcher",
    ):
        value = workflow.get(key) or {}
        warnings.extend(value.get("warnings") or [])
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
            "domain": "portfolio",
            "summary": f"{workflow['portfolio_context_loader']['holding_count']} holding(s) reviewed.",
            "source_refs": workflow["portfolio_market_data_loader"].get("source_refs", []),
        },
    ]
    return {
        "evidence": evidence,
        "warnings": sorted(set(warnings)),
        "contradictions": [],
        "missing_evidence": [
            warning for warning in warnings
            if warning.startswith("no_") or "missing" in warning
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
    if workflow["portfolio_risk_engine"].get("policy_violations"):
        issues.append("portfolio_policy_violations_present")
    finding = actor_review(
        ctx["config"],
        ctx["llm"],
        "advisor_review_auditor",
        "Advisor packet audited for evidence, math, and blocked action boundaries.",
        {"issues": issues, "blocked_actions": blocked_actions},
    )
    return {
        "issues": issues,
        "blocked_actions_confirmed": blocked_actions,
        "review_required": True,
        "actor_finding": finding,
        "quality_score": max(0.35, 0.9 - 0.08 * len(issues)),
        "warnings": ["human_review_required_before_downstream_action"],
    }


def build_final_artifact(ctx: dict[str, Any]) -> dict[str, Any]:
    workflow = ctx["state"]["workflow"]
    cash = workflow["cash_flow_normalizer"]
    tax = workflow["tax_workpaper_preparer"]
    tax_capture = workflow["tax_form_ocr_capturer"]
    portfolio = workflow["portfolio_risk_engine"]
    reconciler = workflow["advisor_evidence_reconciler"]
    auditor = workflow["advisor_review_auditor"]
    confidence = round(min(0.86, max(0.45, auditor.get("quality_score", 0.75))), 2)
    summary_parts = [
        f"Bank/cash-flow review detected net cash flow of {money(cash.get('net_cash_flow'))}.",
        f"Draft tax workpapers show review income of {money(tax.get('workpapers', {}).get('draft_income_total'))}.",
        f"Tax form OCR capture found {tax_capture.get('tax_form_count', 0)} form image/answer packet(s) for field review.",
        f"Portfolio risk review estimated total value at {money(portfolio.get('total_value'))} with largest position weight {portfolio.get('largest_position_weight_pct')}%.",
    ]
    warnings = sorted(set(reconciler.get("warnings") or []) | set(auditor.get("warnings") or []))
    return {
        "type": OUTPUT_TYPE,
        "blueprint_id": BLUEPRINT_ID,
        "run_id": ctx["run_id"],
        "generated_at": utc_now_iso(),
        "executive_summary": " ".join(summary_parts),
        "recommended_action": RECOMMENDED_ACTION,
        "confidence": confidence,
        "evidence": reconciler.get("evidence") or [],
        "next_steps": [
            "Review extracted bank-statement totals against source documents.",
            "Review draft tax workpapers and missing-form blockers before filing.",
            "Review portfolio risk policy violations before any trade decision.",
            "Approve, revise, or reject the packet before downstream action."
        ],
        "source_refs": sorted(
            set(workflow["financial_document_reader"].get("source_refs", []))
            | set(workflow["portfolio_market_data_loader"].get("source_refs", []))
            | set(workflow["public_finance_researcher"].get("source_refs", []))
        ),
        "research_summary": {
            "topics": workflow["public_finance_researcher"].get("topics", []),
            "warnings": workflow["public_finance_researcher"].get("warnings", []),
        },
        "research_sources": workflow["public_finance_researcher"].get("sources", []),
        "research_warnings": warnings,
        "bank_statement_extraction": workflow["bank_statement_extractor"],
        "household_finance_summary": cash,
        "tax_review_packet": tax,
        "tax_form_ocr_capture": tax_capture,
        "portfolio_risk_review": portfolio,
        "auditor_review": auditor,
        "model_profiles_used": ctx["state"].get("model_profiles_used", {}),
        "llm_usage": llm_usage(ctx["llm"]),
        "review_only": True,
        "blocked_actions": (ctx["config"].get("human_control") or {}).get("blocked_actions") or [],
    }


def markdown_report(final_artifact: dict[str, Any]) -> str:
    bank = final_artifact["bank_statement_extraction"]
    cash = final_artifact["household_finance_summary"]
    tax = final_artifact["tax_review_packet"]
    tax_capture = final_artifact["tax_form_ocr_capture"]
    portfolio = final_artifact["portfolio_risk_review"]
    lines = [
        "# Financial Advisor Report",
        "",
        final_artifact["executive_summary"],
        "",
        "## Bank Statement Extraction",
        "",
        f"- Statements: {bank.get('statement_count')}",
        f"- Deposits: {money((bank.get('totals') or {}).get('deposits'))}",
        f"- Withdrawals: {money((bank.get('totals') or {}).get('withdrawals'))}",
        f"- Fees: {money((bank.get('totals') or {}).get('fees'))}",
        "",
        "## Household Finance",
        "",
        f"- Income-like deposits: {money(cash.get('income_total'))}",
        f"- Expenses and fees: {money(cash.get('expense_total'))}",
        f"- Net cash flow: {money(cash.get('net_cash_flow'))}",
        "",
        "## Draft Tax Review",
        "",
        f"- Draft income total: {money(tax.get('workpapers', {}).get('draft_income_total'))}",
        f"- Federal withholding: {money(tax.get('workpapers', {}).get('federal_withholding'))}",
        f"- Manager blockers: {', '.join(tax.get('manager_review', {}).get('blockers') or ['none'])}",
        "",
        "## Tax Form OCR Capture",
        "",
        f"- Tax form packets: {tax_capture.get('tax_form_count')}",
        f"- Answer files: {tax_capture.get('answer_file_count')}",
        f"- OCR-required sources: {tax_capture.get('ocr_required_count')}",
        f"- Review-required sources: {', '.join(tax_capture.get('review_required_sources') or ['none'])}",
        "",
        "## Portfolio Risk",
        "",
        f"- Total value: {money(portfolio.get('total_value'))}",
        f"- Cash weight: {portfolio.get('cash_weight_pct')}%",
        f"- Largest position: {portfolio.get('largest_position_weight_pct')}%",
        f"- Policy violations: {', '.join(portfolio.get('policy_violations') or ['none'])}",
        "",
        "## Review Boundary",
        "",
        "This packet is review-only. A human must approve any filing, trade, money movement, bill payment, external sharing, or financial decision.",
        "",
        "## Next Steps",
        "",
        *[f"- {item}" for item in final_artifact["next_steps"]],
    ]
    return "\n".join(lines) + "\n"


def step_financial_advice_reporter(ctx: dict[str, Any]) -> dict[str, Any]:
    finding = actor_review(
        ctx["config"],
        ctx["llm"],
        "financial_advice_reporter",
        "Integrated financial advisor report written for human review.",
        {"workflow_keys": sorted(ctx["state"]["workflow"])},
    )
    ctx["state"].setdefault("actor_findings", {})["financial_advice_reporter"] = finding
    final_artifact = build_final_artifact(ctx)
    output_folder = ctx["output_folder"]
    artifacts = {
        "bank_statement_extraction.json": final_artifact["bank_statement_extraction"],
        "household_finance_summary.json": final_artifact["household_finance_summary"],
        "tax_review_packet.json": final_artifact["tax_review_packet"],
        "tax_form_ocr_capture.json": final_artifact["tax_form_ocr_capture"],
        "portfolio_risk_review.json": final_artifact["portfolio_risk_review"],
        "action_ledger.json": {
            "review_only": True,
            "blocked_actions": final_artifact["blocked_actions"],
            "recommended_action": final_artifact["recommended_action"],
        },
        "artifact_quality.json": {
            "confidence": final_artifact["confidence"],
            "warnings": final_artifact["research_warnings"],
            "required_fields_present": all(final_artifact.get(key) for key in ("type", "executive_summary", "recommended_action", "evidence", "next_steps")),
        },
        "run_health.json": {
            "status": "completed",
            "warnings_count": len(final_artifact["research_warnings"]),
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


STEP_HANDLERS = {
    "financial_folder_watcher": step_financial_folder_watcher,
    "financial_document_reader": step_financial_document_reader,
    "bank_statement_extractor": step_bank_statement_extractor,
    "cash_flow_normalizer": step_cash_flow_normalizer,
    "tax_document_router": step_tax_document_router,
    "tax_form_ocr_capturer": step_tax_form_ocr_capturer,
    "tax_workpaper_preparer": step_tax_workpaper_preparer,
    "portfolio_context_loader": step_portfolio_context_loader,
    "portfolio_market_data_loader": step_portfolio_market_data_loader,
    "portfolio_risk_engine": step_portfolio_risk_engine,
    "public_finance_researcher": step_public_finance_researcher,
    "advisor_evidence_reconciler": step_advisor_evidence_reconciler,
    "advisor_review_auditor": step_advisor_review_auditor,
    "financial_advice_reporter": step_financial_advice_reporter,
}


def run_step(ctx: dict[str, Any], step_id: str) -> dict[str, Any]:
    append_event(ctx["run_dir"], "blueprint_phase_started", {"phase": step_id})
    profile = step_model_profile(ctx["config"], step_id)
    ctx["state"].setdefault("model_profiles_used", {})[step_id] = {
        "llm_config": profile["llm_config"],
        "model": profile["model"],
        "runtime_model": profile["runtime_model"],
    }
    handler = STEP_HANDLERS[step_id]
    started = time.monotonic()
    result = handler(ctx)
    elapsed_ms = int((time.monotonic() - started) * 1000)
    ctx["state"].setdefault("workflow", {})[step_id] = result
    append_event(
        ctx["run_dir"],
        OUTPUT_MESSAGE_BY_STEP[step_id],
        {
            "step_id": step_id,
            "duration_ms": elapsed_ms,
            "llm_config": profile["llm_config"],
            "model": profile["model"],
        },
    )
    append_event(ctx["run_dir"], "blueprint_phase_completed", {"phase": step_id, "duration_ms": elapsed_ms})
    save_state(ctx["run_dir"], ctx["state"])
    return result


def step_result(ctx: dict[str, Any], step_id: str, output: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": "mn.workflow.step_result.v1",
        "agent_id": step_id,
        "workflow_step_id": step_id,
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
    }


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
    output_folder = expand_path(
        payload.get("output_folder") or (resolved_config.get("outputs") or {}).get("folder_path") or f"~/Downloads/{BLUEPRINT_ID}"
    )
    output_folder.mkdir(parents=True, exist_ok=True)
    run_id_value = run_id or payload.get("run_id") or os.environ.get("MN_RUN_ID") or f"{BLUEPRINT_ID}-{uuid.uuid4().hex[:8]}"
    runs_root_path = Path(runs_root).expanduser().resolve() if runs_root else output_folder / "runs"
    run_dir = runs_root_path / run_id_value
    run_dir.mkdir(parents=True, exist_ok=True)
    llm = llm_client if llm_client is not None else DeterministicLLM()
    state = load_state(run_dir) or {"workflow": {}, "actor_findings": {}, "model_profiles_used": {}}
    return {
        "config": resolved_config,
        "payload": payload,
        "blueprint_dir": root,
        "document_folder": document_folder,
        "output_folder": output_folder,
        "runs_root": runs_root_path,
        "run_dir": run_dir,
        "run_id": run_id_value,
        "llm": llm,
        "state": state,
    }


def run_blueprint(
    inputs: dict[str, Any] | None = None,
    config: dict[str, Any] | None = None,
    runs_root: str | Path | None = None,
    run_id: str | None = None,
    llm_client: Any | None = None,
    config_json: str | None = None,
) -> dict[str, Any]:
    start_agent_beacon_thread(f"{BLUEPRINT_NAME} is running")
    ctx = build_context(
        inputs=inputs,
        config=config,
        config_json=config_json,
        runs_root=runs_root,
        run_id=run_id,
        llm_client=llm_client,
    )
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
        ctx["run_dir"] / "run.json",
        {
            "run_id": ctx["run_id"],
            "blueprint_id": BLUEPRINT_ID,
            "status": "running",
            "started_at": utc_now_iso(),
        },
    )
    append_event(ctx["run_dir"], "blueprint_status", {"status": "running", "component": BLUEPRINT_ID})

    requested_step = runtime_step_id()
    steps_to_run = WORKFLOW_STEPS
    if requested_step:
        steps_to_run = WORKFLOW_STEPS[: WORKFLOW_STEPS.index(requested_step) + 1]

    output: dict[str, Any] = {}
    for step_id in steps_to_run:
        if step_id in ctx["state"].get("workflow", {}) and requested_step and step_id != requested_step:
            continue
        output = run_step(ctx, step_id)

    if requested_step:
        return step_result(ctx, requested_step, output)

    final_output = ctx["state"]["workflow"]["financial_advice_reporter"]
    final_artifact = final_output["final_artifact"]
    result = {
        "run_id": ctx["run_id"],
        "blueprint_id": BLUEPRINT_ID,
        "status": "completed",
        "final_artifact": final_artifact,
        "output_files": final_output["output_files"],
    }
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the unified financial advisor blueprint.")
    parser.add_argument("--input-file", type=Path)
    parser.add_argument("--runs-root", type=Path)
    parser.add_argument("--run-id")
    parser.add_argument("--config-json")
    args = parser.parse_args(argv)

    inputs = None
    if args.input_file:
        loaded = json.loads(args.input_file.read_text(encoding="utf-8"))
        inputs = loaded if isinstance(loaded, dict) else {}
    result = run_blueprint(inputs=inputs, runs_root=args.runs_root, run_id=args.run_id, config_json=args.config_json)
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
