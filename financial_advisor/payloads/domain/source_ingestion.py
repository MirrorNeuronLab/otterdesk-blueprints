"""Document discovery, OCR, classification, and deterministic extraction helpers."""

from .common import *
from .review_services import fake_llm_requested

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
    llm = ctx.get("llm")
    provider = str(getattr(llm, "provider", "") or "").strip().lower()
    return (
        isinstance(llm, DeterministicLLM)
        or provider in {"fake", "mock", "deterministic", "deterministic-local", "test"}
        or fake_llm_requested(ctx["config"], ctx.get("payload"))
    )

def build_ocr_runtime(ctx: dict[str, Any]) -> tuple[Any | None, dict[str, Any]]:
    section = (ctx["config"].get("input_skills") or {}).get("llm_ocr")
    section = section if isinstance(section, dict) else {}
    install_policy = str(section.get("install_policy") or "on_first_required_document")
    runtime_managed = install_policy.strip().lower().replace("-", "_") in {
        "runtime",
        "runtime_managed",
        "preinstalled",
        "pre_installed",
    }
    status: dict[str, Any] = {
        "enabled": section.get("enabled", True) is not False,
        "skill_available": extract_document is not None and docker_ocr_client_factory_from_config is not None,
        "configured": False,
        "status": "not_needed",
        "install_policy": install_policy,
        "trigger": "PDF/image with less than 40 embedded characters",
        "source_model": "lightonai/LightOnOCR-2-1B",
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
                "status": "ready_for_runtime_managed_first_use" if runtime_managed else "ready_for_lazy_first_use",
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
