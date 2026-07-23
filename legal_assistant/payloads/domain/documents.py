"""Legal source ingestion and bounded evidence summaries."""

from __future__ import annotations

from .common import *
from .runtime_services import build_ocr_runtime, expand_runtime_path
from .state import load_state, save_state

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


def watch(ctx: dict[str, Any], **_options: Any) -> dict[str, Any]:
    state = load_state(ctx)
    run_dir = Path(ctx["run_dir"])
    write_json(run_dir / "run.json", {"run_id": ctx["run_id"], "blueprint_id": BLUEPRINT_ID, "status": "running", "started_at": utc_now_iso()})
    write_json(run_dir / "config.json", ctx["config"])
    write_json(run_dir / "inputs.json", {"payload": ctx["payload"], "document_folder": state["document_folder"], "dataset_inputs": DATASET_INPUTS})
    save_state(ctx, state, "legal_matter_state.json")
    return {"document_folder": state["document_folder"]}


def read_documents(ctx: dict[str, Any], **_options: Any) -> dict[str, Any]:
    from .review import build_llm_client

    state = load_state(ctx)
    llm = build_llm_client(ctx["config"], ctx["payload"], None)
    ocr_client, ocr_status = build_ocr_runtime({"config": ctx["config"], "payload": ctx["payload"], "llm": llm})
    records = load_documents(Path(state["document_folder"]), ocr_client=ocr_client)
    state.update({"records": records, "evidence": summarize_records(records), "warnings": record_warnings(records), "ocr_status": ocr_status})
    save_state(ctx, state, "legal_matter_state.json")
    return {"document_count": len(records), "warning_count": len(state["warnings"])}


__all__ = ["read_documents", "watch"]
