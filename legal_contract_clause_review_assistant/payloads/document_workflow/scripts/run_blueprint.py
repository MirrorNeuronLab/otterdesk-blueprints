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

BLUEPRINT_ID = 'legal_contract_clause_review_assistant'
BLUEPRINT_NAME = 'Legal Contract Clause Review Assistant'
OUTPUT_TYPE = 'contract_clause_review_packet'
RECOMMENDED_ACTION = 'attorney_review_required_before_relying_on_clause_findings'
FIELD_PROFILE = ['governing_law', 'change_of_control', 'assignment', 'indemnity', 'termination', 'audit_rights', 'renewal', 'exclusivity', 'liability']
DATASET_INPUT = {'name': 'Contract Understanding Atticus Dataset (CUAD) v1', 'provider': 'The Atticus Project on Zenodo and Hugging Face', 'url': 'https://zenodo.org/records/4595826', 'alternate_url': 'https://huggingface.co/datasets/theatticusproject/cuad', 'license': 'CC BY 4.0', 'availability_note': 'Public dataset with 510 commercial contracts and 13,000+ labels across 41 clause types.', 'expected_files': ['full_contracts_pdf/*.pdf', 'full_contracts_txt/*.txt', '*.csv', '*.json'], 'download_hint': 'Download CUAD_v1.zip from Zenodo or use the Hugging Face dataset for text-oriented experiments.'}


def _workspace_root() -> Path | None:
    for name in ("MN_WORKSPACE_ROOT", "MIRROR_NEURON_WORKSPACE", "OTTERDESK_MIRROR_NEURON_WORKSPACE"):
        value = os.environ.get(name)
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
            "document_type": record.get("document_type"),
            "text_preview": text[:500],
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
    output_folder = Path(payload.get("output_folder") or (resolved_config.get("outputs") or {}).get("folder_path") or f"~/Download/{BLUEPRINT_ID}").expanduser()
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
    confidence = 0.72 if records else 0.35
    final_artifact = {
        "type": OUTPUT_TYPE,
        "executive_summary": f"{BLUEPRINT_NAME} processed {len(records)} local document records and prepared a review-only extraction packet.",
        "recommended_action": RECOMMENDED_ACTION,
        "confidence": confidence,
        "evidence": evidence,
        "next_steps": [
            "Download or select the public sample input folder if no documents were processed.",
            "Review OCR warnings and extracted fields against source pages.",
            "Approve, revise, or reject before any downstream use.",
        ],
        "source_refs": ["inputs.json", "events.jsonl", "result.json", "inputs/public_dataset.json"],
        "dataset_input": DATASET_INPUT,
        "field_profile": FIELD_PROFILE,
        "document_count": len(records),
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
    result = {"run_id": run_id, "blueprint_id": BLUEPRINT_ID, "status": "completed", "records": records, "final_artifact": final_artifact}

    append_event(run_dir, "blueprint_phase_completed", {"phase": "running_worker", "component": BLUEPRINT_ID})
    append_event(run_dir, "human_input_requested", {"mode": "approval_required", "reason": "Review extracted values before downstream use."})
    append_event(run_dir, "blueprint_phase_started", {"phase": "writing_artifacts", "component": BLUEPRINT_ID})
    write_json(run_dir / "result.json", result)
    write_json(run_dir / "final_artifact.json", final_artifact)
    append_event(run_dir, "artifact_written", {"path": "result.json"})
    append_event(run_dir, "artifact_written", {"path": "final_artifact.json"})
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
