#!/usr/bin/env python3
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


def _workspace_root() -> Path | None:
    for name in ("MN_WORKSPACE_ROOT", "MIRROR_NEURON_WORKSPACE", "OTTERDESK_MIRROR_NEURON_WORKSPACE"):
        value = os.environ.get(name)
        if value:
            return Path(value).expanduser()
    return None


def _add_repo_paths() -> None:
    skill_roots = []
    if os.environ.get("MN_SKILLS_ROOT"):
        skill_roots.append(Path(os.environ["MN_SKILLS_ROOT"]).expanduser())
    workspace_root = _workspace_root()
    if workspace_root:
        skill_roots.append(workspace_root / "mn-skills")
    skill_roots.extend(
        parent / "mn-skills"
        for parent in Path(__file__).resolve().parents
    )

    for skill_root in skill_roots:
        support = skill_root / "blueprint_support_skill" / "src"
        tax_skill = skill_root / "tax_pdf_ocr_skill" / "src"
        if support.exists() and str(support) not in sys.path:
            sys.path.insert(0, str(support))
        if tax_skill.exists() and str(tax_skill) not in sys.path:
            sys.path.insert(0, str(tax_skill))


_add_repo_paths()

try:  # noqa: E402
    from mn_blueprint_support.standard import (
        architecture_contract,
        create_runtime_context,
        load_config,
        resolve_input_overrides,
        run_blueprint_cli,
        utc_now_iso,
    )
except ModuleNotFoundError:  # pragma: no cover - exercised by host-local runtime
    def utc_now_iso() -> str:
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    def _read_json_object(path: Path) -> dict[str, Any]:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}

    def _deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
        merged = copy.deepcopy(base)
        for key, value in overlay.items():
            if isinstance(value, dict) and isinstance(merged.get(key), dict):
                merged[key] = _deep_merge(merged[key], value)
            else:
                merged[key] = copy.deepcopy(value)
        return merged

    def load_config(
        blueprint_id: str,
        *,
        default_config_path: str | Path,
        config: dict[str, Any] | None = None,
        config_path: str | Path | None = None,
        config_json: str | None = None,
        run_id: str | None = None,
        runs_root: str | Path | None = None,
        input_adapter: str | None = None,
        input_file: str | Path | None = None,
        write_run_store: bool | None = None,
    ) -> dict[str, Any]:
        if config_path is None:
            config_path = os.environ.get("MN_BLUEPRINT_CONFIG_PATH")
        if config_json is None:
            config_json = os.environ.get("MN_BLUEPRINT_CONFIG_JSON")
        resolved = _read_json_object(Path(default_config_path)) if Path(default_config_path).exists() else {}
        if config_path:
            resolved = _deep_merge(resolved, _read_json_object(Path(config_path)))
        if config_json:
            decoded = json.loads(config_json)
            if isinstance(decoded, dict):
                resolved = _deep_merge(resolved, decoded)
        if config:
            resolved = _deep_merge(resolved, config)
        identity = resolved.setdefault("identity", {})
        identity.setdefault("blueprint_id", blueprint_id)
        identity.setdefault("name", "Personal Income Tax Expert")
        if run_id or os.environ.get("MN_RUN_ID"):
            identity["run_id"] = run_id or os.environ["MN_RUN_ID"]
        if runs_root:
            resolved.setdefault("outputs", {})["run_root"] = str(runs_root)
        elif os.environ.get("MN_RUNS_ROOT"):
            resolved.setdefault("outputs", {})["run_root"] = os.environ["MN_RUNS_ROOT"]
        if input_adapter:
            resolved.setdefault("inputs", {})["adapter"] = input_adapter
        if input_file:
            payload = json.loads(Path(input_file).read_text(encoding="utf-8"))
            resolved.setdefault("inputs", {})["payload"] = payload if isinstance(payload, dict) else {}
        if write_run_store is not None:
            resolved.setdefault("outputs", {})["write_run_store"] = bool(write_run_store)
        return resolved

    def resolve_input_overrides(config: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        inputs = config.get("inputs") if isinstance(config.get("inputs"), dict) else {}
        payload = inputs.get("payload") if isinstance(inputs.get("payload"), dict) else {}
        source = {
            "adapter": inputs.get("adapter") or "mock",
            "description": inputs.get("description"),
            "path": inputs.get("path"),
            "real_ready": bool(payload.get("document_folder") or payload.get("tax_document_folder")),
        }
        return dict(payload), source

    class _RuntimeContext:
        def __init__(
            self,
            blueprint_id: str,
            config: dict[str, Any],
            inputs: dict[str, Any],
            input_source: dict[str, Any],
        ) -> None:
            identity = config.get("identity") if isinstance(config.get("identity"), dict) else {}
            outputs = config.get("outputs") if isinstance(config.get("outputs"), dict) else {}
            self.blueprint_id = blueprint_id
            self.name = str(identity.get("name") or "Personal Income Tax Expert")
            self.run_id = str(identity.get("run_id") or os.environ.get("MN_RUN_ID") or f"tax-{uuid.uuid4().hex[:8]}")
            self.config = config
            self.inputs = inputs
            self.input_source = input_source
            self.run_dir: Path | None = None
            if outputs.get("write_run_store", True) is not False:
                root = Path(outputs.get("run_root") or os.environ.get("MN_RUNS_ROOT") or "/tmp/mn-runs").expanduser()
                self.run_dir = root / self.run_id
                self.run_dir.mkdir(parents=True, exist_ok=True)

        def _write_json(self, name: str, payload: dict[str, Any]) -> None:
            if self.run_dir:
                (self.run_dir / name).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

        def start(self) -> None:
            self._write_json("config.json", self.config)
            self._write_json("inputs.json", self.inputs)
            self._write_json(
                "run.json",
                {"run_id": self.run_id, "blueprint_id": self.blueprint_id, "status": "running", "started_at": utc_now_iso()},
            )
            self.event("run_started", {"input_source": self.input_source})

        def event(self, event_type: str, payload: dict[str, Any]) -> None:
            if not self.run_dir:
                return
            event = {
                "ts": utc_now_iso(),
                "run_id": self.run_id,
                "blueprint_id": self.blueprint_id,
                "type": event_type,
                "payload": payload,
            }
            with (self.run_dir / "events.jsonl").open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(event, sort_keys=True) + "\n")

        def finish(self, result: dict[str, Any]) -> None:
            self._write_json("result.json", result)
            if isinstance(result.get("final_artifact"), dict):
                self._write_json("final_artifact.json", result["final_artifact"])
            self._write_json(
                "run.json",
                {"run_id": self.run_id, "blueprint_id": self.blueprint_id, "status": "completed", "ended_at": utc_now_iso()},
            )

        def fail(self, error: Exception) -> None:
            self.event("run_failed", {"error": str(error)})
            self._write_json(
                "run.json",
                {"run_id": self.run_id, "blueprint_id": self.blueprint_id, "status": "failed", "ended_at": utc_now_iso()},
            )

    def create_runtime_context(
        blueprint_id: str,
        config: dict[str, Any],
        inputs: dict[str, Any],
        input_source: dict[str, Any],
    ) -> _RuntimeContext:
        return _RuntimeContext(blueprint_id, config, inputs, input_source)

    def architecture_contract(config: dict[str, Any], input_source: dict[str, Any]) -> dict[str, Any]:
        return {
            "config": {
                "identity": config.get("identity"),
                "mode": config.get("mode"),
                "standard_version": config.get("standard_version"),
            },
            "inputs": {"source": input_source},
            "agent_handoffs": config.get("agent_handoffs"),
            "input_skills": config.get("input_skills"),
            "outputs": config.get("outputs"),
        }

    def run_blueprint_cli(run_func: Any, argv: list[str] | None = None, *, default_blueprint_id: str | None = None) -> None:
        parser = argparse.ArgumentParser(description="Run the Personal Income Tax Expert blueprint.")
        parser.add_argument("--blueprint-id", default=default_blueprint_id)
        parser.add_argument("--config-path", default=None)
        parser.add_argument("--config-json", default=None)
        parser.add_argument("--run-id", default=None)
        parser.add_argument("--runs-root", default=None)
        parser.add_argument("--input-adapter", default=None)
        parser.add_argument("--input-file", default=None)
        parser.add_argument("--no-run-store", action="store_true")
        args = parser.parse_args(argv)
        result = run_func(
            args.blueprint_id or default_blueprint_id or BLUEPRINT_ID,
            config_path=args.config_path,
            config_json=args.config_json,
            run_id=args.run_id,
            runs_root=args.runs_root,
            input_adapter=args.input_adapter,
            input_file=args.input_file,
            write_run_store=False if args.no_run_store else None,
        )
        print(json.dumps(result, indent=2, sort_keys=True))

try:  # noqa: E402
    from mn_tax_pdf_ocr_skill import extract_tax_pdf_folder, redact_tax_identifiers
except ModuleNotFoundError:  # pragma: no cover - fallback for minimal bundles
    extract_tax_pdf_folder = None

    def redact_tax_identifiers(text: str) -> str:
        return re.sub(r"\b\d{3}-\d{2}-\d{4}\b", "[REDACTED]", text or "")


BLUEPRINT_ID = "personal_income_tax_expert"

STANDARD_DEDUCTION_2025 = {
    "single": 15750,
    "married_filing_separately": 15750,
    "married_filing_jointly": 31500,
    "qualifying_surviving_spouse": 31500,
    "head_of_household": 23625,
}

TAX_INPUT_KEYS = {
    "description",
    "document_folder",
    "filing_status",
    "scenario",
    "tax_document_folder",
    "tax_year",
}


def _default_config_path() -> Path:
    candidates = []
    for parent in Path(__file__).resolve().parents:
        candidates.append(parent / "config" / "default.json")
        candidates.append(parent / BLUEPRINT_ID / "config" / "default.json")
    workspace_root = _workspace_root()
    if workspace_root:
        candidates.append(workspace_root / "otterdesk-blueprints" / BLUEPRINT_ID / "config" / "default.json")
    candidates.extend(
        [
            Path.home() / ".mn" / "blueprints" / BLUEPRINT_ID / "config" / "default.json",
        ]
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return Path(__file__).resolve().parents[3] / "config" / "default.json"


def _runtime_message_payload() -> dict[str, Any]:
    for env_name in ("MN_MESSAGE_FILE", "MIRROR_NEURON_MESSAGE_FILE"):
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
        payload = _find_tax_payload(decoded)
        if payload:
            return payload
    return {}


def _find_tax_payload(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    if any(key in value for key in TAX_INPUT_KEYS):
        return {key: value[key] for key in TAX_INPUT_KEYS if key in value}
    for key in ("payload", "input", "body", "data", "message", "content"):
        payload = _find_tax_payload(value.get(key))
        if payload:
            return payload
    return {}


def run_blueprint(
    blueprint_id: str = BLUEPRINT_ID,
    *,
    inputs: dict[str, Any] | None = None,
    config: dict[str, Any] | None = None,
    config_path: str | Path | None = None,
    config_json: str | None = None,
    run_id: str | None = None,
    runs_root: str | Path | None = None,
    input_adapter: str | None = None,
    input_file: str | Path | None = None,
    write_run_store: bool | None = None,
) -> dict[str, Any]:
    default_config_path = _default_config_path()
    resolved_config = load_config(
        blueprint_id,
        default_config_path=default_config_path,
        config=config,
        config_path=config_path,
        config_json=config_json,
        run_id=run_id,
        runs_root=runs_root,
        input_adapter=input_adapter,
        input_file=input_file,
        write_run_store=write_run_store,
    )
    adapter_inputs, input_source = resolve_input_overrides(resolved_config)
    runtime_inputs = _merge_runtime_inputs(adapter_inputs, _runtime_message_payload(), inputs or {})
    context = create_runtime_context(blueprint_id, resolved_config, runtime_inputs, input_source)
    started_at = utc_now_iso()
    context.start()
    try:
        documents = _load_documents(resolved_config, runtime_inputs)
        context.event("tax_document_intake_completed", _document_summary(documents))

        intake = _intake_agent(documents, resolved_config, runtime_inputs)
        context.event("tax_intake_agent_completed", intake)

        proposal = _proposal_agent(documents, intake, resolved_config, runtime_inputs)
        context.event("tax_proposal_agent_completed", proposal)

        review = _review_agent(documents, proposal, resolved_config, runtime_inputs)
        context.event("tax_review_agent_completed", review)

        final_artifact = _packet_writer_agent(documents, intake, proposal, review, resolved_config, runtime_inputs)
        context.event(
            "human_notice",
            {
                "notice_id": f"{context.run_id}-tax-review",
                "kind": "tax_packet_review",
                "title": "Tax packet needs review",
                "message": final_artifact["advisor_message"],
                "chat_delivery": "otterdesk_worker_chat",
                "severity": "info",
            },
        )

        ended_at = utc_now_iso()
        result = {
            "identity": {
                "blueprint_id": blueprint_id,
                "name": context.name,
                "run_id": context.run_id,
            },
            "blueprint": blueprint_id,
            "name": context.name,
            "category": "Finance",
            "description": resolved_config.get("metadata", {}).get("description"),
            "run": {
                "run_id": context.run_id,
                "run_dir": str(context.run_dir) if context.run_dir else None,
                "started_at": started_at,
                "ended_at": ended_at,
                "status": "completed",
            },
            "architecture": architecture_contract(resolved_config, input_source),
            "config": resolved_config,
            "inputs": runtime_inputs,
            "input_source": input_source,
            "agent_roles": list((resolved_config.get("llm") or {}).get("agents", {}).values()),
            "runtime_features": list((resolved_config.get("metadata") or {}).get("runtime_features") or []),
            "document_summary": _document_summary(documents),
            "timeline": [
                {"agent": "document_intake_agent", "output": intake},
                {"agent": "tax_proposal_agent", "output": proposal},
                {"agent": "tax_review_agent", "output": review},
                {"agent": "form_1040_packet_writer", "output": final_artifact},
            ],
            "final_artifact": final_artifact,
            "warnings": review.get("warnings", []),
        }
        context.finish(result)
        return result
    except Exception as error:
        context.fail(error)
        raise


def _load_documents(config: dict[str, Any], runtime_inputs: dict[str, Any]) -> list[dict[str, Any]]:
    folder = _document_folder_value(config, runtime_inputs)
    folder_path = Path(str(folder)).expanduser() if folder else None
    if folder_path and folder_path.exists() and folder_path.is_dir() and extract_tax_pdf_folder is not None:
        return extract_tax_pdf_folder(folder_path)
    if folder_path and folder_path.exists() and folder_path.is_dir():
        return _fallback_folder_scan(folder_path)
    return list((config.get("tax_documents") or {}).get("sample_documents") or [])


def _fallback_folder_scan(folder: Path) -> list[dict[str, Any]]:
    records = []
    for path in sorted(folder.iterdir()):
        if not path.is_file() or path.suffix.lower() not in {".pdf", ".txt", ".json"}:
            continue
        text = ""
        if path.suffix.lower() in {".txt", ".json"}:
            text = path.read_text(encoding="utf-8")
        records.append(
            {
                "path": str(path),
                "filename": path.name,
                "document_type": _classify(path.name, text),
                "text": redact_tax_identifiers(text),
                "ocr_required": path.suffix.lower() == ".pdf" and not text,
                "extraction_method": "fallback",
                "warnings": ["PDF OCR skill unavailable; verify extracted values manually."]
                if path.suffix.lower() == ".pdf"
                else [],
            }
        )
    return records


def _classify(filename: str, text: str) -> str:
    haystack = f"{filename}\n{text}".lower()
    if "1099-int" in haystack or "interest income" in haystack:
        return "1099-INT"
    if "1099-r" in haystack or "401" in haystack or "gross distribution" in haystack:
        return "1099-R"
    if "w-2" in haystack or "wage and tax statement" in haystack:
        return "W-2"
    if "1099-div" in haystack:
        return "1099-DIV"
    return "unknown_tax_document"


def _document_summary(documents: list[dict[str, Any]]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    ocr_required = []
    for document in documents:
        doc_type = str(document.get("document_type") or "unknown_tax_document")
        counts[doc_type] = counts.get(doc_type, 0) + 1
        if document.get("ocr_required"):
            ocr_required.append(document.get("filename"))
    return {
        "document_count": len(documents),
        "document_types": counts,
        "ocr_required": ocr_required,
    }


def _intake_agent(
    documents: list[dict[str, Any]],
    config: dict[str, Any],
    runtime_inputs: dict[str, Any],
) -> dict[str, Any]:
    required = set((config.get("tax_documents") or {}).get("recommended_forms") or [])
    found = {str(document.get("document_type")) for document in documents}
    gaps = sorted(required - found)
    if not documents:
        gaps.append("tax_document_folder")
    return {
        "role": "document_intake_agent",
        "found_forms": sorted(found),
        "missing_or_unconfirmed": sorted(set(gaps)),
        "tax_year": int(runtime_inputs.get("tax_year") or (config.get("tax_profile") or {}).get("tax_year") or 2025),
        "filing_status": str(runtime_inputs.get("filing_status") or (config.get("tax_profile") or {}).get("filing_status") or "single"),
        "needs_ocr": [document.get("filename") for document in documents if document.get("ocr_required")],
    }


def _proposal_agent(
    documents: list[dict[str, Any]],
    intake: dict[str, Any],
    config: dict[str, Any],
    runtime_inputs: dict[str, Any],
) -> dict[str, Any]:
    values = _extract_values(documents)
    filing_status = _normalize_status(str(intake["filing_status"]))
    deduction = _standard_deduction(config, filing_status)
    agi = values["wages"] + values["taxable_interest"] + values["retirement_taxable"]
    taxable_income = max(0.0, agi - deduction)
    return {
        "role": "tax_proposal_agent",
        "proposal_type": "draft_form_1040_line_mapping",
        "line_map": {
            "1z_wages": _money(values["wages"]),
            "2b_taxable_interest": _money(values["taxable_interest"]),
            "4b_taxable_ira_pensions_annuities": _money(values["retirement_taxable"]),
            "11_adjusted_gross_income": _money(agi),
            "12_standard_deduction": _money(deduction),
            "15_taxable_income": _money(taxable_income),
            "25d_total_federal_income_tax_withheld": _money(values["federal_withholding"]),
        },
        "evidence": values["evidence"],
        "assumptions": [
            f"Filing status is treated as {filing_status.replace('_', ' ')} until the user confirms it.",
            "Standard deduction is used until itemized deductions are supplied and reviewed.",
            "State tax return preparation is outside this federal 1040 draft packet.",
        ],
        "questions_for_user": _questions_for_user(intake, values, runtime_inputs, config),
    }


def _review_agent(
    documents: list[dict[str, Any]],
    proposal: dict[str, Any],
    config: dict[str, Any],
    runtime_inputs: dict[str, Any],
) -> dict[str, Any]:
    warnings = []
    if any(document.get("ocr_required") for document in documents):
        warnings.append("Some PDFs need OCR before their values should be trusted.")
    if "tax_document_folder" in proposal.get("questions_for_user", []):
        warnings.append("A real local tax document folder has not been provided.")
    if not proposal["evidence"]:
        warnings.append("No source evidence was extracted; this is a demo packet only.")
    if proposal["line_map"]["15_taxable_income"] == "$0.00":
        warnings.append("Taxable income is zero in the draft; confirm that income documents are complete.")
    return {
        "role": "tax_review_agent",
        "review_status": "needs_human_review",
        "warnings": warnings,
        "checks": [
            "Matched extracted document types to likely Form 1040 lines.",
            "Kept unsupported credits and deductions out of the draft packet.",
            "Marked OCR and missing-document risks for follow-up.",
            "Prepared a source-grounded advisor conversation summary.",
        ],
        "do_not_file_until": [
            "Identity, filing status, address, dependents, and signatures are confirmed.",
            "All source PDFs have been checked against the draft line map.",
            "A qualified preparer or the taxpayer reviews the final return.",
        ],
    }


def _packet_writer_agent(
    documents: list[dict[str, Any]],
    intake: dict[str, Any],
    proposal: dict[str, Any],
    review: dict[str, Any],
    config: dict[str, Any],
    runtime_inputs: dict[str, Any],
) -> dict[str, Any]:
    tax_year = intake["tax_year"]
    advisor_message = _advisor_message(intake, proposal, review)
    return {
        "type": "prepared_1040_tax_packet",
        "title": "Prepared Form 1040 Draft - What Is a 1040 Tax Form",
        "tax_year": tax_year,
        "status": "draft_needs_review",
        "what_is_a_1040_tax_form": (
            "Form 1040 is the main U.S. individual income tax return. "
            "This packet maps extracted income and withholding evidence to likely Form 1040 lines, "
            "but it is not a filed return and it still needs taxpayer or preparer review."
        ),
        "prepared_form_1040": {
            "filing_status": intake["filing_status"],
            "line_map": proposal["line_map"],
            "source_evidence": proposal["evidence"],
            "assumptions": proposal["assumptions"],
        },
        "advisor_message": advisor_message,
        "conversation_context": {
            "advisor_voice": "personal_tax_advisor",
            "opening": advisor_message,
            "next_best_questions": proposal["questions_for_user"],
            "review_status": review["review_status"],
        },
        "document_summary": _document_summary(documents),
        "review": review,
        "next_steps": [
            "Upload or point me to the complete local folder for W-2, 1099, 1098, 1095-A, and brokerage forms.",
            "Confirm filing status, dependents, address, and whether you plan to itemize.",
            "Review the draft Form 1040 line map before using any tax software or filing workflow.",
        ],
        "knowledge_sources": list((config.get("knowledge") or {}).get("irs_sources") or []),
    }


def _extract_values(documents: list[dict[str, Any]]) -> dict[str, Any]:
    values = {
        "wages": 0.0,
        "taxable_interest": 0.0,
        "retirement_taxable": 0.0,
        "federal_withholding": 0.0,
        "evidence": [],
    }
    for document in documents:
        doc_type = str(document.get("document_type") or "")
        text = str(document.get("text") or "")
        if doc_type == "W-2":
            _add_amount(values, "wages", text, ("box 1 wages", "wages"))
            _add_amount(values, "federal_withholding", text, ("box 2 federal income tax withheld", "federal income tax withheld"))
        elif doc_type == "1099-INT":
            _add_amount(values, "taxable_interest", text, ("box 1 interest income", "interest income"))
            _add_amount(values, "federal_withholding", text, ("box 4 federal income tax withheld", "federal income tax withheld"))
        elif doc_type == "1099-R":
            _add_amount(values, "retirement_taxable", text, ("box 2a taxable amount", "taxable amount", "gross distribution"))
            _add_amount(values, "federal_withholding", text, ("box 4 federal income tax withheld", "federal income tax withheld"))
        _record_evidence(values, document, doc_type)
    return values


def _add_amount(values: dict[str, Any], key: str, text: str, labels: tuple[str, ...]) -> None:
    amount = _find_amount(text, labels)
    if amount is not None:
        values[key] += amount


def _find_amount(text: str, labels: tuple[str, ...]) -> float | None:
    lowered = text.lower()
    for label in labels:
        pattern = re.compile(rf"{re.escape(label.lower())}[^0-9$-]*\$?([0-9][0-9,]*(?:\.[0-9]{{2}})?)")
        match = pattern.search(lowered)
        if match:
            return float(match.group(1).replace(",", ""))
    amounts = re.findall(r"\$?([0-9][0-9,]*(?:\.[0-9]{2})?)", text)
    if len(amounts) == 1:
        return float(amounts[0].replace(",", ""))
    return None


def _record_evidence(values: dict[str, Any], document: dict[str, Any], doc_type: str) -> None:
    if doc_type == "unknown_tax_document":
        return
    values["evidence"].append(
        {
            "document_type": doc_type,
            "filename": document.get("filename"),
            "extraction_method": document.get("extraction_method"),
            "ocr_required": bool(document.get("ocr_required")),
        }
    )


def _questions_for_user(
    intake: dict[str, Any],
    values: dict[str, Any],
    runtime_inputs: dict[str, Any],
    config: dict[str, Any],
) -> list[str]:
    questions = []
    if not _document_folder_value(config, runtime_inputs):
        questions.append("tax_document_folder")
    if "W-2" not in intake["found_forms"]:
        questions.append("Do you have W-2 wages, self-employment income, or only investment/retirement income?")
    if "1099-R" in intake["found_forms"]:
        questions.append("Was any retirement distribution rolled over, Roth, early, or subject to an exception code?")
    if values["federal_withholding"] == 0:
        questions.append("Did any form report federal income tax withholding?")
    questions.append("Will you claim the standard deduction, or do you have itemized deductions to review?")
    return questions


def _merge_runtime_inputs(*sources: dict[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for source in sources:
        for key, value in source.items():
            if value in (None, "") and key in merged:
                continue
            merged[key] = value
    return merged


def _document_folder_value(config: dict[str, Any], runtime_inputs: dict[str, Any]) -> Any:
    return (
        runtime_inputs.get("document_folder")
        or runtime_inputs.get("tax_document_folder")
        or (config.get("tax_documents") or {}).get("folder_path")
        or ""
    )


def _normalize_status(value: str) -> str:
    normalized = value.strip().lower().replace(" ", "_").replace("-", "_")
    if normalized in STANDARD_DEDUCTION_2025:
        return normalized
    return "single"


def _standard_deduction(config: dict[str, Any], filing_status: str) -> float:
    table = ((config.get("tax_knowledge") or {}).get("standard_deduction_2025") or STANDARD_DEDUCTION_2025)
    return float(table.get(filing_status, STANDARD_DEDUCTION_2025["single"]))


def _money(value: float) -> str:
    return f"${value:,.2f}"


def _advisor_message(intake: dict[str, Any], proposal: dict[str, Any], review: dict[str, Any]) -> str:
    found = ", ".join(intake["found_forms"]) or "no source forms yet"
    warnings = review.get("warnings") or []
    warning_sentence = f" I want to pause on {len(warnings)} review issue(s) before you file." if warnings else ""
    return (
        "I took a first pass through your tax packet and built a draft Form 1040 map from "
        f"{found}. The big picture is AGI {proposal['line_map']['11_adjusted_gross_income']} "
        f"and taxable income {proposal['line_map']['15_taxable_income']}.{warning_sentence} "
        "Before we treat this as ready, I would like you to confirm the missing items and compare each number "
        "against the original PDFs."
    )


def main(argv: list[str] | None = None) -> None:
    run_blueprint_cli(run_blueprint, argv, default_blueprint_id=BLUEPRINT_ID)


if __name__ == "__main__":
    main()
