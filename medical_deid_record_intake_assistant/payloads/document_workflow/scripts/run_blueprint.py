#!/usr/bin/env python3.11
from __future__ import annotations

import argparse
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

BLUEPRINT_ID = 'medical_deid_record_intake_assistant'
BLUEPRINT_NAME = 'Medical De-Identification Record Intake Assistant'
OUTPUT_TYPE = 'medical_deidentification_review_packet'
RECOMMENDED_ACTION = 'privacy_officer_review_required_before_release'
FIELD_PROFILE = ['patient_name', 'date_of_birth', 'medical_record_number', 'doctor', 'medications', 'diagnoses', 'test_tables', 'visit_dates', 'redaction_spans']
DATASET_INPUT = {'name': 'RootCauseAnalytics Healthcare Library Sample', 'provider': 'RootCauseAnalytics on Hugging Face', 'url': 'https://huggingface.co/datasets/RootCauseAnalytics/Healthcare-Library-Sample', 'license': 'CC BY-NC 4.0 according to the public dataset/forum descriptions; review source terms before production use.', 'availability_note': 'Public synthetic healthcare document sample listed on Hugging Face with OCR-oriented PDFs and labels.', 'expected_files': ['*.pdf', 'ground_truth.csv', 'ground_truth.jsonl', 'bboxes.jsonl'], 'download_hint': 'Use the Hugging Face dataset files or clone with git-lfs/huggingface_hub when available.'}


def _workspace_root() -> Path | None:
    value = os.environ.get("MN_WORKSPACE_ROOT")
    if value:
        return Path(value).expanduser()
    for parent in Path(__file__).resolve().parents:
        if (parent / "mn-skills").exists():
            return parent
    return None


def _add_repo_paths() -> None:
    if os.environ.get("MN_USE_LOCAL_SKILLS", "").strip().lower() not in {"1", "true", "yes"}:
        return
    roots = []
    if os.environ.get("MN_SKILLS_ROOT"):
        roots.append(Path(os.environ["MN_SKILLS_ROOT"]).expanduser())
    workspace = _workspace_root()
    if workspace:
        roots.append(workspace / "mn-skills")
    for parent in Path(__file__).resolve().parents:
        roots.append(parent / "mn-skills")
    for root in roots:
        support = root / "blueprint_support_skill" / "src"
        if support.exists() and str(support) not in sys.path:
            sys.path.insert(0, str(support))
        candidate = root / "llm_ocr_skill" / "src"
        if candidate.exists() and str(candidate) not in sys.path:
            sys.path.insert(0, str(candidate))


_add_repo_paths()

from mn_blueprint_support import get_actor_llm_client, llm_usage, resolve_actor_specs, run_actor_reviews

try:
    from mn_llm_ocr_skill import docker_ocr_client_factory_from_config, extract_document_folder
except Exception:  # pragma: no cover - fallback for minimal local checks
    docker_ocr_client_factory_from_config = None
    extract_document_folder = None


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    return value if isinstance(value, dict) else {}


def deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_resolved_config(default_path: Path, overlay: dict[str, Any] | None = None) -> dict[str, Any]:
    resolved = read_json(default_path)
    env_path = os.environ.get("MN_BLUEPRINT_CONFIG_PATH")
    if env_path:
        resolved = deep_merge(resolved, read_json(Path(env_path)))
    env_json = os.environ.get("MN_BLUEPRINT_CONFIG_JSON")
    if env_json:
        decoded = json.loads(env_json)
        if isinstance(decoded, dict):
            resolved = deep_merge(resolved, decoded)
    if overlay:
        resolved = deep_merge(resolved, overlay)
    return resolved


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def append_event(run_dir: Path, event_type: str, payload: dict[str, Any]) -> None:
    record = {"type": event_type, "timestamp": utc_now_iso(), "payload": payload}
    with (run_dir / "events.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def redactor(text: str) -> str:
    value = re.sub(r"\b\d{3}[- ]?\d{2}[- ]?\d{4}\b", "[REDACTED-SSN]", text or "")
    value = re.sub(r"\b\d{9,18}\b", "[REDACTED-ID]", value)
    value = re.sub(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "[REDACTED-EMAIL]", value)
    return value


def classifier(text: str, filename: str) -> str:
    haystack = f"{filename}\n{text}".lower()
    for field in FIELD_PROFILE:
        key = str(field).replace("_", " ").lower()
        if key in haystack:
            return str(field)
    return "document"


def fallback_extract(folder: Path) -> list[dict[str, Any]]:
    if not folder.exists():
        return []
    records = []
    for path in sorted(folder.rglob("*")):
        if path.is_dir() or path.suffix.lower() not in {".txt", ".json"}:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception as exc:
            records.append({"path": str(path), "filename": path.name, "document_type": "unreadable", "text": "", "ocr_required": False, "extraction_method": "fallback", "warnings": [str(exc)], "metadata": {}})
            continue
        records.append({"path": str(path), "filename": path.name, "document_type": classifier(text, path.name), "text": redactor(text), "ocr_required": False, "extraction_method": "embedded_text_fallback", "warnings": [], "metadata": {}})
    return records


def extract_records(folder: Path, config: dict[str, Any]) -> list[dict[str, Any]]:
    if extract_document_folder is None:
        return fallback_extract(folder)
    skill_config = {"input_skills": config.get("input_skills", {})}
    factory = docker_ocr_client_factory_from_config(skill_config) if docker_ocr_client_factory_from_config else None
    try:
        return extract_document_folder(folder, classifier=classifier, redactor=redactor, llm_ocr_client_factory=factory, min_text_chars=40)
    except Exception as exc:
        records = fallback_extract(folder)
        records.append({"path": str(folder), "filename": folder.name, "document_type": "ocr_warning", "text": "", "ocr_required": True, "extraction_method": "fallback_after_ocr_error", "warnings": [str(exc)], "metadata": {"dataset_input": DATASET_INPUT}})
        return records


def summarize_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    evidence = []
    for record in records[:20]:
        text = str(record.get("text") or "")
        evidence.append({
            "source": record.get("filename"),
            "document_type": display_document_type(record),
            "text_preview": text[:500],
            "structured_values": structured_values_from_text(text),
            "ocr_required": bool(record.get("ocr_required")),
            "extraction_method": record.get("extraction_method"),
            "warnings": record.get("warnings") or [],
        })
    if not evidence:
        evidence.append({
            "source": "inputs/public_dataset.json",
            "document_type": "dataset_reference",
            "text_preview": DATASET_INPUT.get("availability_note", ""),
            "ocr_required": False,
            "extraction_method": "public_dataset_note",
            "warnings": ["No local document folder was provided; download the public sample input and rerun."],
        })
    return evidence


def display_document_type(record: dict[str, Any]) -> str:
    filename = str(record.get("filename") or "").lower()
    suffix = Path(filename).suffix.lower()
    if filename == "sample_dataset_manifest.json":
        return "sample_dataset_manifest"
    if filename.endswith("_labels.json") or "ground_truth" in filename or "answer" in filename:
        return "label_or_answer_file"
    if suffix == ".pdf":
        return "source_pdf"
    if suffix in {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp"}:
        return "source_image"
    if suffix == ".json":
        return "structured_json"
    if suffix in {".txt", ".md"}:
        return "source_text"
    return str(record.get("document_type") or "document")


def structured_values_from_text(text: str, *, limit: int = 12) -> list[dict[str, str]]:
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
                joined = ", ".join(str(item) for item in value[:5])
                values.append({"field": prefix, "value": joined[:180]})
            else:
                for index, item in enumerate(value[:3]):
                    add(f"{prefix}[{index}]", item)
        elif value not in (None, ""):
            values.append({"field": prefix, "value": str(value)[:180]})

    add("", decoded)
    return values[:limit]


def record_warnings(records: list[dict[str, Any]]) -> list[str]:
    warnings: list[str] = []
    for record in records:
        for warning in record.get("warnings") or []:
            text = str(warning)
            if text and text not in warnings:
                warnings.append(text)
    return warnings


def render_final_markdown(final_artifact: dict[str, Any]) -> str:
    lines = [
        f"# {final_artifact.get('title') or BLUEPRINT_NAME}",
        "",
        f"**Status:** {final_artifact.get('status', 'review_ready')}",
        f"**Recommended action:** {final_artifact.get('recommended_action')}",
        f"**Confidence:** {final_artifact.get('confidence')}",
        "",
        "## Executive Summary",
        str(final_artifact.get("executive_summary") or ""),
        "",
        "## Document Summary",
    ]
    summary = final_artifact.get("document_summary") if isinstance(final_artifact.get("document_summary"), dict) else {}
    for key in ("document_count", "ocr_required_count", "warning_count"):
        lines.append(f"- {key.replace('_', ' ').title()}: {summary.get(key, 0)}")
    lines.extend(["", "## Evidence Highlights"])
    for item in (final_artifact.get("evidence") or [])[:10]:
        if not isinstance(item, dict):
            continue
        preview = str(item.get("text_preview") or "").replace("\n", " ").strip()
        if len(preview) > 240:
            preview = preview[:237] + "..."
        lines.append(f"- **{item.get('source')}** ({item.get('document_type')}): {preview or 'No text preview available.'}")
        for value in item.get("structured_values") or []:
            lines.append(f"  - `{value.get('field')}`: {value.get('value')}")
        for warning in item.get("warnings") or []:
            lines.append(f"  - Warning: {warning}")
    lines.extend(["", "## Next Steps"])
    for step in final_artifact.get("next_steps") or []:
        lines.append(f"- {step}")
    lines.extend(["", "## Review Boundary"])
    boundary = final_artifact.get("review_boundary") if isinstance(final_artifact.get("review_boundary"), dict) else {}
    for item in boundary.get("blocked_actions") or []:
        lines.append(f"- {item}")
    lines.extend(["", "## Source References"])
    for ref in final_artifact.get("source_refs") or []:
        lines.append(f"- `{ref}`")
    return "\n".join(lines) + "\n"


def build_output_bundle(
    final_artifact: dict[str, Any],
    *,
    output_folder: Path,
    run_dir: Path,
    run_id: str,
    records: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    warnings = record_warnings(records)
    ocr_required_count = len([record for record in records if record.get("ocr_required")])
    checks = [
        {"name": "has_executive_summary", "ok": bool(final_artifact.get("executive_summary"))},
        {"name": "has_evidence", "ok": bool(final_artifact.get("evidence"))},
        {"name": "has_next_steps", "ok": bool(final_artifact.get("next_steps"))},
        {"name": "has_source_refs", "ok": bool(final_artifact.get("source_refs"))},
        {"name": "writes_user_download_folder", "ok": True},
    ]
    quality_status = "usable_with_ocr_warnings" if ocr_required_count or warnings else (
        "usable_with_review" if all(check["ok"] for check in checks[:4]) else "needs_attention"
    )
    artifact_quality = {
        "schema_version": "mn.blueprint.artifact_quality.v1",
        "blueprint_id": BLUEPRINT_ID,
        "run_id": run_id,
        "status": quality_status,
        "checks": checks,
        "evidence_count": len(final_artifact.get("evidence") or []),
        "document_count": len(records),
        "total_documents": len(records),
        "ocr_required_count": ocr_required_count,
        "warning_count": len(warnings),
        "warnings": warnings[:20],
        "highest_priority_issue": (
            "Resolve OCR/PDF rendering warnings before trusting image-only source values."
            if ocr_required_count or warnings
            else "Human review is required before downstream use."
        ),
    }
    run_health = {
        "schema_version": "mn.blueprint.run_health.v1",
        "blueprint_id": BLUEPRINT_ID,
        "run_id": run_id,
        "status": "completed_with_ocr_warnings" if ocr_required_count or warnings else "completed",
        "warning_count": len(warnings),
        "failure_count": 0,
        "document_count": len(records),
        "ocr_required_count": ocr_required_count,
        "output_folder": str(output_folder),
        "run_store": str(run_dir),
        "generated_at": utc_now_iso(),
    }
    action_ledger = {
        "schema_version": "mn.blueprint.action_ledger.v1",
        "blueprint_id": BLUEPRINT_ID,
        "run_id": run_id,
        "review_only": True,
        "actions": [
            {"step": "load_inputs", "status": "completed", "source_refs": ["inputs.json"]},
            {"step": "extract_documents", "status": "completed", "record_count": len(records)},
            {"step": "actor_review", "status": "completed", "actor_count": len(final_artifact.get("actor_findings") or {})},
            {"step": "write_final_outputs", "status": "completed", "output_folder": str(output_folder)},
        ],
        "blocked_actions": domain_blocked_actions(),
    }
    output_files = [
        {"kind": "final_artifact_json", "path": str(output_folder / "final_artifact.json")},
        {"kind": "report_markdown", "path": str(output_folder / "final_report.md")},
        {"kind": "action_ledger_json", "path": str(output_folder / "action_ledger.json")},
        {"kind": "artifact_quality_json", "path": str(output_folder / "artifact_quality.json")},
        {"kind": "run_health_json", "path": str(output_folder / "run_health.json")},
    ]
    return action_ledger, artifact_quality, run_health, output_files


def write_user_outputs(
    final_artifact: dict[str, Any],
    *,
    output_folder: Path,
    run_dir: Path,
    run_id: str,
    records: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    output_folder.mkdir(parents=True, exist_ok=True)
    action_ledger, artifact_quality, run_health, output_files = build_output_bundle(
        final_artifact,
        output_folder=output_folder,
        run_dir=run_dir,
        run_id=run_id,
        records=records,
    )
    final_artifact["artifact_quality"] = {
        "status": artifact_quality["status"],
        "warning_count": artifact_quality["warning_count"],
        "ocr_required_count": artifact_quality["ocr_required_count"],
        "highest_priority_issue": artifact_quality["highest_priority_issue"],
        "artifact": "artifact_quality.json",
    }
    final_artifact["run_health"] = {
        "status": run_health["status"],
        "warning_count": run_health["warning_count"],
        "failure_count": run_health["failure_count"],
        "artifact": "run_health.json",
    }
    final_artifact["action_ledger"] = {
        "review_only": True,
        "artifact": "action_ledger.json",
        "blocked_actions": action_ledger["blocked_actions"],
    }
    final_artifact["output_files"] = output_files
    write_json(output_folder / "final_artifact.json", final_artifact)
    (output_folder / "final_report.md").write_text(render_final_markdown(final_artifact), encoding="utf-8")
    write_json(output_folder / "action_ledger.json", action_ledger)
    write_json(output_folder / "artifact_quality.json", artifact_quality)
    write_json(output_folder / "run_health.json", run_health)
    write_json(run_dir / "action_ledger.json", action_ledger)
    write_json(run_dir / "artifact_quality.json", artifact_quality)
    write_json(run_dir / "run_health.json", run_health)
    return action_ledger, artifact_quality, run_health, output_files


def domain_next_steps(records: list[dict[str, Any]]) -> list[str]:
    if BLUEPRINT_ID == "invoice_bill_extraction_assistant":
        return [
            "Verify supplier, customer, invoice number, dates, totals, and payment terms against the source invoice image/PDF.",
            "Resolve OCR warnings for scanned PDFs before posting anything to ERP or payment workflows.",
            "Approve, revise, or reject the payable packet with an AP reviewer.",
        ]
    if BLUEPRINT_ID == "legal_contract_clause_review_assistant":
        return [
            "Review extracted clause text against the source agreement before relying on any clause category.",
            "Ask counsel to confirm missing, ambiguous, or high-risk terms such as assignment, liability, termination, and governing law.",
            "Use the packet as attorney-review support only, not legal advice.",
        ]
    if BLUEPRINT_ID == "medical_deid_record_intake_assistant":
        return [
            "Review every detected identifier and redaction warning with a privacy officer before release.",
            "Resolve OCR warnings for scanned pages because unreadable pages can hide PHI.",
            "Confirm that clinical meaning remains intact after de-identification.",
        ]
    if BLUEPRINT_ID == "tax_form_ocr_capture_assistant":
        return [
            "Verify each captured tax field against the source image and expected answer file.",
            "Resolve any low-confidence OCR or classification mismatch before using values in tax preparation.",
            "Keep the packet review-only until checked by a tax preparer.",
        ]
    return [
        "Review OCR warnings and extracted fields against source pages.",
        "Approve, revise, or reject before any downstream use.",
    ]


def domain_blocked_actions() -> list[str]:
    if BLUEPRINT_ID == "invoice_bill_extraction_assistant":
        return ["post_to_erp_without_review", "submit_payment_without_review", "treat_extraction_as_final_record"]
    if BLUEPRINT_ID == "legal_contract_clause_review_assistant":
        return ["treat_as_legal_advice", "redline_or_sign_contract_without_attorney_review", "notify_counterparty_without_review"]
    if BLUEPRINT_ID == "medical_deid_record_intake_assistant":
        return ["release_records_without_privacy_review", "claim_hipaa_safe_harbor_without_authorized_review", "share_identifiers_downstream"]
    if BLUEPRINT_ID == "tax_form_ocr_capture_assistant":
        return ["use_values_for_filing_without_review", "submit_tax_return_without_preparer_review", "store_unredacted_identifiers_outside_approved_paths"]
    return ["treat_extraction_as_final_record"]


def run_blueprint(
    inputs: dict[str, Any] | None = None,
    config: dict[str, Any] | None = None,
    runs_root: str | Path | None = None,
    run_id: str | None = None,
    llm_client: Any | None = None,
) -> dict[str, Any]:
    start_agent_beacon_thread(f"{BLUEPRINT_NAME} is running")
    blueprint_dir = Path(__file__).resolve().parents[3]
    resolved_config = load_resolved_config(blueprint_dir / "config" / "default.json", config)
    payload = dict((resolved_config.get("inputs") or {}).get("payload") or {})
    if inputs:
        payload.update(inputs)
    run_id = run_id or payload.get("run_id") or f"{BLUEPRINT_ID}-{uuid.uuid4().hex[:8]}"
    output_folder = Path(payload.get("output_folder") or (resolved_config.get("outputs") or {}).get("folder_path") or f"outputs/{BLUEPRINT_ID}").expanduser()
    runs_root_path = Path(runs_root).expanduser() if runs_root else output_folder / "runs"
    run_dir = runs_root_path / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    document_folder = Path(payload.get("document_folder") or "").expanduser() if payload.get("document_folder") else blueprint_dir / "examples" / "sample_inputs"

    write_json(run_dir / "config.json", resolved_config)
    write_json(run_dir / "inputs.json", {"payload": payload, "document_folder": str(document_folder), "dataset_input": DATASET_INPUT})
    write_json(run_dir / "run.json", {"run_id": run_id, "blueprint_id": BLUEPRINT_ID, "status": "running", "started_at": utc_now_iso()})
    append_event(run_dir, "blueprint_phase_started", {"phase": "loading_inputs", "component": BLUEPRINT_ID})
    append_event(run_dir, "blueprint_phase_completed", {"phase": "loading_inputs", "component": BLUEPRINT_ID})
    append_event(run_dir, "blueprint_phase_started", {"phase": "running_worker", "component": BLUEPRINT_ID})

    records = extract_records(document_folder, resolved_config)
    evidence = summarize_records(records)
    warnings = record_warnings(records)
    ocr_required_count = len([record for record in records if record.get("ocr_required")])
    confidence = 0.35 if not records else (0.58 if ocr_required_count or warnings else 0.78)
    packet_status = "needs_input" if not records else ("review_ready_with_ocr_warnings" if ocr_required_count or warnings else "review_ready")
    final_artifact = {
        "type": OUTPUT_TYPE,
        "title": f"{BLUEPRINT_NAME} Review Packet",
        "status": packet_status,
        "executive_summary": f"{BLUEPRINT_NAME} processed {len(records)} local document records and prepared a review-only extraction packet.",
        "recommended_action": RECOMMENDED_ACTION,
        "confidence": confidence,
        "evidence": evidence,
        "next_steps": domain_next_steps(records),
        "source_refs": ["inputs.json", "events.jsonl", "result.json", "inputs/public_dataset.json"],
        "dataset_input": DATASET_INPUT,
        "field_profile": FIELD_PROFILE,
        "document_count": len(records),
        "document_summary": {
            "document_count": len(records),
            "total_documents": len(records),
            "ocr_required_count": ocr_required_count,
            "warning_count": len(warnings),
            "document_types": sorted({display_document_type(record) for record in records}),
        },
        "quality_summary": {
            "real_values_present": bool(records),
            "evidence_preview_count": len(evidence),
            "warnings": warnings[:10],
        },
        "review_boundary": {
            "review_only": True,
            "blocked_actions": domain_blocked_actions(),
        },
        "generated_at": utc_now_iso(),
    }
    llm = get_actor_llm_client(resolved_config, llm_client)
    actor_state: dict[str, Any] = {}
    actor_ids = list(resolve_actor_specs(resolved_config).keys())
    actor_findings = run_actor_reviews(
        config=resolved_config,
        llm=llm,
        actor_ids=actor_ids,
        state=actor_state,
        task="Review the extraction packet and prepare actor findings for human approval.",
        context={
            "blueprint_id": BLUEPRINT_ID,
            "document_count": len(records),
            "output_type": OUTPUT_TYPE,
            "recommended_action": RECOMMENDED_ACTION,
            "evidence": evidence[:8],
            "field_profile": FIELD_PROFILE,
        },
        event_sink=run_dir,
    )
    final_artifact["actor_findings"] = actor_findings
    final_artifact["llm_usage"] = llm_usage(llm)
    action_ledger, artifact_quality, run_health, output_files = write_user_outputs(
        final_artifact,
        output_folder=output_folder,
        run_dir=run_dir,
        run_id=run_id,
        records=records,
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
        "output_files": output_files,
    }

    append_event(run_dir, "blueprint_phase_completed", {"phase": "running_worker", "component": BLUEPRINT_ID})
    append_event(run_dir, "human_input_requested", {"mode": "approval_required", "reason": "Review extracted values before downstream use."})
    append_event(run_dir, "blueprint_phase_started", {"phase": "writing_artifacts", "component": BLUEPRINT_ID})
    write_json(run_dir / "result.json", result)
    write_json(run_dir / "final_artifact.json", final_artifact)
    append_event(run_dir, "artifact_written", {"path": "result.json"})
    append_event(run_dir, "artifact_written", {"path": "final_artifact.json"})
    for name in ("action_ledger.json", "artifact_quality.json", "run_health.json"):
        append_event(run_dir, "artifact_written", {"path": name})
    for item in output_files:
        append_event(run_dir, "artifact_written", {"path": item["path"]})
    append_event(run_dir, "blueprint_phase_completed", {"phase": "writing_artifacts", "component": BLUEPRINT_ID})
    append_event(run_dir, "blueprint_phase_completed", {"phase": "completed", "component": BLUEPRINT_ID})
    write_json(run_dir / "run.json", {"run_id": run_id, "blueprint_id": BLUEPRINT_ID, "status": "completed", "completed_at": utc_now_iso()})
    return result


def main() -> None:
    start_agent_beacon_thread(f"{BLUEPRINT_NAME} is running")
    parser = argparse.ArgumentParser(description=BLUEPRINT_NAME)
    parser.add_argument("--input-folder", default="")
    parser.add_argument("--runs-root", default="")
    parser.add_argument("--run-id", default="")
    args = parser.parse_args()
    inputs = {}
    if args.input_folder:
        inputs["document_folder"] = args.input_folder
    result = run_blueprint(inputs=inputs, runs_root=args.runs_root or None, run_id=args.run_id or None)
    print(json.dumps({"run_id": result["run_id"], "status": result["status"], "final_artifact": result["final_artifact"]}, indent=2))


if __name__ == "__main__":
    main()
