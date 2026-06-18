#!/usr/bin/env python3.11
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from mn_blueprint_support import get_llm_client, start_agent_beacon_thread
except Exception:  # pragma: no cover - optional runtime support
    def start_agent_beacon_thread(message: str | None = None) -> None:
        return None

    def get_llm_client(mode: str | None = None) -> Any:
        return _FallbackLLMClient()

try:
    from mn_blueprint_support import (
        AGENT_EVENT_STDOUT_PREFIX,
        agent_activity_event as support_agent_activity_event,
        emit_agent_activity_stdout as support_emit_agent_activity_stdout,
        redact_observability_value as support_redact_observability_value,
    )
except Exception:  # pragma: no cover - optional runtime support
    AGENT_EVENT_STDOUT_PREFIX = "__MN_EVENT__"
    support_agent_activity_event = None
    support_emit_agent_activity_stdout = None
    support_redact_observability_value = None


BLUEPRINT_ID = "personal_financial_advisor"
BLUEPRINT_NAME = "Personal Financial Advisor"
OUTPUT_TYPE = "personal_financial_advisor_report"
RECOMMENDED_ACTION = "review_household_finance_report_before_any_financial_action"
SUPPORTED_SUFFIXES = {".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp", ".txt", ".json", ".csv"}
TEXT_SUFFIXES = {".txt", ".json", ".csv"}
FIELD_PROFILE = [
    "document_kind",
    "institution_or_merchant",
    "account_or_source",
    "document_date",
    "income_amounts",
    "expense_amounts",
    "recurring_items",
    "balances",
    "debt_or_credit_obligations",
    "fees",
    "risk_flags",
    "recommended_actions",
]
DEFAULT_RESEARCH_SOURCE_URLS = [
    "https://consumer.gov/managing-your-money",
    "https://www.consumerfinance.gov/consumer-tools/bank-accounts/",
    "https://www.consumerfinance.gov/consumer-tools/credit-cards/",
    "https://www.consumerfinance.gov/consumer-tools/debt-collection/",
]
RESEARCH_TOPIC_BY_RISK = {
    "missing_documents": "official consumer guidance organizing household financial records",
    "ocr_review": "official consumer guidance reviewing financial statements for errors",
    "classification": "official consumer guidance organizing financial documents and bills",
    "income_visibility": "official consumer guidance tracking income household budget",
    "cash_flow": "official consumer guidance cash flow budget expenses exceed income",
    "fees": "official consumer guidance avoiding bank account fees overdraft fees",
    "review_required": "official consumer guidance monthly budget review emergency savings",
    "document_hygiene": "official consumer guidance keeping financial records organized",
}
DATASET_INPUT = {
    "name": "AgamiAI Indian Bank Statement Synthetic Dataset",
    "provider": "AgamiAI on Hugging Face",
    "url": "https://huggingface.co/datasets/AgamiAI/Indian-Bank-Statements",
    "license": "Apache 2.0",
    "availability_note": (
        "Public synthetic bank statement sample used only as one finance-document demo source; "
        "real runs can include statements, income docs, receipts, bills, images, text, JSON, and CSV files."
    ),
    "expected_files": sorted(SUPPORTED_SUFFIXES),
    "download_hint": "Use the bundled sample files or fetch a small public sample before trying a larger local folder.",
}
OUTPUT_MESSAGE_BY_STEP = {
    "financial_folder_watcher": "financial_folder_watcher_completed",
    "financial_document_reader": "financial_document_reader_completed",
    "financial_activity_classifier": "financial_activity_classifier_completed",
    "financial_health_assessor": "financial_health_assessor_completed",
    "financial_market_researcher": "financial_market_researcher_completed",
    "financial_advice_reporter": "financial_advice_reporter_completed",
}
RUNTIME_GRAPH_STEP_IDS = set(OUTPUT_MESSAGE_BY_STEP)
ADVISOR_INPUT_KEYS = {
    "document_folder",
    "output_folder",
    "monitoring",
    "field_profile",
    "run_id",
    "watch",
}


def _workspace_root() -> Path | None:
    value = os.environ.get("MN_WORKSPACE_ROOT")
    if value:
        return Path(value).expanduser()
    for parent in Path(__file__).resolve().parents:
        if (parent / "mn-skills").exists():
            return parent
    return None


def _add_repo_paths() -> None:
    roots = []
    if os.environ.get("MN_SKILLS_ROOT"):
        roots.append(Path(os.environ["MN_SKILLS_ROOT"]).expanduser())
    workspace = _workspace_root()
    if workspace:
        roots.append(workspace / "mn-skills")
    for parent in Path(__file__).resolve().parents:
        roots.append(parent / "mn-skills")
    for root in roots:
        for skill_name in ("llm_ocr_skill", "w3m_browser_skill", "blueprint_support_skill"):
            candidate = root / skill_name / "src"
            if candidate.exists() and str(candidate) not in sys.path:
                sys.path.insert(0, str(candidate))


_add_repo_paths()

try:
    from mn_llm_ocr_skill import docker_ocr_client_factory_from_config, extract_document_folder
except Exception:  # pragma: no cover - fallback for minimal local checks
    docker_ocr_client_factory_from_config = None
    extract_document_folder = None

W3mBrowserConfig = None
research_topic = None
browse_url = None
build_search_url = None

try:
    from mn_blueprint_support.context_memory import (
        add_item,
        compile_context,
        compile_context_state,
        context_stub,
        make_content,
    )
except Exception:  # pragma: no cover - optional runtime support
    add_item = None
    compile_context = None
    compile_context_state = None
    context_stub = None
    make_content = None


def _load_w3m_browser_skill() -> None:
    global W3mBrowserConfig, browse_url, build_search_url, research_topic
    if W3mBrowserConfig is not None and research_topic is not None and browse_url is not None and build_search_url is not None:
        return
    try:
        from mn_w3m_browser_skill import W3mBrowserConfig as imported_config
        from mn_w3m_browser_skill import browse_url as imported_browse_url
        from mn_w3m_browser_skill import build_search_url as imported_build_search_url
        from mn_w3m_browser_skill import research_topic as imported_research_topic
    except Exception:  # pragma: no cover - optional outside the research DockerWorker
        return
    W3mBrowserConfig = imported_config
    browse_url = imported_browse_url
    build_search_url = imported_build_search_url
    research_topic = imported_research_topic


class _FallbackLLMClient:
    provider = "fallback"
    model = "deterministic-fallback"

    def __init__(self) -> None:
        self.calls = 0
        self.fallback_calls = 0
        self.prompts: list[dict[str, str]] = []

    def generate_json(self, *, system_prompt: str, user_prompt: str, fallback: dict[str, Any]) -> dict[str, Any]:
        self.calls += 1
        self.fallback_calls += 1
        self.prompts.append({"system": system_prompt, "user": user_prompt})
        response = dict(fallback)
        response.setdefault("confidence", 0.55)
        response.setdefault("rationale", "Deterministic fallback used because the default LLM was unavailable.")
        response["provider"] = self.provider
        response["model"] = self.model
        response["used_fallback"] = True
        return response


def _resolve_llm_client(config: dict[str, Any]) -> Any:
    llm_config = config.get("llm") if isinstance(config.get("llm"), dict) else {}
    if llm_config.get("enabled") is False:
        return get_llm_client("fake")
    mode = str(llm_config.get("mode") or os.environ.get("MN_BLUEPRINT_LLM_MODE") or "live").strip().lower()
    if (
        os.environ.get("MN_BLUEPRINT_QUICK_TEST", "").strip().lower() in {"1", "true", "yes", "on"}
        and bool(llm_config.get("quick_test_uses_fake", False))
    ):
        return get_llm_client("fake")
    if mode in {"fake", "mock", "deterministic"}:
        return get_llm_client("fake")
    _apply_llm_config_env(llm_config)
    try:
        client = get_llm_client(mode if mode not in {"default"} else None)
    except Exception:
        client = _FallbackLLMClient()
    if hasattr(client, "prefer_shared_skill"):
        client.prefer_shared_skill = bool(llm_config.get("prefer_shared_skill", True))
    if hasattr(client, "strict"):
        client.strict = bool(llm_config.get("strict_json", False))
    return client


def _apply_llm_config_env(llm_config: dict[str, Any]) -> None:
    configs = llm_config.get("configs") if isinstance(llm_config.get("configs"), dict) else {}
    default_config = str(llm_config.get("default_config") or "primary")
    primary = configs.get(default_config) if isinstance(configs.get(default_config), dict) else {}
    values = {
        "MN_LLM_API_BASE": llm_config.get("api_base") or primary.get("api_base"),
        "MN_LLM_PROVIDER": llm_config.get("provider") or primary.get("provider"),
        "MN_LLM_MODEL": llm_config.get("model") or primary.get("model"),
        "MN_LLM_TIMEOUT_SECONDS": llm_config.get("timeout_seconds") or primary.get("timeout_seconds"),
        "MN_LLM_MAX_TOKENS": llm_config.get("max_tokens") or primary.get("max_tokens"),
        "MN_LLM_NUM_RETRIES": llm_config.get("num_retries") or primary.get("num_retries"),
    }
    for env_name, value in values.items():
        if value not in (None, "") and not os.environ.get(env_name):
            os.environ[env_name] = str(value)


def _llm_usage(llm: Any) -> dict[str, Any]:
    return {
        "provider": str(getattr(llm, "provider", "unknown")),
        "model": str(getattr(llm, "model", "unknown")),
        "calls": int(getattr(llm, "calls", 0) or 0),
        "fallback_calls": int(getattr(llm, "fallback_calls", 0) or 0),
    }


def _actor_spec(config: dict[str, Any], actor_id: str) -> dict[str, Any]:
    llm_config = config.get("llm") if isinstance(config.get("llm"), dict) else {}
    agents = llm_config.get("agents") if isinstance(llm_config.get("agents"), dict) else {}
    spec = agents.get(actor_id) if isinstance(agents.get(actor_id), dict) else {}
    return {
        "role": spec.get("role") or actor_id.replace("_", " ").title(),
        "responsibilities": spec.get("responsibilities") if isinstance(spec.get("responsibilities"), list) else [],
        "model": spec.get("model") or llm_config.get("model") or "default",
    }


def _actor_generate_json(
    llm: Any,
    config: dict[str, Any],
    actor_id: str,
    stage: str,
    payload: dict[str, Any],
    fallback: dict[str, Any],
) -> dict[str, Any]:
    spec = _actor_spec(config, actor_id)
    system_prompt = (
        f"You are the {spec['role']} for a review-only personal finance coworker. "
        "Return only JSON. Stay source-grounded, preserve privacy, and never recommend moving money, "
        "paying bills, trading, filing taxes, syncing accounts, or sharing reports without human approval."
    )
    user_prompt = json.dumps(
        {
            "actor_id": actor_id,
            "stage": stage,
            "responsibilities": spec["responsibilities"],
            "privacy_rules": [
                "Local LLM prompts may use redacted snippets and structured values.",
                "Public web searches must use only generic risk categories and document types.",
            ],
            "payload": payload,
            "fallback_schema": fallback,
        },
        indent=2,
        sort_keys=True,
        default=str,
    )
    try:
        response = llm.generate_json(system_prompt=system_prompt, user_prompt=user_prompt, fallback=fallback)
    except Exception as exc:
        response = dict(fallback)
        response["llm_error"] = str(exc)
        response["used_fallback"] = True
        if hasattr(llm, "fallback_calls"):
            try:
                llm.fallback_calls += 1
            except Exception:
                pass
    if not isinstance(response, dict):
        response = dict(fallback)
        response["used_fallback"] = True
    merged = dict(fallback)
    for key, value in response.items():
        if value is not None:
            merged[key] = _compact_json_value(value)
    merged["actor_id"] = actor_id
    merged["role"] = spec["role"]
    merged["model"] = spec["model"]
    merged["generated_at"] = utc_now_iso()
    return merged


def _compact_json_value(value: Any, *, string_limit: int = 2000, list_limit: int = 30, dict_limit: int = 40) -> Any:
    if isinstance(value, str):
        return value[:string_limit]
    if isinstance(value, list):
        return [_compact_json_value(item, string_limit=string_limit, list_limit=list_limit, dict_limit=dict_limit) for item in value[:list_limit]]
    if isinstance(value, dict):
        compact: dict[str, Any] = {}
        for index, (key, item) in enumerate(value.items()):
            if index >= dict_limit:
                break
            compact[str(key)] = _compact_json_value(item, string_limit=string_limit, list_limit=list_limit, dict_limit=dict_limit)
        return compact
    return value


def _actor_findings(state: dict[str, Any] | None = None) -> dict[str, Any]:
    if state is None:
        return {}
    findings = state.get("actor_findings")
    if isinstance(findings, dict):
        return findings
    findings = {}
    state["actor_findings"] = findings
    return findings


def _record_actor_finding(state: dict[str, Any], actor_id: str, finding: dict[str, Any]) -> dict[str, Any]:
    findings = _actor_findings(state)
    findings[actor_id] = finding
    return finding


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


def append_event(run_dir: Path, event_type: str, payload: dict[str, Any]) -> None:
    record = {"type": event_type, "timestamp": utc_now_iso(), "payload": payload}
    with (run_dir / "events.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True, default=str) + "\n")


def emit_activity(
    run_dir: Path | None,
    event_type: str,
    *,
    message: str,
    category: str = "agent",
    agent_id: str | None = None,
    step_id: str | None = None,
    status: str | None = None,
    tool_name: str | None = None,
    target: str | None = None,
    duration_ms: int | float | None = None,
    result_summary: str | None = None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    agent_id = agent_id or step_id or _runtime_graph_step_id() or BLUEPRINT_ID
    step_id = step_id or agent_id
    if support_agent_activity_event is not None:
        event = support_agent_activity_event(
            event_type,
            message=message,
            category=category,
            agent_id=agent_id,
            step_id=step_id,
            status=status,
            tool_name=tool_name,
            target=target,
            duration_ms=duration_ms,
            result_summary=result_summary,
            details=details,
        )
    else:
        event = {
            "type": event_type,
            "payload": {
                "schema": "mn.agent.activity.v1",
                "category": category,
                "message": str(message or "")[:300],
                "agent_id": agent_id,
                "step_id": step_id,
                "step": step_id,
                "status": status,
                "tool_name": tool_name,
                "target": target,
                "duration_ms": duration_ms,
                "result_summary": str(result_summary or "")[:700] if result_summary else None,
                "details": _redact_activity_value(details or {}),
                "component": BLUEPRINT_ID,
                "emitted_at": utc_now_iso(),
            },
        }
    payload = {key: value for key, value in dict(event.get("payload") or {}).items() if value not in (None, "", {})}
    payload.setdefault("component", BLUEPRINT_ID)
    payload.setdefault("agent_id", agent_id)
    payload.setdefault("step_id", step_id)
    event = {"type": event_type, "payload": payload}
    if run_dir is not None:
        append_event(run_dir, event_type, payload)
    if _live_runtime_events_enabled():
        if support_emit_agent_activity_stdout is not None:
            support_emit_agent_activity_stdout(event)
        else:
            print(AGENT_EVENT_STDOUT_PREFIX + json.dumps(event, sort_keys=True, default=str), flush=True)
    return event


def emit_actor_activity(
    run_dir: Path | None,
    actor_id: str,
    message: str,
    *,
    status: str = "working",
    details: dict[str, Any] | None = None,
    result_summary: str | None = None,
) -> dict[str, Any]:
    return emit_activity(
        run_dir,
        "agent_activity",
        message=message,
        category="agent",
        agent_id=actor_id,
        step_id=actor_id,
        status=status,
        result_summary=result_summary,
        details=details,
    )


def _redact_activity_value(value: Any) -> Any:
    if support_redact_observability_value is not None:
        return support_redact_observability_value(value)
    if isinstance(value, dict):
        return {str(key): _redact_activity_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact_activity_value(item) for item in value[:25]]
    if isinstance(value, str):
        return redactor(value)[:700]
    return value


def _live_runtime_events_enabled() -> bool:
    return bool(os.environ.get("MN_JOB_ID") or os.environ.get("MN_RUNTIME_DRIVER"))


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def redactor(text: str) -> str:
    value = re.sub(r"\b\d{3}[- ]?\d{2}[- ]?\d{4}\b", "[REDACTED-SSN]", text or "")
    value = re.sub(r"\b(?:\d[ -]*?){13,19}\b", "[REDACTED-CARD]", value)
    value = re.sub(r"\b\d{9,18}\b", "[REDACTED-ID]", value)
    value = re.sub(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "[REDACTED-EMAIL]", value)
    return value


def classifier(text: str, filename: str) -> str:
    haystack = f"{filename}\n{text}".lower()
    if any(token in haystack for token in ("paystub", "payroll", "salary", "wage", "form w-2", "1099", "income")):
        return "income_document"
    if any(token in haystack for token in ("receipt", "merchant", "store", "purchase", "subtotal", "tip")):
        return "receipt"
    if any(token in haystack for token in ("invoice", "bill", "amount due", "due date", "utility")):
        return "bill_or_invoice"
    if any(token in haystack for token in ("credit card", "visa", "mastercard", "statement balance", "minimum payment")):
        return "credit_card_statement"
    if any(token in haystack for token in ("loan", "mortgage", "principal", "apr", "interest rate")):
        return "loan_or_debt_statement"
    if any(token in haystack for token in ("bank statement", "opening balance", "closing balance", "account number", "deposit", "withdrawal")):
        return "bank_statement"
    if any(token in haystack for token in ("form 1040", "schedule c", "tax return", "tax year")):
        return "tax_document"
    if any(token in haystack for token in ("debit", "credit", "balance", "transaction", "expense")):
        return "financial_document"
    return "unknown_financial_document"


def iter_financial_files(folder: Path) -> list[Path]:
    if not folder.exists() or not folder.is_dir():
        return []
    return sorted(
        path
        for path in folder.rglob("*")
        if path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES
    )


def fallback_extract(folder: Path) -> list[dict[str, Any]]:
    records = []
    for path in iter_financial_files(folder):
        warnings: list[str] = []
        text = ""
        ocr_required = path.suffix.lower() not in TEXT_SUFFIXES
        extraction_method = "ocr_required_no_skill" if ocr_required else "embedded_text_fallback"
        if path.suffix.lower() in TEXT_SUFFIXES:
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except Exception as exc:
                warnings.append(str(exc))
                extraction_method = "fallback_read_error"
        else:
            warnings.append("OCR skill was unavailable; file was fingerprinted but not text-extracted.")
        records.append(
            {
                "path": str(path),
                "filename": path.name,
                "document_type": classifier(text, path.name),
                "text": redactor(text),
                "ocr_required": ocr_required,
                "extraction_method": extraction_method,
                "warnings": warnings,
                "metadata": {"suffix": path.suffix.lower(), "size_bytes": _safe_stat(path).get("size_bytes", 0)},
            }
        )
    return records


def extract_records(folder: Path, config: dict[str, Any]) -> list[dict[str, Any]]:
    fallback_records = fallback_extract(folder)
    if extract_document_folder is None:
        return fallback_records

    skill_config = {"input_skills": config.get("input_skills", {})}
    ocr_config = (config.get("input_skills") or {}).get("llm_ocr") or {}
    factory = docker_ocr_client_factory_from_config(skill_config) if docker_ocr_client_factory_from_config else None
    try:
        records = extract_document_folder(
            folder,
            classifier=classifier,
            redactor=redactor,
            llm_ocr_client_factory=factory,
            min_text_chars=int(ocr_config.get("min_text_chars") or 40),
        )
    except Exception as exc:
        fallback_records.append(
            {
                "path": str(folder),
                "filename": folder.name,
                "document_type": "ocr_warning",
                "text": "",
                "ocr_required": True,
                "extraction_method": "fallback_after_ocr_error",
                "warnings": [str(exc)],
                "metadata": {"dataset_input": DATASET_INPUT},
            }
        )
        return fallback_records

    seen = {str(Path(str(record.get("path") or "")).resolve()) for record in records if record.get("path")}
    for record in fallback_records:
        record_path = str(Path(str(record.get("path") or "")).resolve())
        if record_path not in seen:
            records.append(record)
    return records


def _safe_stat(path: Path) -> dict[str, int]:
    try:
        stat = path.stat()
    except OSError:
        return {"size_bytes": 0, "mtime_ns": 0}
    return {"size_bytes": stat.st_size, "mtime_ns": stat.st_mtime_ns}


def fingerprint_file(path: Path) -> dict[str, Any]:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError:
        digest.update(str(path).encode("utf-8"))
    stat = _safe_stat(path)
    return {
        "path": str(path),
        "filename": path.name,
        "size_bytes": stat["size_bytes"],
        "mtime_ns": stat["mtime_ns"],
        "sha256": digest.hexdigest(),
    }


MONEY_RE = re.compile(r"(?<![\w.])(?:USD\s*|US\$\s*|\$\s*)?(-?\d{1,3}(?:,\d{3})+(?:\.\d{2})|-?\d+\.\d{2})(?![\w.])")
INCOME_HINTS = {"salary", "payroll", "paystub", "wage", "income", "deposit", "credit", "1099", "w-2"}
EXPENSE_HINTS = {"receipt", "purchase", "debit", "withdrawal", "payment", "paid", "total", "amount due", "fee", "charge", "bill", "invoice"}
BALANCE_HINTS = {"balance", "opening balance", "closing balance", "available balance", "statement balance"}


def _money(value: float) -> str:
    return f"${value:,.2f}"


def _extract_money_amounts(text: str) -> list[float]:
    amounts = []
    for match in MONEY_RE.finditer(text or ""):
        try:
            amounts.append(float(match.group(1).replace(",", "")))
        except ValueError:
            continue
    return amounts


def _line_amount_entries(records: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    income: list[dict[str, Any]] = []
    expenses: list[dict[str, Any]] = []
    balances: list[dict[str, Any]] = []
    for record in records:
        text = str(record.get("text") or "")
        document_type = str(record.get("document_type") or "")
        for line in text.splitlines() or [text]:
            line_text = line.strip()
            if not line_text:
                continue
            amounts = _extract_money_amounts(line_text)
            if not amounts:
                continue
            lower = line_text.lower()
            entry_base = {
                "source": record.get("filename"),
                "document_type": document_type,
                "line_preview": redactor(line_text[:220]),
            }
            for amount in amounts:
                entry = {**entry_base, "amount": round(abs(amount), 2), "display_amount": _money(abs(amount))}
                if any(hint in lower for hint in BALANCE_HINTS):
                    balances.append(entry)
                elif document_type == "income_document" or any(hint in lower for hint in INCOME_HINTS):
                    income.append(entry)
                elif document_type in {"receipt", "bill_or_invoice", "credit_card_statement", "loan_or_debt_statement"} or any(hint in lower for hint in EXPENSE_HINTS):
                    expenses.append(entry)
    return income, expenses, balances


def build_document_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(str(record.get("document_type") or "unknown") for record in records)
    ocr_required = [str(record.get("filename")) for record in records if record.get("ocr_required")]
    warnings = [
        {"source": record.get("filename"), "warning": warning}
        for record in records
        for warning in (record.get("warnings") or [])
    ]
    return {
        "document_count": len(records),
        "document_types": dict(sorted(counts.items())),
        "ocr_required": ocr_required,
        "warning_count": len(warnings),
        "warnings": warnings[:20],
        "supported_file_types": sorted(SUPPORTED_SUFFIXES),
    }


def summarize_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    evidence = []
    for record in records[:30]:
        text = str(record.get("text") or "")
        evidence.append(
            {
                "source": record.get("filename"),
                "document_type": record.get("document_type"),
                "text_preview": text[:500],
                "ocr_required": bool(record.get("ocr_required")),
                "extraction_method": record.get("extraction_method"),
                "warnings": record.get("warnings") or [],
            }
        )
    if not evidence:
        evidence.append(
            {
                "source": "inputs/public_dataset.json",
                "document_type": "dataset_reference",
                "text_preview": DATASET_INPUT.get("availability_note", ""),
                "ocr_required": False,
                "extraction_method": "public_dataset_note",
                "warnings": ["No local finance documents were processed; add files to the monitored folder and rerun."],
            }
        )
    return evidence


def build_financial_sections(records: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    income_entries, expense_entries, balance_entries = _line_amount_entries(records)
    income_total = round(sum(item["amount"] for item in income_entries), 2)
    expense_total = round(sum(item["amount"] for item in expense_entries), 2)
    net_cash_flow = round(income_total - expense_total, 2)
    savings_rate = round((net_cash_flow / income_total) * 100.0, 2) if income_total > 0 else None

    snapshot = {
        "detected_income_total": _money(income_total),
        "detected_expense_total": _money(expense_total),
        "detected_net_cash_flow": _money(net_cash_flow),
        "savings_rate_estimate_pct": savings_rate,
        "balance_mentions": balance_entries[:12],
        "basis": "Amounts are source-text estimates for review, not a reconciled ledger.",
    }
    income_summary = {
        "total_detected": _money(income_total),
        "entry_count": len(income_entries),
        "entries": income_entries[:20],
        "sources": sorted({str(item.get("source")) for item in income_entries if item.get("source")}),
    }
    expense_summary = {
        "total_detected": _money(expense_total),
        "entry_count": len(expense_entries),
        "entries": expense_entries[:30],
        "sources": sorted({str(item.get("source")) for item in expense_entries if item.get("source")}),
    }
    return snapshot, income_summary, expense_summary


def _risk_item(
    severity: str,
    category: str,
    finding: str,
    advice: str,
    *,
    owner: str = "human_reviewer",
    blocker: bool = False,
) -> dict[str, Any]:
    return {
        "severity": severity,
        "category": category,
        "finding": finding,
        "advice": advice,
        "owner": owner,
        "blocker": blocker,
    }


def build_risk_register(
    records: list[dict[str, Any]],
    document_summary: dict[str, Any],
    income_summary: dict[str, Any],
    expense_summary: dict[str, Any],
) -> list[dict[str, Any]]:
    risks: list[dict[str, Any]] = []
    if not records:
        risks.append(
            _risk_item(
                "high",
                "missing_documents",
                "No finance documents were processed.",
                "Add income records, statements, receipts, bills, or CSV exports to the monitored folder.",
                blocker=True,
            )
        )
    if document_summary["ocr_required"]:
        risks.append(
            _risk_item(
                "medium",
                "ocr_review",
                f"{len(document_summary['ocr_required'])} file(s) required OCR or image/PDF review.",
                "Compare every OCR-derived amount against the source file before relying on the report.",
            )
        )
    if document_summary["document_types"].get("unknown_financial_document"):
        risks.append(
            _risk_item(
                "medium",
                "classification",
                "Some files could not be confidently classified.",
                "Open unknown files and rename or annotate them so the next run can classify them correctly.",
            )
        )
    income_total = _parse_money(income_summary.get("total_detected"))
    expense_total = _parse_money(expense_summary.get("total_detected"))
    if income_total <= 0 and records:
        risks.append(
            _risk_item(
                "medium",
                "income_visibility",
                "No income amounts were detected in the current document set.",
                "Add paystubs, payroll exports, deposit statements, or income summaries before treating cash-flow status as complete.",
            )
        )
    if income_total > 0 and expense_total > income_total:
        risks.append(
            _risk_item(
                "high",
                "cash_flow",
                "Detected expenses exceed detected income for this review packet.",
                "Review discretionary spending, upcoming bills, and missing income documents before making budget decisions.",
                blocker=True,
            )
        )
    if any("fee" in str(record.get("text") or "").lower() for record in records):
        risks.append(
            _risk_item(
                "low",
                "fees",
                "One or more source documents mention fees.",
                "Review bank, card, overdraft, late, or service fees and decide whether any can be avoided next cycle.",
            )
        )
    if not risks:
        risks.append(
            _risk_item(
                "low",
                "review_required",
                "No blocking automated risk was detected, but this remains a draft review packet.",
                "Confirm source documents, amounts, and reminders before taking any financial action.",
            )
        )
    return risks


def _parse_money(value: Any) -> float:
    text = str(value or "0")
    try:
        return float(text.replace("$", "").replace(",", ""))
    except ValueError:
        return 0.0


def build_reminders(records: list[dict[str, Any]], risks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    reminders: list[dict[str, Any]] = []
    for record in records:
        text = str(record.get("text") or "")
        for line in text.splitlines():
            lower = line.lower()
            if "due date" in lower or "payment due" in lower or "minimum payment" in lower:
                reminders.append(
                    {
                        "kind": "payment_or_bill_review",
                        "source": record.get("filename"),
                        "reminder": redactor(line.strip()[:220]),
                        "action": "Confirm due date, amount, autopay status, and available cash before payment.",
                    }
                )
    if any(risk.get("blocker") for risk in risks):
        reminders.append(
            {
                "kind": "human_review",
                "source": "risk_register",
                "reminder": "Blocking review items are present.",
                "action": "Resolve blocker risks before using this report for planning decisions.",
            }
        )
    if not reminders:
        reminders.append(
            {
                "kind": "monthly_review",
                "source": "advisor_policy",
                "reminder": "Schedule a monthly review of income, recurring expenses, fees, debt payments, and emergency cash.",
                "action": "Keep adding receipts, statements, and income records to the monitored folder.",
            }
        )
    return reminders[:20]


def build_advisor_recommendations(risks: list[dict[str, Any]], records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    recommendations = []
    for risk in risks:
        recommendations.append(
            {
                "priority": len(recommendations) + 1,
                "action": risk.get("advice"),
                "reason": risk.get("finding"),
                "risk_category": risk.get("category"),
                "owner": risk.get("owner"),
            }
        )
    if records and not any(item.get("risk_category") == "document_hygiene" for item in recommendations):
        recommendations.append(
            {
                "priority": len(recommendations) + 1,
                "action": "Keep the folder organized by month and document type so future watch cycles can spot changes faster.",
                "reason": "Source-grounded reports improve when documents are complete and easy to classify.",
                "risk_category": "document_hygiene",
                "owner": "human_reviewer",
            }
        )
    return recommendations[:12]


def resolve_research_config(config: dict[str, Any]) -> dict[str, Any]:
    default = {
        "enabled": True,
        "max_queries": 3,
        "max_sources_per_query": 2,
        "timeout_seconds": 12,
        "max_chars": 6000,
        "width": 100,
        "source_urls": DEFAULT_RESEARCH_SOURCE_URLS,
        "use_model_compression": True,
        "token_budget": 6000,
        "target_tokens": 2400,
    }
    input_skill_config = ((config.get("input_skills") or {}).get("w3m_browser") or {})
    research_config = config.get("internet_research") or {}
    merged = deep_merge(default, input_skill_config if isinstance(input_skill_config, dict) else {})
    if isinstance(research_config, dict):
        merged = deep_merge(merged, research_config)
    merged["enabled"] = bool(merged.get("enabled"))
    merged["max_queries"] = max(1, int(merged.get("max_queries") or 3))
    merged["max_sources_per_query"] = max(1, int(merged.get("max_sources_per_query") or 2))
    merged["timeout_seconds"] = max(1, int(merged.get("timeout_seconds") or 12))
    merged["max_chars"] = max(1000, int(merged.get("max_chars") or 6000))
    return merged


def build_research_queries(risks: list[dict[str, Any]], document_summary: dict[str, Any], limit: int) -> list[str]:
    categories = [str(risk.get("category") or "") for risk in risks if isinstance(risk, dict)]
    if document_summary.get("document_types", {}).get("invoice_or_bill"):
        categories.append("cash_flow")
    if document_summary.get("document_types", {}).get("credit_or_loan_statement"):
        categories.append("fees")
    queries: list[str] = []
    for category in categories:
        query = RESEARCH_TOPIC_BY_RISK.get(category)
        if query and query not in queries:
            queries.append(query)
    if not queries:
        queries.append(RESEARCH_TOPIC_BY_RISK["review_required"])
    return queries[:limit]


def _safe_research_inputs(risks: list[dict[str, Any]], document_summary: dict[str, Any], limit: int) -> dict[str, Any]:
    categories = []
    for risk in risks:
        if isinstance(risk, dict) and risk.get("category"):
            category = str(risk.get("category"))
            if category not in categories:
                categories.append(category)
    return {
        "risk_categories": categories[:12],
        "document_types": document_summary.get("document_types", {}),
        "document_count": document_summary.get("document_count", 0),
        "ocr_required_count": len(document_summary.get("ocr_required") or []),
        "default_queries": build_research_queries(risks, document_summary, limit),
    }


def _sanitize_research_queries(queries: Any, fallback: list[str], limit: int) -> list[str]:
    safe: list[str] = []
    blocked = re.compile(r"[$@#]|\b\d{4,}\b|account|routing|ssn|social security|acme|fresh market|community bank", re.I)
    for query in queries if isinstance(queries, list) else []:
        value = " ".join(str(query or "").split())
        if not value or blocked.search(value):
            continue
        if value not in safe:
            safe.append(value[:160])
    for query in fallback:
        if query not in safe:
            safe.append(query)
    return safe[:limit]


def _extract_public_urls(text: str, search_url: str, limit: int) -> list[str]:
    search_host = _url_host(search_url)
    urls: list[str] = []
    for raw in re.findall(r"https?://[^\s<>()\"']+", text or ""):
        url = raw.rstrip("].,;:")
        host = _url_host(url)
        if not host or host == search_host or "duckduckgo.com" in host:
            continue
        if url not in urls:
            urls.append(url)
        if len(urls) >= limit:
            break
    return urls


def _url_host(url: str) -> str:
    match = re.match(r"https?://([^/]+)", str(url or ""))
    return match.group(1).lower() if match else ""


def _select_urls_from_llm(response: dict[str, Any], candidates: list[str], max_sources: int) -> list[str]:
    allowed = set(candidates)
    selected: list[str] = []
    raw_items = response.get("selected_urls") or response.get("urls") or []
    if isinstance(raw_items, list):
        for item in raw_items:
            url = str(item.get("url") if isinstance(item, dict) else item)
            if url in allowed and url not in selected:
                selected.append(url)
            if len(selected) >= max_sources:
                break
    for url in candidates:
        if len(selected) >= max_sources:
            break
        if url not in selected:
            selected.append(url)
    return selected[:max_sources]


def financial_market_researcher(
    risks: list[dict[str, Any]],
    document_summary: dict[str, Any],
    config: dict[str, Any],
    run_id: str,
    llm: Any | None = None,
    run_dir: Path | None = None,
) -> dict[str, Any]:
    actor_id = "financial_market_researcher"
    research_config = resolve_research_config(config)
    if not research_config.get("enabled"):
        emit_actor_activity(
            run_dir,
            actor_id,
            "Browser research is disabled for this run.",
            status="skipped",
            details={"reason": "internet_research.disabled"},
        )
        return {
            "research_summary": "Browser research is disabled for this run.",
            "research_sources": [],
            "research_warnings": ["internet_research.disabled"],
            "research_queries": [],
            "research_plan": {},
            "research_findings": [],
            "context_compression": {"enabled": False, "reason": "research disabled"},
        }
    _load_w3m_browser_skill()
    if W3mBrowserConfig is None or browse_url is None or build_search_url is None:
        emit_actor_activity(
            run_dir,
            actor_id,
            "Browser research could not start because w3m_browser_skill is unavailable.",
            status="failed",
            details={"reason": "w3m_browser_skill unavailable"},
        )
        return {
            "research_summary": "Browser research was requested, but w3m_browser_skill is not available.",
            "research_sources": [],
            "research_warnings": ["w3m_browser_skill unavailable"],
            "research_queries": [],
            "research_plan": {},
            "research_findings": [],
            "context_compression": {"enabled": False, "reason": "w3m_browser_skill unavailable"},
        }

    llm = llm or _resolve_llm_client(config)
    browser_config = W3mBrowserConfig(
        timeout_seconds=research_config["timeout_seconds"],
        max_chars=research_config["max_chars"],
        width=int(research_config.get("width") or 100),
        allow_hosts=tuple(research_config.get("allow_hosts") or ()),
        deny_hosts=tuple(research_config.get("deny_hosts") or ()),
    )
    source_url_fallbacks = [str(url) for url in research_config.get("source_urls") or [] if str(url).strip()]
    safe_inputs = _safe_research_inputs(risks, document_summary, research_config["max_queries"])
    emit_actor_activity(
        run_dir,
        actor_id,
        "Planning privacy-safe public financial research.",
        status="started",
        details={
            "risk_categories": safe_inputs.get("risk_categories", []),
            "document_types": safe_inputs.get("document_types", []),
        },
    )
    plan_fallback = {
        "search_queries": safe_inputs["default_queries"],
        "research_focus": safe_inputs["risk_categories"] or ["review_required"],
        "rationale": "Use generic consumer-finance guidance derived from risk categories and document types.",
    }
    plan = _actor_generate_json(
        llm,
        config,
        "financial_market_researcher",
        "plan_public_research",
        safe_inputs,
        plan_fallback,
    )
    queries = _sanitize_research_queries(plan.get("search_queries"), safe_inputs["default_queries"], research_config["max_queries"])
    emit_actor_activity(
        run_dir,
        actor_id,
        "Research plan created.",
        status="completed",
        details={"queries": queries, "research_focus": plan.get("research_focus") or safe_inputs["risk_categories"]},
    )
    collected_sources: list[dict[str, Any]] = []
    search_pages: list[dict[str, Any]] = []
    warnings: list[str] = []

    def browser_observer(event_type: str, payload: dict[str, Any]) -> None:
        payload = dict(payload or {})
        emit_activity(
            run_dir,
            event_type,
            message=str(payload.get("message") or "Browser tool activity"),
            category=str(payload.get("category") or "tool"),
            agent_id=actor_id,
            step_id=actor_id,
            status=str(payload.get("status") or ""),
            tool_name=str(payload.get("tool_name") or "w3m"),
            target=str(payload.get("target") or ""),
            duration_ms=payload.get("duration_ms"),
            result_summary=str(payload.get("result_summary") or ""),
            details=payload.get("details") if isinstance(payload.get("details"), dict) else {},
        )

    def browse_with_observer(url: str) -> dict[str, Any]:
        try:
            return browse_url(url, browser_config, observer=browser_observer)
        except TypeError:
            browser_observer(
                "tool_call_started",
                {"message": f"Browsing {url}", "category": "tool", "tool_name": "w3m", "target": url, "status": "started"},
            )
            result = browse_url(url, browser_config)
            browser_observer(
                "tool_call_completed" if result.get("status") == "ok" else "tool_call_failed",
                {
                    "message": f"Browsed {url}" if result.get("status") == "ok" else f"Could not browse {url}",
                    "category": "tool" if result.get("status") == "ok" else "error",
                    "tool_name": "w3m",
                    "target": url,
                    "status": result.get("status"),
                    "result_summary": result.get("snippet") or result.get("error") or "",
                    "details": {"title": result.get("title"), "returncode": result.get("returncode")},
                },
            )
            return result

    for query in queries:
        search_url = build_search_url(query, browser_config)
        emit_actor_activity(
            run_dir,
            actor_id,
            "Searching DuckDuckGo for public financial guidance.",
            status="working",
            details={"query": query, "search_url": search_url},
        )
        search_page = browse_with_observer(search_url)
        if search_page.get("status") != "ok":
            warnings.append(f"{search_url}: {search_page.get('error') or search_page.get('status')}")
            candidates = source_url_fallbacks[: research_config["max_sources_per_query"]]
        else:
            candidates = _extract_public_urls(str(search_page.get("text") or ""), search_url, limit=12)
        if not candidates:
            candidates = source_url_fallbacks[: research_config["max_sources_per_query"]]
        if search_page.get("status") != "ok" and not candidates:
            continue
        emit_actor_activity(
            run_dir,
            actor_id,
            "Candidate public sources collected.",
            status="working",
            details={"query": query, "candidate_count": len(candidates), "candidate_urls": candidates[:6]},
        )
        search_pages.append(
            {
                "query": query,
                "search_url": search_url,
                "candidate_urls": candidates,
                "snippet": str(search_page.get("snippet") or search_page.get("text") or "")[:700],
            }
        )
        select_fallback = {
            "selected_urls": candidates[: research_config["max_sources_per_query"]],
            "rationale": "Use the first public result URLs from the text browser search page.",
        }
        selection = _actor_generate_json(
            llm,
            config,
            "financial_market_researcher",
            "select_public_sources",
            {
                "query": query,
                "search_url": search_url,
                "candidate_urls": candidates,
                "candidate_count": len(candidates),
            },
            select_fallback,
        )
        for url in _select_urls_from_llm(selection, candidates, research_config["max_sources_per_query"]):
            emit_actor_activity(
                run_dir,
                actor_id,
                "Browsing selected public source.",
                status="working",
                details={"query": query, "url": url},
            )
            source = browse_with_observer(url)
            if source.get("status") != "ok":
                warnings.append(f"{url}: {source.get('error') or source.get('status')}")
                continue
            source_url = str(source.get("url") or url)
            if any(existing.get("url") == source_url for existing in collected_sources):
                continue
            collected_sources.append(
                {
                    "query": query,
                    "url": source_url,
                    "title": str(source.get("title") or source_url)[:200],
                    "snippet": redactor(str(source.get("snippet") or source.get("text") or ""))[:700],
                }
            )
            emit_actor_activity(
                run_dir,
                actor_id,
                "Public source captured.",
                status="completed",
                details={
                    "query": query,
                    "url": source_url,
                    "title": str(source.get("title") or source_url)[:200],
                },
                result_summary=redactor(str(source.get("snippet") or source.get("text") or ""))[:500],
            )

    findings_fallback = {
        "summary": "No public web research source text was collected." if not collected_sources else "\n".join(
            f"{source.get('title')}: {source.get('snippet')}" for source in collected_sources[:6]
        ),
        "findings": [
            {
                "topic": source.get("query", ""),
                "finding": source.get("snippet", ""),
                "source_url": source.get("url", ""),
            }
            for source in collected_sources[:10]
        ],
        "warnings": warnings,
    }
    findings = _actor_generate_json(
        llm,
        config,
        "financial_market_researcher",
        "summarize_public_research",
        {
            "research_plan": {
                "search_queries": queries,
                "research_focus": plan.get("research_focus") or safe_inputs["risk_categories"],
                "search_pages": search_pages,
            },
            "sources": collected_sources,
            "warnings": warnings,
        },
        findings_fallback,
    )
    summary = str(findings.get("summary") or findings_fallback["summary"]).strip()
    compression = compile_research_context(run_id, summary, collected_sources, config, research_config)
    emit_actor_activity(
        run_dir,
        actor_id,
        "Financial market research completed.",
        status="completed",
        details={
            "query_count": len(queries),
            "source_count": len(collected_sources),
            "warning_count": len(warnings),
            "source_urls": [source.get("url") for source in collected_sources[:10]],
        },
        result_summary=summary[:700],
    )
    return {
        "research_summary": summary,
        "research_plan": {
            "search_queries": queries,
            "research_focus": plan.get("research_focus") or safe_inputs["risk_categories"],
            "search_pages": search_pages,
            "rationale": plan.get("rationale", ""),
        },
        "research_findings": findings.get("findings") if isinstance(findings.get("findings"), list) else findings_fallback["findings"],
        "research_sources": collected_sources[:20],
        "research_warnings": warnings[:20],
        "research_queries": queries,
        "context_compression": compression,
    }


def compile_research_context(
    run_id: str,
    summary: str,
    sources: list[dict[str, Any]],
    config: dict[str, Any],
    research_config: dict[str, Any],
) -> dict[str, Any]:
    memory = config.get("memory_layer") or config.get("memory") or {}
    conversation = memory.get("conversation") or {}
    use_model_compression = bool(
        research_config.get("use_model_compression", conversation.get("use_model_compression", False))
    )
    if not use_model_compression:
        return {"enabled": False, "use_model_compression": False}
    if not all([context_stub, make_content, add_item, compile_context, compile_context_state]):
        return {
            "enabled": False,
            "use_model_compression": True,
            "warning": "Membrane context helpers are unavailable",
        }
    try:
        stub = context_stub()
        focus_id = f"{run_id}_financial_research"
        content = make_content(
            goal_id=focus_id,
            artifact_type="financial_research_context",
            payload={"summary": summary, "sources": sources},
            allow_roles=["financial_advisor", "otterdesk_chat"],
            source_refs=[source["url"] for source in sources if source.get("url")],
            validation={"review_only": True, "private_document_text_used_in_queries": False},
        )
        add_item(stub, run_id, focus_id, "Fact", "validated", BLUEPRINT_ID, content, confidence=0.8)
        compiled = compile_context(
            stub,
            run_id,
            "financial_advisor",
            focus_id,
            token_budget=int(research_config.get("token_budget") or conversation.get("token_budget") or 6000),
            target_tokens=int(research_config.get("target_tokens") or conversation.get("target_tokens") or 2400),
            objective="Summarize public financial guidance for a review-only household finance report.",
            current_subtask="Use source-grounded public research without exposing private customer document text.",
            use_model_compression=True,
        )
        state = compile_context_state(compiled)
        state["enabled"] = True
        state["use_model_compression"] = True
        return state
    except Exception as exc:  # pragma: no cover - depends on optional runtime service
        return {"enabled": False, "use_model_compression": True, "warning": str(exc)}


def build_final_artifact(
    records: list[dict[str, Any]],
    watch_state: dict[str, Any],
    run_id: str,
    research: dict[str, Any] | None = None,
    actor_findings: dict[str, Any] | None = None,
    llm_usage: dict[str, Any] | None = None,
) -> dict[str, Any]:
    document_summary = build_document_summary(records)
    financial_snapshot, income_summary, expense_summary = build_financial_sections(records)
    risks = build_risk_register(records, document_summary, income_summary, expense_summary)
    recommendations = build_advisor_recommendations(risks, records)
    reminders = build_reminders(records, risks)
    research = research or {
        "research_summary": "No browser research was run for this cycle.",
        "research_sources": [],
        "research_warnings": [],
        "research_queries": [],
        "research_plan": {},
        "research_findings": [],
        "context_compression": {"enabled": False, "reason": "not requested"},
    }
    actor_findings = actor_findings or {}
    blocker_count = sum(1 for risk in risks if risk.get("blocker"))
    status = "waiting_for_documents" if not records else ("needs_review" if blocker_count else "review_ready")
    confidence = 0.35 if not records else (0.62 if document_summary["ocr_required"] else 0.78)
    reporter = actor_findings.get("financial_advice_reporter") if isinstance(actor_findings.get("financial_advice_reporter"), dict) else {}
    final_artifact = {
        "type": OUTPUT_TYPE,
        "title": "Personal Financial Advisor Report",
        "status": status,
        "executive_summary": reporter.get("executive_summary") or (
            f"{BLUEPRINT_NAME} processed {len(records)} finance document record(s), "
            f"estimated detected income at {income_summary['total_detected']} and detected expenses at {expense_summary['total_detected']}, "
            "and prepared a review-only household finance report."
        ),
        "advisor_message": reporter.get("advisor_message") or _advisor_message(status, risks, financial_snapshot),
        "recommended_action": RECOMMENDED_ACTION,
        "confidence": confidence,
        "evidence": summarize_records(records),
        "document_summary": document_summary,
        "financial_snapshot": financial_snapshot,
        "income_summary": income_summary,
        "expense_summary": expense_summary,
        "risk_register": risks,
        "advisor_recommendations": recommendations,
        "reminders": reminders,
        "research_summary": research.get("research_summary", ""),
        "research_plan": research.get("research_plan", {}),
        "research_findings": research.get("research_findings", []),
        "research_sources": research.get("research_sources", []),
        "research_warnings": research.get("research_warnings", []),
        "research_queries": research.get("research_queries", []),
        "context_compression": research.get("context_compression", {}),
        "actor_findings": actor_findings,
        "llm_usage": llm_usage or {},
        "next_steps": reporter.get("next_steps") if isinstance(reporter.get("next_steps"), list) else [item["action"] for item in recommendations[:5] if item.get("action")],
        "source_refs": ["inputs.json", "events.jsonl", "result.json", "final_artifact.json"],
        "dataset_input": DATASET_INPUT,
        "field_profile": FIELD_PROFILE,
        "watch_state": watch_state,
        "review_only": True,
        "human_review_required": True,
        "safety_boundary": [
            "Does not move money.",
            "Does not pay bills.",
            "Does not place trades.",
            "Does not file taxes.",
            "Does not sync accounting or banking systems.",
            "Does not share reports without human approval.",
        ],
        "run_id": run_id,
        "generated_at": utc_now_iso(),
    }
    return final_artifact


def _advisor_message(status: str, risks: list[dict[str, Any]], snapshot: dict[str, Any]) -> str:
    if status == "waiting_for_documents":
        return (
            "I am ready to watch the folder, but I did not find usable finance documents yet. "
            "Add income records, statements, receipts, bills, or CSV exports and rerun the scan."
        )
    risk_sentence = "No blocker was detected." if not any(risk.get("blocker") for risk in risks) else "There are blocker items to review first."
    return (
        "I took a first pass through the folder and prepared a source-grounded household finance snapshot. "
        f"Detected net cash flow is {snapshot['detected_net_cash_flow']}. {risk_sentence} "
        "Treat this as a review packet, not final financial advice."
    )


def write_output_folder_artifacts(
    final_artifact: dict[str, Any],
    output_folder: Path,
    run_id: str,
    cycle: int,
) -> list[dict[str, str]]:
    output_folder.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    stem = _safe_filename(f"{run_id}-cycle-{cycle}-{timestamp}")
    json_path = output_folder / f"{stem}-final-artifact.json"
    markdown_path = output_folder / f"{stem}-report.md"
    stable_json_path = output_folder / "final_artifact.json"
    stable_markdown_path = output_folder / "final_report.md"
    action_ledger_path = output_folder / "action_ledger.json"
    artifact_quality_path = output_folder / "artifact_quality.json"
    run_health_path = output_folder / "run_health.json"
    artifact_quality = build_output_artifact_quality(final_artifact)
    run_health = build_output_run_health(final_artifact, run_id, cycle, artifact_quality)
    action_ledger = build_output_action_ledger(final_artifact)
    output_files = [
        {"kind": "final_artifact_json", "path": str(json_path)},
        {"kind": "report_markdown", "path": str(markdown_path)},
        {"kind": "latest_final_artifact_json", "path": str(stable_json_path)},
        {"kind": "latest_report_markdown", "path": str(stable_markdown_path)},
        {"kind": "action_ledger_json", "path": str(action_ledger_path)},
        {"kind": "artifact_quality_json", "path": str(artifact_quality_path)},
        {"kind": "run_health_json", "path": str(run_health_path)},
    ]
    final_artifact["output_files"] = output_files
    final_artifact["artifact_quality"] = artifact_quality
    final_artifact["run_health"] = run_health
    final_artifact["action_ledger"] = action_ledger
    write_json(json_path, final_artifact)
    report_markdown = render_markdown_report(final_artifact)
    markdown_path.write_text(report_markdown, encoding="utf-8")
    write_json(stable_json_path, final_artifact)
    stable_markdown_path.write_text(report_markdown, encoding="utf-8")
    write_json(action_ledger_path, action_ledger)
    write_json(artifact_quality_path, artifact_quality)
    write_json(run_health_path, run_health)
    return output_files


def build_output_artifact_quality(final_artifact: dict[str, Any]) -> dict[str, Any]:
    doc_summary = final_artifact.get("document_summary") if isinstance(final_artifact.get("document_summary"), dict) else {}
    risks = [risk for risk in final_artifact.get("risk_register", []) if isinstance(risk, dict)]
    blockers = [risk for risk in risks if risk.get("blocker")]
    warnings = []
    if not doc_summary.get("document_count"):
        warnings.append("No supported finance documents were processed.")
    if doc_summary.get("ocr_required"):
        warnings.append("Some documents require OCR/source review before financial values are trusted.")
    if blockers:
        warnings.append(f"{len(blockers)} blocker risk(s) require human review before action.")
    return {
        "schema_version": "mn.blueprint.artifact_quality.v1",
        "status": "usable_with_review_warnings" if warnings else "usable_with_review",
        "confidence": final_artifact.get("confidence"),
        "review_required": True,
        "warnings": warnings,
        "quality_checks": [
            {"name": "documents_processed", "passed": bool(doc_summary.get("document_count"))},
            {"name": "cash_flow_snapshot_present", "passed": bool(final_artifact.get("financial_snapshot"))},
            {"name": "risk_register_present", "passed": bool(final_artifact.get("risk_register"))},
            {"name": "human_review_boundary_present", "passed": bool(final_artifact.get("safety_boundary"))},
        ],
        "highest_priority_issue": warnings[0] if warnings else "Review-only financial packet is ready for household review.",
    }


def build_output_run_health(
    final_artifact: dict[str, Any],
    run_id: str,
    cycle: int,
    artifact_quality: dict[str, Any],
) -> dict[str, Any]:
    warnings = list(artifact_quality.get("warnings") or [])
    research_sources = final_artifact.get("research_sources") if isinstance(final_artifact.get("research_sources"), list) else []
    return {
        "schema_version": "mn.blueprint.run_health.v1",
        "status": "completed_with_warnings" if warnings else "completed",
        "run_id": run_id,
        "cycle": cycle,
        "generated_at": final_artifact.get("generated_at") or utc_now_iso(),
        "warning_count": len(warnings),
        "research_source_count": len(research_sources),
        "llm": final_artifact.get("llm_usage", {}),
    }


def build_output_action_ledger(final_artifact: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "step": "documents_read",
            "status": "completed",
            "details": final_artifact.get("document_summary", {}),
        },
        {
            "step": "cash_flow_snapshot_built",
            "status": "completed",
            "details": final_artifact.get("financial_snapshot", {}),
        },
        {
            "step": "risk_register_and_reminders_prepared",
            "status": "completed",
            "details": {
                "risk_count": len(final_artifact.get("risk_register") or []),
                "reminder_count": len(final_artifact.get("reminders") or []),
            },
        },
        {
            "step": "human_review_gate",
            "status": "blocked_pending_review",
            "details": {
                "human_review_required": True,
                "blocked_actions": final_artifact.get("safety_boundary", []),
            },
        },
    ]


def render_markdown_report(final_artifact: dict[str, Any]) -> str:
    snapshot = final_artifact.get("financial_snapshot") if isinstance(final_artifact.get("financial_snapshot"), dict) else {}
    doc_summary = final_artifact.get("document_summary") if isinstance(final_artifact.get("document_summary"), dict) else {}
    income = final_artifact.get("income_summary") if isinstance(final_artifact.get("income_summary"), dict) else {}
    expenses = final_artifact.get("expense_summary") if isinstance(final_artifact.get("expense_summary"), dict) else {}
    watch = final_artifact.get("watch_state") if isinstance(final_artifact.get("watch_state"), dict) else {}
    lines = [
        "# Personal Financial Advisor Report",
        "",
        f"**Status:** {final_artifact.get('status', 'needs_review')}",
        "",
        str(final_artifact.get("advisor_message") or ""),
        "",
        "## Cash-Flow Snapshot",
        "",
        f"- Detected income: {snapshot.get('detected_income_total', '$0.00')}",
        f"- Detected expenses: {snapshot.get('detected_expense_total', '$0.00')}",
        f"- Detected net cash flow: {snapshot.get('detected_net_cash_flow', '$0.00')}",
        f"- Savings rate estimate: {snapshot.get('savings_rate_estimate_pct', 'n/a')}",
        "",
        "## Document Status",
        "",
        f"- Documents processed: {doc_summary.get('document_count', 0)}",
        f"- OCR/image review required: {len(doc_summary.get('ocr_required') or [])}",
        f"- Watch mode: {watch.get('mode', 'one_shot')}",
        f"- New or changed files: {len(watch.get('new_or_changed_files') or [])}",
        "",
        "## Income Sources",
        "",
    ]
    lines.extend(_markdown_table(["Source", "Amount", "Evidence"], _amount_rows(income.get("entries"))))
    lines.extend(["", "## Expenses And Bills", ""])
    lines.extend(_markdown_table(["Source", "Amount", "Evidence"], _amount_rows(expenses.get("entries"))))
    lines.extend(["", "## Risk Reminders", ""])
    lines.extend(
        _markdown_table(
            ["Severity", "Category", "Finding", "Advice"],
            [
                [risk.get("severity", ""), risk.get("category", ""), risk.get("finding", ""), risk.get("advice", "")]
                for risk in final_artifact.get("risk_register", [])
                if isinstance(risk, dict)
            ],
        )
    )
    lines.extend(["", "## Research Context", ""])
    lines.append(str(final_artifact.get("research_summary") or "No public web research was collected."))
    if final_artifact.get("research_findings"):
        lines.extend(["", "### Research Findings", ""])
        lines.extend(
            _markdown_table(
                ["Topic", "Finding", "Source"],
                [
                    [
                        finding.get("topic", ""),
                        finding.get("finding", ""),
                        finding.get("source_url", ""),
                    ]
                    for finding in final_artifact.get("research_findings", [])
                    if isinstance(finding, dict)
                ],
            )
        )
    lines.extend(["", "### Research Sources", ""])
    lines.extend(
        _markdown_table(
            ["Source", "Query", "Snippet"],
            [
                [
                    source.get("title") or source.get("url", ""),
                    source.get("query", ""),
                    f"{source.get('url', '')}<br>{source.get('snippet', '')}",
                ]
                for source in final_artifact.get("research_sources", [])
                if isinstance(source, dict)
            ],
        )
    )
    if final_artifact.get("research_warnings"):
        lines.extend(["", "### Research Warnings", ""])
        for warning in final_artifact.get("research_warnings", []):
            lines.append(f"- {warning}")
    if final_artifact.get("actor_findings"):
        lines.extend(["", "## Actor Findings", ""])
        actor_rows = []
        for actor_id, finding in (final_artifact.get("actor_findings") or {}).items():
            if isinstance(finding, dict):
                actor_rows.append(
                    [
                        actor_id,
                        finding.get("summary") or finding.get("rationale") or finding.get("status") or "",
                        finding.get("confidence", ""),
                    ]
                )
        lines.extend(_markdown_table(["Actor", "Finding", "Confidence"], actor_rows))
    lines.extend(["", "## Advisor Recommendations", ""])
    for item in final_artifact.get("advisor_recommendations", []):
        if isinstance(item, dict):
            lines.append(f"- P{item.get('priority')}: {item.get('action')} ({item.get('reason')})")
    lines.extend(["", "## Reminders", ""])
    for reminder in final_artifact.get("reminders", []):
        if isinstance(reminder, dict):
            lines.append(f"- **{reminder.get('kind', 'review')}:** {reminder.get('reminder', '')} Action: {reminder.get('action', '')}")
    lines.extend(
        [
            "",
            "## Source Evidence",
            "",
        ]
    )
    lines.extend(
        _markdown_table(
            ["Source", "Type", "Method", "Preview"],
            [
                [
                    evidence.get("source", ""),
                    evidence.get("document_type", ""),
                    evidence.get("extraction_method", ""),
                    evidence.get("text_preview", ""),
                ]
                for evidence in final_artifact.get("evidence", [])
                if isinstance(evidence, dict)
            ],
        )
    )
    lines.extend(["", "This is a review-only report. Do not use it to move money, pay bills, place trades, file taxes, or share financial information without human approval.", ""])
    return "\n".join(lines)


def _amount_rows(entries: Any) -> list[list[Any]]:
    rows = []
    for entry in entries or []:
        if isinstance(entry, dict):
            rows.append([entry.get("source", ""), entry.get("display_amount", ""), entry.get("line_preview", "")])
    return rows


def _markdown_table(headers: list[str], rows: list[list[Any]]) -> list[str]:
    if not rows:
        rows = [["None" for _ in headers]]
    lines = [
        "| " + " | ".join(_markdown_cell(header) for header in headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        padded = [*row, *[""] * (len(headers) - len(row))]
        lines.append("| " + " | ".join(_markdown_cell(cell) for cell in padded[: len(headers)]) + " |")
    return lines


def _markdown_cell(value: Any) -> str:
    return str(value or "").replace("|", "\\|").replace("\n", "<br>")


def _safe_filename(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip(".-")
    return safe or "personal_financial_advisor-report"


def resolve_runtime_inputs(resolved_config: dict[str, Any], inputs: dict[str, Any] | None) -> dict[str, Any]:
    payload = dict((resolved_config.get("inputs") or {}).get("payload") or {})
    if inputs:
        payload = deep_merge(payload, inputs)
    return payload


def resolve_monitoring(resolved_config: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    monitoring = dict(resolved_config.get("monitoring") or {})
    payload_monitoring = payload.get("monitoring")
    if isinstance(payload_monitoring, dict):
        monitoring = deep_merge(monitoring, payload_monitoring)
    if "watch" in payload:
        monitoring["enabled"] = bool(payload.get("watch"))
    monitoring["enabled"] = bool(monitoring.get("enabled"))
    monitoring["poll_interval_seconds"] = max(1, int(monitoring.get("poll_interval_seconds") or 60))
    max_cycles = monitoring.get("max_cycles")
    monitoring["max_cycles"] = int(max_cycles) if str(max_cycles).strip().isdigit() else None
    return monitoring


def resolve_document_folder(payload: dict[str, Any], blueprint_dir: Path) -> Path:
    configured = str(payload.get("document_folder") or "").strip()
    if configured:
        return Path(configured).expanduser()
    return blueprint_dir / "examples" / "sample_inputs"


def _runtime_json_from_env(*env_names: str) -> dict[str, Any]:
    for env_name in env_names:
        raw_path = os.environ.get(env_name)
        if not raw_path:
            continue
        path = Path(raw_path)
        if not path.exists():
            continue
        try:
            decoded = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(decoded, dict):
            return decoded
    return {}


def _runtime_message_envelope() -> dict[str, Any]:
    return _runtime_json_from_env("MN_MESSAGE_FILE", "MIRROR_NEURON_MESSAGE_FILE")


def _runtime_context_payload() -> dict[str, Any]:
    return _runtime_json_from_env("MN_CONTEXT_FILE", "MIRROR_NEURON_CONTEXT_FILE")


def _runtime_message_payload() -> dict[str, Any]:
    payload = _find_advisor_payload(_runtime_message_envelope())
    return payload if payload else {}


def _find_advisor_payload(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    if any(key in value for key in ADVISOR_INPUT_KEYS):
        return {key: value[key] for key in ADVISOR_INPUT_KEYS if key in value}
    for key in ("payload", "input", "body", "data", "message", "content", "outputs"):
        payload = _find_advisor_payload(value.get(key))
        if payload:
            return payload
    return {}


def _runtime_graph_step_id() -> str:
    context = _runtime_context_payload()
    message = _runtime_message_envelope()
    candidates = [
        os.environ.get("MN_WORKFLOW_STEP_ID", ""),
        os.environ.get("MN_AGENT_ID", ""),
        os.environ.get("MN_NODE_ID", ""),
        os.environ.get("MIRROR_NEURON_AGENT_ID", ""),
        os.environ.get("MIRROR_NEURON_NODE_ID", ""),
        str(context.get("workflow_step_id") or ""),
        str(context.get("agent_id") or ""),
        str(context.get("node_id") or ""),
        str(message.get("to") or ""),
    ]
    for candidate in candidates:
        step_id = candidate.strip()
        if step_id in RUNTIME_GRAPH_STEP_IDS:
            return step_id
    return ""


def _workflow_state_path(run_dir: Path) -> Path:
    return run_dir / "workflow_state.json"


def _load_workflow_state(run_dir: Path) -> dict[str, Any]:
    return read_json(_workflow_state_path(run_dir))


def _save_workflow_state(run_dir: Path, state: dict[str, Any]) -> None:
    state["updated_at"] = utc_now_iso()
    write_json(_workflow_state_path(run_dir), state)


def _runtime_step_result(
    step_id: str,
    run_id: str,
    output_message_type: str,
    outputs: dict[str, Any],
    *,
    status: str = "completed",
    summary: str | None = None,
) -> dict[str, Any]:
    now = utc_now_iso()
    return {
        "schema": "mn.workflow.step_result.v1",
        "agent_id": step_id,
        "workflow_step_id": step_id,
        "blueprint": BLUEPRINT_ID,
        "status": status,
        "output_message_type": output_message_type,
        "summary": summary or f"{step_id.replace('_', ' ').title()} completed.",
        "run": {
            "run_id": run_id,
            "started_at": now,
            "ended_at": now,
            "status": status,
        },
        "outputs": outputs,
    }


def _watch_state_for_step(document_folder: Path, monitoring: dict[str, Any], cycle: int = 1) -> dict[str, Any]:
    fingerprints = {str(path): fingerprint_file(path) for path in iter_financial_files(document_folder)}
    return {
        "mode": "watch" if monitoring.get("enabled") else "one_shot",
        "cycles_completed": cycle,
        "processed_files": list(fingerprints.values()),
        "new_or_changed_files": list(fingerprints.values()),
        "poll_interval_seconds": monitoring.get("poll_interval_seconds") if monitoring.get("enabled") else None,
        "last_scan_at": utc_now_iso(),
    }


def _state_records(state: dict[str, Any]) -> list[dict[str, Any]]:
    records = state.get("records")
    return records if isinstance(records, list) else []


def _classification_from_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    document_summary = build_document_summary(records)
    financial_snapshot, income_summary, expense_summary = build_financial_sections(records)
    return {
        "document_summary": document_summary,
        "financial_snapshot": financial_snapshot,
        "income_summary": income_summary,
        "expense_summary": expense_summary,
    }


def _assessment_from_state(state: dict[str, Any]) -> dict[str, Any]:
    records = _state_records(state)
    document_summary = state.get("document_summary") if isinstance(state.get("document_summary"), dict) else None
    income_summary = state.get("income_summary") if isinstance(state.get("income_summary"), dict) else None
    expense_summary = state.get("expense_summary") if isinstance(state.get("expense_summary"), dict) else None
    if not all([document_summary, income_summary, expense_summary]):
        sections = _classification_from_records(records)
        document_summary = sections["document_summary"]
        income_summary = sections["income_summary"]
        expense_summary = sections["expense_summary"]
    risks = build_risk_register(records, document_summary, income_summary, expense_summary)
    return {
        "risk_register": risks,
        "advisor_recommendations": build_advisor_recommendations(risks, records),
        "reminders": build_reminders(records, risks),
    }


def _run_financial_folder_watcher_actor(llm: Any, config: dict[str, Any], watch_state: dict[str, Any], document_folder: Path) -> dict[str, Any]:
    file_count = len(watch_state.get("processed_files") or [])
    fallback = {
        "status": "ready" if file_count else "waiting_for_documents",
        "summary": f"Folder watcher saw {file_count} supported finance file(s).",
        "attention_items": ["Add finance documents to the watched folder."] if not file_count else [],
        "confidence": 0.82 if file_count else 0.45,
    }
    return _actor_generate_json(
        llm,
        config,
        "financial_folder_watcher",
        "watch_folder",
        {
            "document_folder": str(document_folder),
            "file_count": file_count,
            "changed_file_count": len(watch_state.get("new_or_changed_files") or []),
            "supported_file_types": sorted(SUPPORTED_SUFFIXES),
        },
        fallback,
    )


def _run_financial_document_reader_actor(llm: Any, config: dict[str, Any], records: list[dict[str, Any]]) -> dict[str, Any]:
    document_summary = build_document_summary(records)
    fallback = {
        "summary": f"Document reader processed {len(records)} record(s) and preserved OCR metadata for review.",
        "document_notes": [
            {
                "source": item.get("source"),
                "document_type": item.get("document_type"),
                "review_note": item.get("warnings", ["Ready for source review"])[0] if item.get("warnings") else "Ready for source review",
            }
            for item in summarize_records(records)[:12]
        ],
        "confidence": 0.72 if records else 0.35,
    }
    return _actor_generate_json(
        llm,
        config,
        "financial_document_reader",
        "read_financial_documents",
        {"document_summary": document_summary, "redacted_evidence": summarize_records(records)[:12]},
        fallback,
    )


def _run_financial_activity_classifier_actor(llm: Any, config: dict[str, Any], sections: dict[str, Any]) -> dict[str, Any]:
    fallback = {
        "summary": "Activity classifier organized detected income, expenses, balances, and document categories.",
        "allowed_categories": sorted(
            {
                "income_document",
                "receipt",
                "bill_or_invoice",
                "credit_card_statement",
                "loan_or_debt_statement",
                "bank_statement",
                "tax_document",
                "financial_document",
                "unknown_financial_document",
            }
        ),
        "confidence": 0.74,
    }
    return _actor_generate_json(
        llm,
        config,
        "financial_activity_classifier",
        "financial_activity_classifier_review",
        sections,
        fallback,
    )


def _run_financial_health_assessor_actor(
    llm: Any,
    config: dict[str, Any],
    assessment: dict[str, Any],
    sections: dict[str, Any],
) -> dict[str, Any]:
    fallback = {
        "summary": f"Health assessor found {len(assessment.get('risk_register') or [])} review risk(s).",
        "review_questions": [
            "Are all income sources for this period included?",
            "Have OCR-derived amounts been checked against source files?",
            "Are due dates, fees, and minimum payments confirmed before acting?",
        ],
        "confidence": 0.72,
    }
    return _actor_generate_json(
        llm,
        config,
        "financial_health_assessor",
        "financial_health_assessor_review",
        {
            "financial_snapshot": sections.get("financial_snapshot", {}),
            "document_summary": sections.get("document_summary", {}),
            "risk_register": assessment.get("risk_register", []),
            "advisor_recommendations": assessment.get("advisor_recommendations", []),
            "reminders": assessment.get("reminders", []),
        },
        fallback,
    )


def _run_financial_advice_reporter_actor(llm: Any, config: dict[str, Any], final_artifact: dict[str, Any]) -> dict[str, Any]:
    fallback = {
        "summary": "Advice reporter prepared the review-only household finance report.",
        "executive_summary": final_artifact.get("executive_summary", ""),
        "advisor_message": final_artifact.get("advisor_message", ""),
        "next_steps": final_artifact.get("next_steps", []),
        "confidence": final_artifact.get("confidence", 0.7),
    }
    return _actor_generate_json(
        llm,
        config,
        "financial_advice_reporter",
        "financial_advice_reporter_review",
        {
            "status": final_artifact.get("status"),
            "document_summary": final_artifact.get("document_summary"),
            "financial_snapshot": final_artifact.get("financial_snapshot"),
            "risk_register": final_artifact.get("risk_register"),
            "research_summary": final_artifact.get("research_summary"),
            "research_findings": final_artifact.get("research_findings"),
            "safety_boundary": final_artifact.get("safety_boundary"),
        },
        fallback,
    )


def run_runtime_step(
    step_id: str,
    inputs: dict[str, Any] | None = None,
    config: dict[str, Any] | None = None,
    runs_root: str | Path | None = None,
    run_id: str | None = None,
    llm_client: Any | None = None,
) -> dict[str, Any]:
    if step_id not in RUNTIME_GRAPH_STEP_IDS:
        raise ValueError(f"Unknown workflow step: {step_id}")

    blueprint_dir = Path(__file__).resolve().parents[3]
    resolved_config = read_json(blueprint_dir / "config" / "default.json")
    if config:
        resolved_config = deep_merge(resolved_config, config)
    runtime_inputs = deep_merge(_runtime_message_payload(), inputs or {})
    payload = resolve_runtime_inputs(resolved_config, runtime_inputs)
    monitoring = resolve_monitoring(resolved_config, payload)
    run_id = run_id or payload.get("run_id") or os.environ.get("MN_RUN_ID") or f"{BLUEPRINT_ID}-{uuid.uuid4().hex[:8]}"
    output_folder = Path(
        payload.get("output_folder")
        or (resolved_config.get("outputs") or {}).get("folder_path")
        or f"outputs/{BLUEPRINT_ID}"
    ).expanduser()
    runs_root_path = Path(runs_root).expanduser() if runs_root else output_folder / "runs"
    run_dir = runs_root_path / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    document_folder = resolve_document_folder(payload, blueprint_dir)
    llm = llm_client or _resolve_llm_client(resolved_config)
    state = _load_workflow_state(run_dir)
    state.update(
        {
            "blueprint_id": BLUEPRINT_ID,
            "run_id": run_id,
            "document_folder": str(document_folder),
            "output_folder": str(output_folder),
            "monitoring": monitoring,
        }
    )
    write_json(
        run_dir / "inputs.json",
        {
            "payload": payload,
            "document_folder": str(document_folder),
            "output_folder": str(output_folder),
            "monitoring": monitoring,
            "dataset_input": DATASET_INPUT,
        },
    )
    append_event(run_dir, "runtime_step_started", {"step_id": step_id, "component": BLUEPRINT_ID})
    emit_actor_activity(run_dir, step_id, f"{step_id.replace('_', ' ').title()} started.", status="started")

    if step_id == "financial_folder_watcher":
        watch_state = _watch_state_for_step(document_folder, monitoring)
        state["watch_state"] = watch_state
        write_json(run_dir / str(monitoring.get("processed_state_file") or "watch_state.json"), watch_state)
        append_event(
            run_dir,
            "financial_folder_watcher_completed",
            {
                "document_folder": str(document_folder),
                "file_count": len(watch_state.get("processed_files") or []),
                "changed_file_count": len(watch_state.get("new_or_changed_files") or []),
                "cycle": watch_state.get("cycles_completed", 1),
            },
        )
        finding = _record_actor_finding(
            state,
            "financial_folder_watcher",
            _run_financial_folder_watcher_actor(llm, resolved_config, watch_state, document_folder),
        )
        outputs = {
            "watch_state": watch_state,
            "document_folder": str(document_folder),
            "output_folder": str(output_folder),
            "actor_finding": finding,
            "llm_usage": _llm_usage(llm),
        }
    elif step_id == "financial_document_reader":
        records = extract_records(document_folder, resolved_config)
        state["records"] = records
        write_json(run_dir / "financial_records.json", records)
        append_event(run_dir, "financial_document_reader_completed", {"record_count": len(records), "cycle": 1})
        finding = _record_actor_finding(
            state,
            "financial_document_reader",
            _run_financial_document_reader_actor(llm, resolved_config, records),
        )
        outputs = {
            "record_count": len(records),
            "records_path": str(run_dir / "financial_records.json"),
            "ocr_metadata_present": all("ocr_required" in item and "extraction_method" in item for item in records),
            "actor_finding": finding,
            "llm_usage": _llm_usage(llm),
        }
    elif step_id == "financial_activity_classifier":
        records = _state_records(state)
        sections = _classification_from_records(records)
        state.update(sections)
        append_event(
            run_dir,
            "financial_activity_classifier_completed",
            {"document_types": sections["document_summary"]["document_types"], "cycle": 1},
        )
        finding = _record_actor_finding(
            state,
            "financial_activity_classifier",
            _run_financial_activity_classifier_actor(llm, resolved_config, sections),
        )
        sections["actor_finding"] = finding
        sections["llm_usage"] = _llm_usage(llm)
        outputs = sections
    elif step_id == "financial_health_assessor":
        assessment = _assessment_from_state(state)
        state.update(assessment)
        append_event(
            run_dir,
            "financial_health_assessor_completed",
            {
                "risk_count": len(assessment["risk_register"]),
                "cycle": 1,
            },
        )
        sections = {
            "document_summary": state.get("document_summary", {}),
            "financial_snapshot": state.get("financial_snapshot", {}),
            "income_summary": state.get("income_summary", {}),
            "expense_summary": state.get("expense_summary", {}),
        }
        finding = _record_actor_finding(
            state,
            "financial_health_assessor",
            _run_financial_health_assessor_actor(llm, resolved_config, assessment, sections),
        )
        assessment["actor_finding"] = finding
        assessment["llm_usage"] = _llm_usage(llm)
        outputs = assessment
    elif step_id == "financial_market_researcher":
        records = _state_records(state)
        if not isinstance(state.get("document_summary"), dict):
            state.update(_classification_from_records(records))
        if not isinstance(state.get("risk_register"), list):
            state.update(_assessment_from_state(state))
        research = financial_market_researcher(
            state.get("risk_register") if isinstance(state.get("risk_register"), list) else [],
            state.get("document_summary") if isinstance(state.get("document_summary"), dict) else build_document_summary(records),
            resolved_config,
            run_id,
            llm,
            run_dir,
        )
        state["research"] = research
        _record_actor_finding(
            state,
            "financial_market_researcher",
            {
                "actor_id": "financial_market_researcher",
                "role": "Financial market researcher",
                "summary": research.get("research_summary", ""),
                "research_plan": research.get("research_plan", {}),
                "research_findings": research.get("research_findings", []),
                "confidence": 0.72 if research.get("research_sources") else 0.4,
                "generated_at": utc_now_iso(),
            },
        )
        write_json(run_dir / "research.json", research)
        append_event(
            run_dir,
            "financial_market_researcher_completed",
            {
                "source_count": len(research.get("research_sources") or []),
                "warning_count": len(research.get("research_warnings") or []),
                "cycle": 1,
            },
        )
        research["actor_findings"] = _actor_findings(state)
        research["llm_usage"] = _llm_usage(llm)
        outputs = research
    else:
        records = _state_records(state)
        watch_state = state.get("watch_state") if isinstance(state.get("watch_state"), dict) else _watch_state_for_step(document_folder, monitoring)
        research = state.get("research") if isinstance(state.get("research"), dict) else None
        final_artifact = build_final_artifact(
            records,
            watch_state,
            run_id,
            research=research,
            actor_findings=_actor_findings(state),
            llm_usage=_llm_usage(llm),
        )
        reporter_finding = _record_actor_finding(
            state,
            "financial_advice_reporter",
            _run_financial_advice_reporter_actor(llm, resolved_config, final_artifact),
        )
        final_artifact = build_final_artifact(
            records,
            watch_state,
            run_id,
            research=research,
            actor_findings=_actor_findings(state),
            llm_usage=_llm_usage(llm),
        )
        append_event(
            run_dir,
            "human_input_requested",
            {"mode": "approval_required", "reason": "Review advisor report before any financial action.", "cycle": 1},
        )
        output_files = write_output_folder_artifacts(final_artifact, output_folder, run_id, cycle=1)
        result = {
            "run_id": run_id,
            "blueprint_id": BLUEPRINT_ID,
            "status": "completed",
            "cycle": 1,
            "records": records,
            "final_artifact": final_artifact,
            "output_files": output_files,
        }
        write_json(run_dir / "result.json", result)
        write_json(run_dir / "final_artifact.json", final_artifact)
        append_event(run_dir, "financial_advice_reporter_completed", {"output_files": output_files, "cycle": 1})
        outputs = {
            "final_artifact": final_artifact,
            "output_files": output_files,
            "actor_finding": reporter_finding,
            "llm_usage": _llm_usage(llm),
        }

    _save_workflow_state(run_dir, state)
    emit_actor_activity(run_dir, step_id, f"{step_id.replace('_', ' ').title()} completed.", status="completed")
    append_event(run_dir, "runtime_step_completed", {"step_id": step_id, "component": BLUEPRINT_ID})
    return _runtime_step_result(
        step_id,
        run_id,
        OUTPUT_MESSAGE_BY_STEP[step_id],
        outputs,
        summary=f"{step_id.replace('_', ' ').title()} completed in runtime step mode.",
    )


def run_blueprint(
    inputs: dict[str, Any] | None = None,
    config: dict[str, Any] | None = None,
    runs_root: str | Path | None = None,
    run_id: str | None = None,
    llm_client: Any | None = None,
) -> dict[str, Any]:
    start_agent_beacon_thread(f"{BLUEPRINT_NAME} is running")
    blueprint_dir = Path(__file__).resolve().parents[3]
    resolved_config = read_json(blueprint_dir / "config" / "default.json")
    if config:
        resolved_config = deep_merge(resolved_config, config)
    runtime_inputs = deep_merge(_runtime_message_payload(), inputs or {})
    payload = resolve_runtime_inputs(resolved_config, runtime_inputs)
    monitoring = resolve_monitoring(resolved_config, payload)
    run_id = run_id or payload.get("run_id") or f"{BLUEPRINT_ID}-{uuid.uuid4().hex[:8]}"
    output_folder = Path(
        payload.get("output_folder")
        or (resolved_config.get("outputs") or {}).get("folder_path")
        or f"outputs/{BLUEPRINT_ID}"
    ).expanduser()
    runs_root_path = Path(runs_root).expanduser() if runs_root else output_folder / "runs"
    run_dir = runs_root_path / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    document_folder = resolve_document_folder(payload, blueprint_dir)
    llm = llm_client or _resolve_llm_client(resolved_config)

    workflow_step_id = _runtime_graph_step_id()
    if workflow_step_id:
        return run_runtime_step(
            workflow_step_id,
            inputs=payload,
            config=resolved_config,
            runs_root=runs_root_path,
            run_id=run_id,
            llm_client=llm,
        )

    write_json(run_dir / "config.json", resolved_config)
    write_json(
        run_dir / "inputs.json",
        {
            "payload": payload,
            "document_folder": str(document_folder),
            "output_folder": str(output_folder),
            "monitoring": monitoring,
            "dataset_input": DATASET_INPUT,
        },
    )
    write_json(
        run_dir / "run.json",
        {"run_id": run_id, "blueprint_id": BLUEPRINT_ID, "status": "running", "started_at": utc_now_iso()},
    )

    if monitoring["enabled"]:
        result = run_watch_loop(document_folder, output_folder, resolved_config, run_dir, run_id, monitoring, llm)
    else:
        fingerprints = {str(path): fingerprint_file(path) for path in iter_financial_files(document_folder)}
        watch_state = {
            "mode": "one_shot",
            "cycles_completed": 1,
            "processed_files": list(fingerprints.values()),
            "new_or_changed_files": list(fingerprints.values()),
            "poll_interval_seconds": None,
            "last_scan_at": utc_now_iso(),
        }
        result = run_scan_cycle(document_folder, output_folder, resolved_config, run_dir, run_id, watch_state, cycle=1, llm=llm)

    write_json(
        run_dir / "run.json",
        {"run_id": run_id, "blueprint_id": BLUEPRINT_ID, "status": "completed", "completed_at": utc_now_iso()},
    )
    return result


def run_watch_loop(
    document_folder: Path,
    output_folder: Path,
    config: dict[str, Any],
    run_dir: Path,
    run_id: str,
    monitoring: dict[str, Any],
    llm: Any,
) -> dict[str, Any]:
    processed: dict[str, dict[str, Any]] = {}
    final_result: dict[str, Any] | None = None
    cycle = 0
    max_cycles = monitoring.get("max_cycles")
    while True:
        cycle += 1
        append_event(run_dir, "watch_cycle_started", {"cycle": cycle, "component": BLUEPRINT_ID})
        current = {str(path): fingerprint_file(path) for path in iter_financial_files(document_folder)}
        changed = [
            fingerprint
            for key, fingerprint in current.items()
            if processed.get(key, {}).get("sha256") != fingerprint.get("sha256")
            or processed.get(key, {}).get("mtime_ns") != fingerprint.get("mtime_ns")
        ]
        processed = current
        watch_state = {
            "mode": "watch",
            "cycles_completed": cycle,
            "processed_files": list(processed.values()),
            "new_or_changed_files": changed,
            "poll_interval_seconds": monitoring["poll_interval_seconds"],
            "last_scan_at": utc_now_iso(),
        }
        write_json(run_dir / str(monitoring.get("processed_state_file") or "watch_state.json"), watch_state)
        final_result = run_scan_cycle(document_folder, output_folder, config, run_dir, run_id, watch_state, cycle=cycle, llm=llm)
        append_event(
            run_dir,
            "watch_cycle_completed",
            {"cycle": cycle, "changed_files": len(changed), "component": BLUEPRINT_ID},
        )
        if max_cycles is not None and cycle >= max_cycles:
            break
        time.sleep(monitoring["poll_interval_seconds"])
    return final_result or {}


def run_scan_cycle(
    document_folder: Path,
    output_folder: Path,
    config: dict[str, Any],
    run_dir: Path,
    run_id: str,
    watch_state: dict[str, Any],
    cycle: int,
    llm: Any,
) -> dict[str, Any]:
    state = _load_workflow_state(run_dir)
    actor_findings = _actor_findings(state)
    state["watch_state"] = watch_state
    append_event(run_dir, "blueprint_phase_started", {"phase": "loading_inputs", "component": BLUEPRINT_ID, "cycle": cycle})
    emit_actor_activity(
        run_dir,
        "financial_folder_watcher",
        "Scanning the monitored financial document folder.",
        status="started",
        details={"cycle": cycle, "document_folder": str(document_folder)},
    )
    append_event(
        run_dir,
        "financial_folder_watcher_completed",
        {
            "document_folder": str(document_folder),
            "file_count": len(watch_state.get("processed_files") or []),
            "changed_file_count": len(watch_state.get("new_or_changed_files") or []),
            "cycle": cycle,
        },
    )
    emit_actor_activity(
        run_dir,
        "financial_folder_watcher",
        "Folder scan completed.",
        status="completed",
        details={
            "cycle": cycle,
            "file_count": len(watch_state.get("processed_files") or []),
            "changed_file_count": len(watch_state.get("new_or_changed_files") or []),
        },
    )
    _record_actor_finding(
        state,
        "financial_folder_watcher",
        _run_financial_folder_watcher_actor(llm, config, watch_state, document_folder),
    )
    append_event(run_dir, "blueprint_phase_completed", {"phase": "loading_inputs", "component": BLUEPRINT_ID, "cycle": cycle})
    append_event(run_dir, "blueprint_phase_started", {"phase": "running_worker", "component": BLUEPRINT_ID, "cycle": cycle})

    emit_actor_activity(
        run_dir,
        "financial_document_reader",
        "Reading financial documents and OCR metadata.",
        status="started",
        details={"cycle": cycle},
    )
    records = extract_records(document_folder, config)
    state["records"] = records
    append_event(run_dir, "financial_document_reader_completed", {"record_count": len(records), "cycle": cycle})
    emit_actor_activity(
        run_dir,
        "financial_document_reader",
        "Document reading completed.",
        status="completed",
        details={"cycle": cycle, "record_count": len(records)},
    )
    _record_actor_finding(
        state,
        "financial_document_reader",
        _run_financial_document_reader_actor(llm, config, records),
    )
    document_summary = build_document_summary(records)
    sections = _classification_from_records(records)
    state.update(sections)
    emit_actor_activity(
        run_dir,
        "financial_activity_classifier",
        "Classifying financial activity by document type and cash-flow category.",
        status="started",
        details={"cycle": cycle, "record_count": len(records)},
    )
    append_event(run_dir, "financial_activity_classifier_completed", {"document_types": document_summary["document_types"], "cycle": cycle})
    emit_actor_activity(
        run_dir,
        "financial_activity_classifier",
        "Financial activity classification completed.",
        status="completed",
        details={"cycle": cycle, "document_types": document_summary["document_types"]},
    )
    _record_actor_finding(
        state,
        "financial_activity_classifier",
        _run_financial_activity_classifier_actor(llm, config, sections),
    )

    final_artifact = build_final_artifact(records, watch_state, run_id, actor_findings=actor_findings, llm_usage=_llm_usage(llm))
    assessment = {
        "risk_register": final_artifact["risk_register"],
        "advisor_recommendations": final_artifact["advisor_recommendations"],
        "reminders": final_artifact["reminders"],
    }
    state.update(assessment)
    emit_actor_activity(
        run_dir,
        "financial_health_assessor",
        "Assessing household financial health and risks.",
        status="started",
        details={"cycle": cycle},
    )
    _record_actor_finding(
        state,
        "financial_health_assessor",
        _run_financial_health_assessor_actor(llm, config, assessment, sections),
    )
    append_event(
        run_dir,
        "financial_health_assessor_completed",
        {
            "status": final_artifact["status"],
            "risk_count": len(final_artifact["risk_register"]),
            "cycle": cycle,
        },
    )
    emit_actor_activity(
        run_dir,
        "financial_health_assessor",
        "Financial health assessment completed.",
        status="completed",
        details={"cycle": cycle, "status": final_artifact["status"], "risk_count": len(final_artifact["risk_register"])},
    )
    research = financial_market_researcher(
        final_artifact["risk_register"],
        final_artifact["document_summary"],
        config,
        run_id,
        llm,
        run_dir,
    )
    state["research"] = research
    _record_actor_finding(
        state,
        "financial_market_researcher",
        {
            "actor_id": "financial_market_researcher",
            "role": "Financial market researcher",
            "summary": research.get("research_summary", ""),
            "research_plan": research.get("research_plan", {}),
            "research_findings": research.get("research_findings", []),
            "confidence": 0.72 if research.get("research_sources") else 0.4,
            "generated_at": utc_now_iso(),
        },
    )
    append_event(
        run_dir,
        "financial_market_researcher_completed",
        {
            "source_count": len(research.get("research_sources") or []),
            "warning_count": len(research.get("research_warnings") or []),
            "cycle": cycle,
        },
    )
    final_artifact = build_final_artifact(
        records,
        watch_state,
        run_id,
        research=research,
        actor_findings=actor_findings,
        llm_usage=_llm_usage(llm),
    )
    append_event(run_dir, "blueprint_phase_completed", {"phase": "running_worker", "component": BLUEPRINT_ID, "cycle": cycle})
    append_event(
        run_dir,
        "human_input_requested",
        {"mode": "approval_required", "reason": "Review advisor report before any financial action.", "cycle": cycle},
    )
    append_event(run_dir, "blueprint_phase_started", {"phase": "writing_artifacts", "component": BLUEPRINT_ID, "cycle": cycle})
    emit_actor_activity(
        run_dir,
        "financial_advice_reporter",
        "Writing the review-only advisor report.",
        status="started",
        details={"cycle": cycle},
    )
    _record_actor_finding(
        state,
        "financial_advice_reporter",
        _run_financial_advice_reporter_actor(llm, config, final_artifact),
    )
    final_artifact = build_final_artifact(
        records,
        watch_state,
        run_id,
        research=research,
        actor_findings=actor_findings,
        llm_usage=_llm_usage(llm),
    )
    output_files = write_output_folder_artifacts(final_artifact, output_folder, run_id, cycle)
    result = {
        "run_id": run_id,
        "blueprint_id": BLUEPRINT_ID,
        "status": "completed",
        "cycle": cycle,
        "records": records,
        "final_artifact": final_artifact,
        "output_files": output_files,
    }
    write_json(run_dir / "result.json", result)
    write_json(run_dir / "final_artifact.json", final_artifact)
    append_event(run_dir, "artifact_written", {"path": "result.json", "cycle": cycle})
    append_event(run_dir, "artifact_written", {"path": "final_artifact.json", "cycle": cycle})
    for item in output_files:
        append_event(run_dir, "artifact_written", {"path": item["path"], "cycle": cycle})
    append_event(run_dir, "financial_advice_reporter_completed", {"output_files": output_files, "cycle": cycle})
    emit_actor_activity(
        run_dir,
        "financial_advice_reporter",
        "Advisor report written.",
        status="completed",
        details={"cycle": cycle, "output_files": output_files},
    )
    append_event(run_dir, "blueprint_phase_completed", {"phase": "writing_artifacts", "component": BLUEPRINT_ID, "cycle": cycle})
    append_event(run_dir, "blueprint_phase_completed", {"phase": "completed", "component": BLUEPRINT_ID, "cycle": cycle})
    _save_workflow_state(run_dir, state)
    return result


def main() -> None:
    start_agent_beacon_thread(f"{BLUEPRINT_NAME} is running")
    parser = argparse.ArgumentParser(description=BLUEPRINT_NAME)
    parser.add_argument("--input-folder", default="")
    parser.add_argument("--output-folder", default="")
    parser.add_argument("--runs-root", default="")
    parser.add_argument("--run-id", default="")
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--poll-interval", type=int, default=60)
    parser.add_argument("--max-cycles", type=int, default=0)
    parser.add_argument("--no-run-store", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    inputs: dict[str, Any] = {}
    if args.input_folder:
        inputs["document_folder"] = args.input_folder
    if args.output_folder:
        inputs["output_folder"] = args.output_folder
    if args.once:
        inputs["monitoring"] = {"enabled": False}
    elif args.watch or args.max_cycles:
        inputs["monitoring"] = {"enabled": True, "poll_interval_seconds": args.poll_interval}
        if args.max_cycles:
            inputs["monitoring"]["max_cycles"] = args.max_cycles
    runs_root = args.runs_root or None
    if args.no_run_store and not runs_root:
        runs_root = os.environ.get("TMPDIR", "/tmp")
    result = run_blueprint(inputs=inputs, runs_root=runs_root, run_id=args.run_id or None)
    if result.get("schema") == "mn.workflow.step_result.v1":
        print(json.dumps(result, indent=2))
    else:
        print(json.dumps({"run_id": result["run_id"], "status": result["status"], "final_artifact": result["final_artifact"]}, indent=2))


if __name__ == "__main__":
    main()
