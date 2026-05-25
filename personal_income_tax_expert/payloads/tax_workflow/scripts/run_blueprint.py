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
from xml.sax.saxutils import escape


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
    from mn_blueprint_support import (
        architecture_contract,
        create_runtime_context,
        get_llm_client,
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

    class _FakeLLMClient:
        provider = "fake"
        model = "fake-deterministic-blueprint-agent"

        def __init__(self) -> None:
            self.calls = 0
            self.fallback_calls = 0
            self.prompts: list[dict[str, str]] = []

        def generate_json(
            self,
            *,
            system_prompt: str,
            user_prompt: str,
            fallback: dict[str, Any],
        ) -> dict[str, Any]:
            self.calls += 1
            self.prompts.append({"system": system_prompt, "user": user_prompt})
            response = copy.deepcopy(fallback)
            response.setdefault("confidence", 0.78)
            response.setdefault("rationale", "Deterministic fake tax specialist used the validated fallback packet.")
            response["provider"] = self.provider
            response["model"] = self.model
            return response

    def get_llm_client(mode: str | None = None) -> _FakeLLMClient:
        return _FakeLLMClient()

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

SPECIALIST_STAGES = [
    "client_intake_coordinator",
    "document_understanding_agent",
    "source_field_extractor",
    "income_preparer",
    "deductions_credits_preparer",
    "form_1040_assembler",
    "tax_auditor",
    "manager_reviewer",
    "advisor_report_writer",
]

SPECIALIST_STANDARD_KEYS = {
    "confidence",
    "llm_error",
    "model",
    "provider",
    "rationale",
    "role",
    "specialist",
    "used_fallback",
}

TRANSPORT_SOFT_LIMIT_BYTES = 3_500_000
TRANSPORT_HARD_LIMIT_BYTES = 3_900_000

RECOGNIZED_TAX_FORMS = {
    "W-2",
    "1099-INT",
    "1099-R",
    "1099-DIV",
    "1099-B",
    "1099-NEC",
    "1098",
    "1095-A",
    "5498",
    "brokerage_statement",
}

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
    "output_folder",
    "output_folder_path",
    "scenario",
    "tax_document_folder",
    "taxpayer_profile",
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
    llm_client: Any | None = None,
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
    llm = llm_client or _resolve_llm_client(resolved_config)
    context = create_runtime_context(blueprint_id, resolved_config, runtime_inputs, input_source)
    started_at = utc_now_iso()
    context.start()
    try:
        documents = _load_documents(resolved_config, runtime_inputs)
        context.event("tax_document_intake_completed", _document_summary(documents))

        client_intake = _client_intake_coordinator(documents, resolved_config, runtime_inputs, llm)
        context.event("client_intake_coordinator_completed", client_intake)

        document_dossier = _document_understanding_agent(documents, client_intake, resolved_config, llm)
        context.event("document_understanding_agent_completed", document_dossier)

        source_extraction = _source_field_extractor(documents, document_dossier, resolved_config, llm)
        context.event("source_field_extractor_completed", source_extraction)

        income_workpaper = _income_preparer(source_extraction, document_dossier, client_intake, resolved_config, llm)
        context.event("income_preparer_completed", income_workpaper)

        deductions_workpaper = _deductions_credits_preparer(source_extraction, client_intake, resolved_config, runtime_inputs, llm)
        context.event("deductions_credits_preparer_completed", deductions_workpaper)

        form_1040 = _form_1040_assembler(
            source_extraction,
            income_workpaper,
            deductions_workpaper,
            client_intake,
            resolved_config,
            llm,
        )
        context.event("form_1040_assembler_completed", form_1040)

        audit_review = _tax_auditor(documents, source_extraction, form_1040, resolved_config, runtime_inputs, llm)
        context.event("tax_auditor_completed", audit_review)

        manager_review = _manager_reviewer(form_1040, audit_review, client_intake, resolved_config, llm)
        context.event("manager_reviewer_completed", manager_review)

        advisor_report = _advisor_report_writer(
            client_intake,
            document_dossier,
            form_1040,
            audit_review,
            manager_review,
            resolved_config,
            llm,
        )
        context.event("advisor_report_writer_completed", advisor_report)

        llm_metadata = _llm_metadata(llm, resolved_config)
        final_artifact = _packet_writer_agent(
            documents,
            client_intake,
            document_dossier,
            source_extraction,
            income_workpaper,
            deductions_workpaper,
            form_1040,
            audit_review,
            manager_review,
            advisor_report,
            llm_metadata,
            resolved_config,
            runtime_inputs,
        )
        output_files = _write_output_folder_artifacts(final_artifact, resolved_config, runtime_inputs)
        if output_files:
            final_artifact["output_files"] = output_files
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
                {"agent": "client_intake_coordinator", "output": client_intake},
                {"agent": "document_understanding_agent", "output": document_dossier},
                {"agent": "source_field_extractor", "output": source_extraction},
                {"agent": "income_preparer", "output": income_workpaper},
                {"agent": "deductions_credits_preparer", "output": deductions_workpaper},
                {"agent": "form_1040_assembler", "output": form_1040},
                {"agent": "tax_auditor", "output": audit_review},
                {"agent": "manager_reviewer", "output": manager_review},
                {"agent": "advisor_report_writer", "output": advisor_report},
                {"agent": "form_1040_packet_writer", "output": final_artifact},
            ],
            "final_artifact": final_artifact,
            "output_files": output_files,
            "warnings": _combined_warnings(audit_review, manager_review, final_artifact),
            "llm": llm_metadata,
        }
        transport_result = _compact_result_for_transport(result)
        context.finish(transport_result)
        return transport_result
    except Exception as error:
        context.fail(error)
        raise


def _resolve_llm_client(config: dict[str, Any]) -> Any:
    llm_config = config.get("llm") if isinstance(config.get("llm"), dict) else {}
    if llm_config.get("enabled") is False:
        return get_llm_client("fake")
    if os.environ.get("MN_BLUEPRINT_QUICK_TEST", "").strip().lower() in {"1", "true", "yes", "on"}:
        return get_llm_client("fake")
    mode = str(llm_config.get("mode") or os.environ.get("MN_BLUEPRINT_LLM_MODE") or "ollama").strip().lower()
    if mode in {"fake", "mock", "deterministic"}:
        return get_llm_client("fake")
    if mode in {"ollama", "live", "real"}:
        return get_llm_client("ollama")
    return get_llm_client(mode or None)


def _llm_metadata(llm: Any, config: dict[str, Any]) -> dict[str, Any]:
    llm_config = config.get("llm") if isinstance(config.get("llm"), dict) else {}
    return {
        "enabled": llm_config.get("enabled", True) is not False,
        "mode": str(llm_config.get("mode") or "ollama"),
        "provider": getattr(llm, "provider", "unknown"),
        "model": getattr(llm, "model", str(llm_config.get("model") or "unknown")),
        "api_base": str(llm_config.get("api_base") or "http://192.168.4.173:11434"),
        "calls": int(getattr(llm, "calls", 0) or 0),
        "fallback_calls": int(getattr(llm, "fallback_calls", 0) or 0),
        "specialist_stage_count": len(SPECIALIST_STAGES),
        "specialist_stages": list(SPECIALIST_STAGES),
    }


def _call_tax_specialist(
    llm: Any,
    *,
    stage: str,
    role: str,
    responsibilities: list[str],
    payload: dict[str, Any],
    fallback: dict[str, Any],
) -> dict[str, Any]:
    system_prompt = (
        f"You are the {role} on a U.S. personal income tax preparation team. "
        "Read tax documents like a careful preparer, keep every conclusion source-grounded, "
        "return only JSON, and never mark the packet as filing-ready."
    )
    user_prompt = json.dumps(
        {
            "stage": stage,
            "responsibilities": responsibilities,
            "privacy": "Tax identifiers have been redacted where possible. Treat all content as regulated tax data.",
            "draft_only_policy": "This is a draft review packet, not an official IRS form or e-file submission.",
            "payload": payload,
            "fallback_schema": fallback,
        },
        indent=2,
        sort_keys=True,
    )
    merged = copy.deepcopy(fallback)
    try:
        response = llm.generate_json(system_prompt=system_prompt, user_prompt=user_prompt, fallback=fallback)
        if isinstance(response, dict):
            allowed_keys = set(fallback) | SPECIALIST_STANDARD_KEYS
            for key, value in response.items():
                if key in allowed_keys and value is not None:
                    merged[key] = _compact_json_value(value, string_limit=5000, list_limit=120, dict_key_limit=120)
    except Exception as error:
        merged["llm_error"] = str(error)
        merged["used_fallback"] = True
        if hasattr(llm, "fallback_calls"):
            try:
                llm.fallback_calls += 1
            except Exception:
                pass
    merged["role"] = stage
    merged["specialist"] = role
    merged["provider"] = merged.get("provider") or getattr(llm, "provider", "unknown")
    merged["model"] = merged.get("model") or getattr(llm, "model", "unknown")
    return _compact_json_value(merged, string_limit=5000, list_limit=160, dict_key_limit=140)


def _documents_for_prompt(documents: list[dict[str, Any]], *, max_chars: int = 1800) -> list[dict[str, Any]]:
    prompt_docs = []
    for document in documents:
        text = str(document.get("text") or "")
        prompt_docs.append(
            {
                "filename": document.get("filename"),
                "document_type": document.get("document_type"),
                "extraction_method": document.get("extraction_method"),
                "ocr_required": bool(document.get("ocr_required")),
                "warnings": list(document.get("warnings") or []),
                "text_excerpt": redact_tax_identifiers(text[:max_chars]),
            }
        )
    return prompt_docs


def _compact_result_for_transport(result: dict[str, Any]) -> dict[str, Any]:
    compact = copy.deepcopy(result)
    compact["transport"] = {
        "compacted": False,
        "soft_limit_bytes": TRANSPORT_SOFT_LIMIT_BYTES,
        "hard_limit_bytes": TRANSPORT_HARD_LIMIT_BYTES,
    }
    size = _json_size(compact)
    if size <= TRANSPORT_SOFT_LIMIT_BYTES:
        compact["transport"]["size_bytes"] = size
        return compact

    compact["transport"]["compacted"] = True
    compact["transport"]["original_size_bytes"] = size
    if isinstance(compact.get("config"), dict):
        compact["config"] = _config_summary_for_transport(compact["config"])
    if isinstance(compact.get("architecture"), dict):
        compact["architecture"] = _compact_json_value(compact["architecture"], string_limit=1000, list_limit=30, dict_key_limit=50)
    if isinstance(compact.get("timeline"), list):
        compact["timeline"] = [_timeline_item_summary(item) for item in compact["timeline"]]

    size = _json_size(compact)
    if size > TRANSPORT_HARD_LIMIT_BYTES:
        compact["final_artifact"] = _final_artifact_summary_for_transport(compact.get("final_artifact", {}))
        compact["transport"]["final_artifact_compacted"] = True

    compact = _compact_json_value(compact, string_limit=8000, list_limit=240, dict_key_limit=180)
    compact["transport"]["size_bytes"] = _json_size(compact)
    return compact


def _json_size(value: Any) -> int:
    return len(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8"))


def _config_summary_for_transport(config: dict[str, Any]) -> dict[str, Any]:
    llm_config = config.get("llm") if isinstance(config.get("llm"), dict) else {}
    outputs = config.get("outputs") if isinstance(config.get("outputs"), dict) else {}
    tax_documents = config.get("tax_documents") if isinstance(config.get("tax_documents"), dict) else {}
    return {
        "identity": config.get("identity"),
        "mode": config.get("mode"),
        "metadata": config.get("metadata"),
        "tax_profile": config.get("tax_profile"),
        "tax_documents": {
            "folder_path": tax_documents.get("folder_path", ""),
            "recommended_forms": tax_documents.get("recommended_forms", []),
            "accepted_forms": tax_documents.get("accepted_forms", []),
            "sample_document_count": len(tax_documents.get("sample_documents", []) or []),
        },
        "llm": {
            "enabled": llm_config.get("enabled", True),
            "mode": llm_config.get("mode"),
            "api_base": llm_config.get("api_base"),
            "model": llm_config.get("model"),
            "agent_count": len(llm_config.get("agents", {}) or {}),
        },
        "outputs": {
            "adapter": outputs.get("adapter"),
            "folder_path": outputs.get("folder_path"),
            "run_root": outputs.get("run_root"),
            "write_run_store": outputs.get("write_run_store"),
        },
    }


def _timeline_item_summary(item: Any) -> dict[str, Any]:
    if not isinstance(item, dict):
        return {"output": _compact_json_value(item, string_limit=1000, list_limit=20, dict_key_limit=20)}
    output = item.get("output")
    agent = item.get("agent")
    if agent == "form_1040_packet_writer":
        output_summary = _final_artifact_summary_for_transport(output if isinstance(output, dict) else {})
    else:
        output_summary = _compact_json_value(output, string_limit=2000, list_limit=50, dict_key_limit=60)
    return {"agent": agent, "output": output_summary}


def _final_artifact_summary_for_transport(final_artifact: Any) -> dict[str, Any]:
    if not isinstance(final_artifact, dict):
        return {"summary": _compact_json_value(final_artifact, string_limit=1000, list_limit=20, dict_key_limit=20)}
    prepared = final_artifact.get("prepared_form_1040") if isinstance(final_artifact.get("prepared_form_1040"), dict) else {}
    return {
        "type": final_artifact.get("type"),
        "title": final_artifact.get("title"),
        "tax_year": final_artifact.get("tax_year"),
        "status": final_artifact.get("status"),
        "draft_warning": final_artifact.get("draft_warning"),
        "prepared_form_1040": {
            "filing_status": prepared.get("filing_status"),
            "line_map": prepared.get("line_map"),
            "assumptions": _compact_json_value(prepared.get("assumptions", []), string_limit=1200, list_limit=20, dict_key_limit=20),
            "questions_for_user": _compact_json_value(prepared.get("questions_for_user", []), string_limit=1200, list_limit=20, dict_key_limit=20),
            "schedule_review_flags": _compact_json_value(prepared.get("schedule_review_flags", []), string_limit=1200, list_limit=20, dict_key_limit=20),
        },
        "advisor_message": _compact_json_value(final_artifact.get("advisor_message", ""), string_limit=2500),
        "document_summary": final_artifact.get("document_summary"),
        "review": _compact_json_value(final_artifact.get("review", {}), string_limit=1600, list_limit=30, dict_key_limit=40),
        "manager_review": _compact_json_value(final_artifact.get("manager_review", {}), string_limit=1600, list_limit=30, dict_key_limit=40),
        "next_steps": _compact_json_value(final_artifact.get("next_steps", []), string_limit=1200, list_limit=20, dict_key_limit=20),
        "output_files": final_artifact.get("output_files", []),
        "llm": final_artifact.get("llm"),
        "compaction_note": "Large workpapers were omitted from the API transport response; inspect the local output files for full packet details.",
    }


def _compact_json_value(
    value: Any,
    *,
    string_limit: int = 4000,
    list_limit: int = 80,
    dict_key_limit: int = 80,
    _depth: int = 0,
) -> Any:
    if _depth > 8:
        return _compact_leaf(value, string_limit)
    if isinstance(value, str):
        return _truncate_string(value, string_limit)
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    if isinstance(value, list):
        compacted = [
            _compact_json_value(item, string_limit=string_limit, list_limit=list_limit, dict_key_limit=dict_key_limit, _depth=_depth + 1)
            for item in value[:list_limit]
        ]
        if len(value) > list_limit:
            compacted.append({"_truncated_items": len(value) - list_limit})
        return compacted
    if isinstance(value, dict):
        compacted_dict: dict[str, Any] = {}
        for index, (key, item) in enumerate(value.items()):
            if index >= dict_key_limit:
                compacted_dict["_truncated_keys"] = len(value) - dict_key_limit
                break
            compacted_dict[str(key)] = _compact_json_value(
                item,
                string_limit=string_limit,
                list_limit=list_limit,
                dict_key_limit=dict_key_limit,
                _depth=_depth + 1,
            )
        return compacted_dict
    return _compact_leaf(value, string_limit)


def _compact_leaf(value: Any, string_limit: int) -> str:
    return _truncate_string(str(value), string_limit)


def _truncate_string(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    omitted = len(value) - limit
    return f"{value[:limit]}...[truncated {omitted} chars]"


def _client_intake_coordinator(
    documents: list[dict[str, Any]],
    config: dict[str, Any],
    runtime_inputs: dict[str, Any],
    llm: Any,
) -> dict[str, Any]:
    intake = _intake_agent(documents, config, runtime_inputs)
    fallback = {
        **intake,
        "role": "client_intake_coordinator",
        "engagement_scope": "federal_form_1040_draft_review_packet",
        "taxpayer_confirmations_needed": [
            "legal name, SSN, current mailing address, and signature authority",
            "filing status, dependents, age/blindness, and dependency status",
            "complete income documents, deductions, credits, and estimated tax payments",
        ],
        "draft_only_disclosure": "This packet organizes a draft Form 1040 review and is not a filed return.",
    }
    result = _call_tax_specialist(
        llm,
        stage="client_intake_coordinator",
        role="Client Intake Coordinator",
        responsibilities=[
            "confirm engagement scope",
            "identify missing taxpayer profile facts",
            "build a preparer-style intake checklist",
        ],
        payload={
            "runtime_inputs": runtime_inputs,
            "document_summary": _document_summary(documents),
            "documents": _documents_for_prompt(documents, max_chars=700),
        },
        fallback=fallback,
    )
    result["tax_year"] = _safe_int(result.get("tax_year"), fallback["tax_year"])
    result["filing_status"] = _normalize_status(str(result.get("filing_status") or fallback["filing_status"]))
    result["found_forms"] = sorted(set(str(item) for item in _as_list(result.get("found_forms"), fallback["found_forms"])))
    result["missing_or_unconfirmed"] = sorted(
        set(str(item) for item in _as_list(result.get("missing_or_unconfirmed"), fallback["missing_or_unconfirmed"]))
    )
    result["needs_ocr"] = _as_list(result.get("needs_ocr"), fallback.get("needs_ocr", []))
    return result


def _document_understanding_agent(
    documents: list[dict[str, Any]],
    intake: dict[str, Any],
    config: dict[str, Any],
    llm: Any,
) -> dict[str, Any]:
    understood_documents = []
    complex_forms = []
    for document in documents:
        doc_type = str(document.get("document_type") or "unknown_tax_document")
        if doc_type not in {"W-2", "1099-INT", "1099-R"}:
            complex_forms.append(doc_type)
        understood_documents.append(
            {
                "filename": document.get("filename"),
                "document_type": doc_type,
                "recognized": doc_type in RECOGNIZED_TAX_FORMS,
                "extraction_method": document.get("extraction_method"),
                "ocr_required": bool(document.get("ocr_required")),
                "preparer_summary": _document_preparer_summary(doc_type),
                "routing_notes": _document_routing_notes(doc_type),
                "warnings": list(document.get("warnings") or []),
            }
        )
    fallback = {
        "role": "document_understanding_agent",
        "documents": understood_documents,
        "document_types": _document_summary(documents)["document_types"],
        "complex_or_partially_supported_forms": sorted(set(complex_forms)),
        "missing_profile_facts": intake.get("missing_or_unconfirmed", []),
        "review_notes": [
            "Use source documents only for draft mapping until taxpayer profile facts are confirmed.",
            "Treat non-core forms as schedule review triggers unless a specialist workpaper supports a line.",
        ],
    }
    result = _call_tax_specialist(
        llm,
        stage="document_understanding_agent",
        role="Document Understanding Agent",
        responsibilities=[
            "classify each tax document",
            "explain what each form means for Form 1040 preparation",
            "separate simple source forms from schedule-triggering forms",
        ],
        payload={"intake": intake, "documents": _documents_for_prompt(documents)},
        fallback=fallback,
    )
    if not isinstance(result.get("documents"), list):
        result["documents"] = fallback["documents"]
    if not isinstance(result.get("document_types"), dict):
        result["document_types"] = fallback["document_types"]
    result["complex_or_partially_supported_forms"] = sorted(
        set(str(item) for item in _as_list(result.get("complex_or_partially_supported_forms"), fallback["complex_or_partially_supported_forms"]))
    )
    return result


def _source_field_extractor(
    documents: list[dict[str, Any]],
    document_dossier: dict[str, Any],
    config: dict[str, Any],
    llm: Any,
) -> dict[str, Any]:
    values = _extract_values(documents)
    fallback = {
        "role": "source_field_extractor",
        "totals": _money_totals(values),
        "numeric_totals": _numeric_totals(values),
        "source_fields": values["field_facts"],
        "evidence": values["evidence"],
        "extraction_limits": values["extraction_limits"],
        "confidence": 0.82 if values["evidence"] else 0.35,
        "rationale": "Validated source fields with deterministic extraction and preserved evidence for preparer review.",
    }
    result = _call_tax_specialist(
        llm,
        stage="source_field_extractor",
        role="Source Field Extractor",
        responsibilities=[
            "read document text and identify source boxes",
            "extract money fields with source evidence",
            "flag OCR or unsupported fields instead of guessing",
        ],
        payload={"document_dossier": document_dossier, "documents": _documents_for_prompt(documents)},
        fallback=fallback,
    )
    result["numeric_totals"] = fallback["numeric_totals"]
    result["totals"] = fallback["totals"]
    result["source_fields"] = result.get("source_fields") if isinstance(result.get("source_fields"), list) else fallback["source_fields"]
    result["evidence"] = result.get("evidence") if isinstance(result.get("evidence"), list) else fallback["evidence"]
    result["extraction_limits"] = result.get("extraction_limits") if isinstance(result.get("extraction_limits"), list) else fallback["extraction_limits"]
    return result


def _income_preparer(
    source_extraction: dict[str, Any],
    document_dossier: dict[str, Any],
    intake: dict[str, Any],
    config: dict[str, Any],
    llm: Any,
) -> dict[str, Any]:
    totals = source_extraction["numeric_totals"]
    fallback = {
        "role": "income_preparer",
        "workpaper_type": "income_line_workpaper",
        "line_items": {
            "1z_wages": _money(totals["wages"]),
            "2b_taxable_interest": _money(totals["taxable_interest"]),
            "3a_qualified_dividends_review": _money(totals["qualified_dividends"]),
            "3b_ordinary_dividends_review": _money(totals["ordinary_dividends"]),
            "4b_taxable_ira_pensions_annuities": _money(totals["retirement_taxable"]),
            "7_capital_gain_or_loss_review": "review_required" if totals["brokerage_proceeds"] else _money(0.0),
        },
        "unsupported_or_review_required_income": _income_review_items(document_dossier, totals),
        "assumptions": [
            "Only source-supported income lines are included in the draft.",
            "Brokerage, self-employment, and dividend details remain review-required unless complete schedules are supplied.",
        ],
        "source_evidence": source_extraction.get("evidence", []),
    }
    result = _call_tax_specialist(
        llm,
        stage="income_preparer",
        role="Income Preparer",
        responsibilities=[
            "prepare income workpapers",
            "map source fields to Form 1040 income lines",
            "flag schedule-triggering income for review",
        ],
        payload={"intake": intake, "document_dossier": document_dossier, "source_extraction": source_extraction},
        fallback=fallback,
    )
    if not isinstance(result.get("line_items"), dict):
        result["line_items"] = fallback["line_items"]
    if not isinstance(result.get("unsupported_or_review_required_income"), list):
        result["unsupported_or_review_required_income"] = fallback["unsupported_or_review_required_income"]
    return result


def _deductions_credits_preparer(
    source_extraction: dict[str, Any],
    intake: dict[str, Any],
    config: dict[str, Any],
    runtime_inputs: dict[str, Any],
    llm: Any,
) -> dict[str, Any]:
    filing_status = _normalize_status(str(intake.get("filing_status") or "single"))
    deduction = _standard_deduction(config, filing_status)
    totals = source_extraction["numeric_totals"]
    fallback = {
        "role": "deductions_credits_preparer",
        "workpaper_type": "deductions_credits_review",
        "deduction_method": "standard_deduction_pending_itemized_review",
        "standard_deduction": _money(deduction),
        "itemized_deductions_review": [
            "Mortgage interest on Form 1098 is a Schedule A review item." if totals["mortgage_interest"] else "No itemized deduction source amount was mapped in this draft.",
            "State and local tax, charitable gifts, medical expenses, and other Schedule A facts are unconfirmed.",
        ],
        "credits_review": _credits_review_items(source_extraction),
        "assumptions": [
            f"Filing status is treated as {filing_status.replace('_', ' ')} until the taxpayer confirms it.",
            "Standard deduction is used in the draft unless itemized deductions are supplied and reviewed.",
            "Credits are not claimed without a supporting source document and taxpayer facts.",
        ],
    }
    result = _call_tax_specialist(
        llm,
        stage="deductions_credits_preparer",
        role="Deductions and Credits Preparer",
        responsibilities=[
            "choose draft standard deduction treatment",
            "flag itemized deduction evidence",
            "identify credits that require follow-up",
        ],
        payload={
            "intake": intake,
            "runtime_inputs": runtime_inputs,
            "source_extraction": source_extraction,
            "tax_knowledge": config.get("tax_knowledge", {}),
        },
        fallback=fallback,
    )
    result["standard_deduction"] = fallback["standard_deduction"]
    if not isinstance(result.get("assumptions"), list):
        result["assumptions"] = fallback["assumptions"]
    return result


def _form_1040_assembler(
    source_extraction: dict[str, Any],
    income_workpaper: dict[str, Any],
    deductions_workpaper: dict[str, Any],
    intake: dict[str, Any],
    config: dict[str, Any],
    llm: Any,
) -> dict[str, Any]:
    totals = source_extraction["numeric_totals"]
    filing_status = _normalize_status(str(intake.get("filing_status") or "single"))
    deduction = _standard_deduction(config, filing_status)
    agi = totals["wages"] + totals["taxable_interest"] + totals["retirement_taxable"] + totals["ordinary_dividends"]
    taxable_income = max(0.0, agi - deduction)
    line_map = {
        "1z_wages": _money(totals["wages"]),
        "2b_taxable_interest": _money(totals["taxable_interest"]),
        "3b_ordinary_dividends_review": _money(totals["ordinary_dividends"]),
        "4b_taxable_ira_pensions_annuities": _money(totals["retirement_taxable"]),
        "7_capital_gain_or_loss_review": "review_required" if totals["brokerage_proceeds"] else _money(0.0),
        "11_adjusted_gross_income": _money(agi),
        "12_standard_deduction": _money(deduction),
        "15_taxable_income": _money(taxable_income),
        "25d_total_federal_income_tax_withheld": _money(totals["federal_withholding"]),
    }
    fallback = {
        "role": "form_1040_assembler",
        "proposal_type": "draft_form_1040_line_mapping",
        "filing_status": filing_status,
        "line_map": line_map,
        "evidence": source_extraction.get("evidence", []),
        "assumptions": list(deductions_workpaper.get("assumptions") or []),
        "schedule_review_flags": _schedule_review_flags(source_extraction, income_workpaper, deductions_workpaper),
        "questions_for_user": _questions_for_user(intake, {"federal_withholding": totals["federal_withholding"]}, {}, config),
    }
    result = _call_tax_specialist(
        llm,
        stage="form_1040_assembler",
        role="Form 1040 Assembler",
        responsibilities=[
            "assemble supported Form 1040 draft lines",
            "preserve source evidence and assumptions",
            "avoid unsupported tax calculations",
        ],
        payload={
            "intake": intake,
            "income_workpaper": income_workpaper,
            "deductions_workpaper": deductions_workpaper,
            "source_extraction": source_extraction,
        },
        fallback=fallback,
    )
    result["line_map"] = _normalized_line_map(result.get("line_map"), fallback["line_map"])
    result["questions_for_user"] = _as_list(result.get("questions_for_user"), fallback["questions_for_user"])
    result["assumptions"] = _as_list(result.get("assumptions"), fallback["assumptions"])
    result["evidence"] = result.get("evidence") if isinstance(result.get("evidence"), list) else fallback["evidence"]
    return result


def _tax_auditor(
    documents: list[dict[str, Any]],
    source_extraction: dict[str, Any],
    form_1040: dict[str, Any],
    config: dict[str, Any],
    runtime_inputs: dict[str, Any],
    llm: Any,
) -> dict[str, Any]:
    proposal = {
        "line_map": form_1040["line_map"],
        "evidence": source_extraction.get("evidence", []),
        "questions_for_user": form_1040.get("questions_for_user", []),
    }
    base_review = _review_agent(documents, proposal, config, runtime_inputs)
    warnings = list(base_review["warnings"])
    warnings.extend(source_extraction.get("extraction_limits", []))
    warnings.extend(form_1040.get("schedule_review_flags", []))
    fallback = {
        **base_review,
        "role": "tax_auditor",
        "review_status": "needs_human_review",
        "warnings": sorted(set(warnings)),
        "audit_findings": [
            "Core income and withholding lines have source-backed draft values where available.",
            "Schedule-triggering forms are flagged for review instead of silently included.",
            "The packet should be compared against original documents before any filing workflow.",
        ],
        "source_tie_out": {
            "source_field_count": len(source_extraction.get("source_fields", [])),
            "evidence_count": len(source_extraction.get("evidence", [])),
        },
    }
    result = _call_tax_specialist(
        llm,
        stage="tax_auditor",
        role="Tax Auditor",
        responsibilities=[
            "audit source support",
            "identify filing risks and missing evidence",
            "block unsupported return-ready claims",
        ],
        payload={"source_extraction": source_extraction, "form_1040": form_1040, "documents": _documents_for_prompt(documents, max_chars=600)},
        fallback=fallback,
    )
    result["warnings"] = sorted(set(str(item) for item in _as_list(result.get("warnings"), fallback["warnings"])))
    result["review_status"] = "needs_human_review"
    return result


def _manager_reviewer(
    form_1040: dict[str, Any],
    audit_review: dict[str, Any],
    intake: dict[str, Any],
    config: dict[str, Any],
    llm: Any,
) -> dict[str, Any]:
    blockers = list(audit_review.get("warnings") or [])
    if form_1040.get("questions_for_user"):
        blockers.append("Open taxpayer questions remain before the draft can be treated as complete.")
    fallback = {
        "role": "manager_reviewer",
        "review_status": "manager_review_required",
        "manager_signoff": "not_approved_for_filing",
        "blockers": sorted(set(blockers)),
        "quality_score": 0.72 if audit_review.get("evidence_count") else 0.6,
        "manager_notes": [
            "Prepared as a review packet only.",
            "A human taxpayer or qualified preparer must confirm identity, filing status, dependents, and all source forms.",
        ],
    }
    result = _call_tax_specialist(
        llm,
        stage="manager_reviewer",
        role="Tax Manager Reviewer",
        responsibilities=[
            "perform manager-level review",
            "decide whether the packet is ready for human review",
            "write final blockers and signoff status",
        ],
        payload={"intake": intake, "form_1040": form_1040, "audit_review": audit_review},
        fallback=fallback,
    )
    result["manager_signoff"] = "not_approved_for_filing"
    result["review_status"] = "manager_review_required"
    result["blockers"] = sorted(set(str(item) for item in _as_list(result.get("blockers"), fallback["blockers"])))
    return result


def _advisor_report_writer(
    intake: dict[str, Any],
    document_dossier: dict[str, Any],
    form_1040: dict[str, Any],
    audit_review: dict[str, Any],
    manager_review: dict[str, Any],
    config: dict[str, Any],
    llm: Any,
) -> dict[str, Any]:
    advisor_message = _advisor_message_from_form(intake, form_1040, audit_review)
    fallback = {
        "role": "advisor_report_writer",
        "advisor_message": advisor_message,
        "next_steps": [
            "Upload or point me to the complete local folder for W-2, 1099, 1098, 1095-A, and brokerage forms.",
            "Confirm filing status, dependents, address, age/blindness, and whether anyone can claim you as a dependent.",
            "Review each draft Form 1040 line against the original source documents before using tax software or filing.",
            "Resolve manager blockers and schedule-review flags with a taxpayer or qualified preparer.",
        ],
        "plain_english_summary": "The team prepared a source-grounded federal Form 1040 draft review packet with open review items.",
        "tone": "warm, direct, evidence-grounded, and careful",
    }
    result = _call_tax_specialist(
        llm,
        stage="advisor_report_writer",
        role="Advisor and Report Writer",
        responsibilities=[
            "explain the draft in plain English",
            "summarize open review items",
            "prepare the user-facing report voice",
        ],
        payload={
            "intake": intake,
            "document_dossier": document_dossier,
            "form_1040": form_1040,
            "audit_review": audit_review,
            "manager_review": manager_review,
        },
        fallback=fallback,
    )
    result["advisor_message"] = str(result.get("advisor_message") or fallback["advisor_message"])
    result["next_steps"] = _as_list(result.get("next_steps"), fallback["next_steps"])
    return result


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
    if "1099-div" in haystack or "dividends and distributions" in haystack or "ordinary dividends" in haystack:
        return "1099-DIV"
    if "1099-b" in haystack or "proceeds from broker" in haystack or "cost or other basis" in haystack:
        return "1099-B"
    if "1099-nec" in haystack or "nonemployee compensation" in haystack:
        return "1099-NEC"
    if "form 1098" in haystack or "mortgage interest statement" in haystack:
        return "1098"
    if "1095-a" in haystack or "health insurance marketplace statement" in haystack:
        return "1095-A"
    if "form 5498" in haystack or "ira contribution information" in haystack:
        return "5498"
    if "brokerage" in haystack or "consolidated tax statement" in haystack:
        return "brokerage_statement"
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
    document_dossier: dict[str, Any],
    source_extraction: dict[str, Any],
    income_workpaper: dict[str, Any],
    deductions_workpaper: dict[str, Any],
    form_1040: dict[str, Any],
    audit_review: dict[str, Any],
    manager_review: dict[str, Any],
    advisor_report: dict[str, Any],
    llm_metadata: dict[str, Any],
    config: dict[str, Any],
    runtime_inputs: dict[str, Any],
) -> dict[str, Any]:
    tax_year = intake["tax_year"]
    advisor_message = str(advisor_report.get("advisor_message") or _advisor_message_from_form(intake, form_1040, audit_review))
    return {
        "type": "prepared_1040_tax_packet",
        "title": "Prepared Form 1040 Draft - What Is a 1040 Tax Form",
        "tax_year": tax_year,
        "status": "draft_needs_review",
        "draft_warning": "Draft review packet only. This is not an official IRS form, not a filed return, and not an e-file submission.",
        "what_is_a_1040_tax_form": (
            "Form 1040 is the main U.S. individual income tax return. "
            "This packet maps extracted income and withholding evidence to likely Form 1040 lines, "
            "but it is not a filed return and it still needs taxpayer or preparer review."
        ),
        "prepared_form_1040": {
            "filing_status": intake["filing_status"],
            "line_map": form_1040["line_map"],
            "source_evidence": form_1040.get("evidence", []),
            "assumptions": form_1040.get("assumptions", []),
            "schedule_review_flags": form_1040.get("schedule_review_flags", []),
            "questions_for_user": form_1040.get("questions_for_user", []),
        },
        "document_dossier": document_dossier,
        "preparer_workpapers": {
            "source_field_extraction": source_extraction,
            "income": income_workpaper,
            "deductions_and_credits": deductions_workpaper,
            "form_1040_assembly": form_1040,
        },
        "audit_review": audit_review,
        "manager_review": manager_review,
        "advisor_message": advisor_message,
        "conversation_context": {
            "advisor_voice": "personal_tax_advisor",
            "opening": advisor_message,
            "next_best_questions": form_1040.get("questions_for_user", []),
            "review_status": audit_review["review_status"],
            "manager_signoff": manager_review.get("manager_signoff"),
        },
        "document_summary": _document_summary(documents),
        "review": audit_review,
        "next_steps": advisor_report.get("next_steps", []),
        "llm": llm_metadata,
        "knowledge_sources": list((config.get("knowledge") or {}).get("irs_sources") or []),
    }


def _write_output_folder_artifacts(
    final_artifact: dict[str, Any],
    config: dict[str, Any],
    runtime_inputs: dict[str, Any],
) -> list[dict[str, str]]:
    folder_value = _output_folder_value(config, runtime_inputs)
    if not folder_value:
        return []

    output_dir = _expand_output_folder(folder_value, config)
    run_id = str((config.get("identity") or {}).get("run_id") or "tax-run")
    report_base = run_id if run_id.startswith("personal_income_tax_expert") else f"personal_income_tax_expert-{run_id}"
    stem = _safe_filename(report_base)
    json_path = output_dir / f"{stem}-final-artifact.json"
    markdown_path = output_dir / f"{stem}-report.md"
    pdf_path = output_dir / f"{stem}-tax-review-packet.pdf"

    try:
        output_dir.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        final_artifact.setdefault("output_warnings", []).append(
            f"Could not write output folder artifacts to {output_dir}: {error}"
        )
        return []

    output_files = [
        {"kind": "final_artifact_json", "path": str(json_path)},
        {"kind": "report_markdown", "path": str(markdown_path)},
    ]
    try:
        _write_final_artifact_pdf(final_artifact, pdf_path)
        output_files.append({"kind": "tax_review_packet_pdf", "path": str(pdf_path)})
    except ImportError as error:
        final_artifact.setdefault("output_warnings", []).append(
            f"PDF review packet was skipped because reportlab is unavailable: {error}"
        )
    except OSError as error:
        final_artifact.setdefault("output_warnings", []).append(
            f"Could not write PDF review packet to {pdf_path}: {error}"
        )
    except Exception as error:
        final_artifact.setdefault("output_warnings", []).append(
            f"Could not render PDF review packet: {error}"
        )
    final_artifact["output_files"] = output_files
    try:
        json_path.write_text(json.dumps(final_artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        markdown_path.write_text(_render_final_artifact_markdown(final_artifact), encoding="utf-8")
    except OSError as error:
        final_artifact.setdefault("output_warnings", []).append(
            f"Could not write output folder artifacts to {output_dir}: {error}"
        )
        return []
    return output_files


def _output_folder_value(config: dict[str, Any], runtime_inputs: dict[str, Any]) -> str:
    outputs = config.get("outputs") if isinstance(config.get("outputs"), dict) else {}
    return str(
        runtime_inputs.get("output_folder")
        or runtime_inputs.get("output_folder_path")
        or outputs.get("folder_path")
        or outputs.get("output_folder")
        or ""
    ).strip()


def _expand_output_folder(value: str, config: dict[str, Any]) -> Path:
    if value == "~" or value.startswith("~/"):
        home = _host_home_from_config(config) or Path.home()
        suffix = value[2:] if value.startswith("~/") else ""
        return home / suffix
    return Path(value).expanduser()


def _host_home_from_config(config: dict[str, Any]) -> Path | None:
    run_root = str((config.get("outputs") or {}).get("run_root") or "").strip()
    if run_root.startswith("/Users/"):
        parts = Path(run_root).parts
        if len(parts) >= 3:
            return Path(parts[0]) / parts[1] / parts[2]
    return None


def _safe_filename(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip(".-")
    return safe or "personal_income_tax_expert-report"


def _render_final_artifact_markdown(final_artifact: dict[str, Any]) -> str:
    prepared = final_artifact.get("prepared_form_1040") if isinstance(final_artifact.get("prepared_form_1040"), dict) else {}
    review = final_artifact.get("review") if isinstance(final_artifact.get("review"), dict) else {}
    manager_review = final_artifact.get("manager_review") if isinstance(final_artifact.get("manager_review"), dict) else {}
    document_summary = final_artifact.get("document_summary") if isinstance(final_artifact.get("document_summary"), dict) else {}
    line_map = prepared.get("line_map") if isinstance(prepared.get("line_map"), dict) else {}
    warnings = review.get("warnings") if isinstance(review.get("warnings"), list) else []
    next_steps = final_artifact.get("next_steps") if isinstance(final_artifact.get("next_steps"), list) else []
    questions = prepared.get("questions_for_user") if isinstance(prepared.get("questions_for_user"), list) else []
    schedule_flags = prepared.get("schedule_review_flags") if isinstance(prepared.get("schedule_review_flags"), list) else []

    lines = [
        f"# {final_artifact.get('title') or 'Prepared Form 1040 Draft'}",
        "",
        f"**Draft warning:** {final_artifact.get('draft_warning') or 'Draft review packet only.'}",
        "",
        str(final_artifact.get("advisor_message") or "").strip(),
        "",
        "## Draft Form 1040 Line Map",
        "",
    ]
    for key, value in line_map.items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Document Summary", ""])
    lines.append(f"- Document count: {document_summary.get('document_count', 0)}")
    doc_types = document_summary.get("document_types") if isinstance(document_summary.get("document_types"), dict) else {}
    for key, value in doc_types.items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Review Warnings", ""])
    if warnings:
        lines.extend(f"- {warning}" for warning in warnings)
    else:
        lines.append("- None")
    lines.extend(["", "## Schedule Review Flags", ""])
    if schedule_flags:
        lines.extend(f"- {flag}" for flag in schedule_flags)
    else:
        lines.append("- None")
    lines.extend(["", "## Open Questions", ""])
    if questions:
        lines.extend(f"- {question}" for question in questions)
    else:
        lines.append("- None")
    lines.extend(["", "## Manager Review", ""])
    lines.append(f"- Review status: {manager_review.get('review_status', 'manager_review_required')}")
    lines.append(f"- Signoff: {manager_review.get('manager_signoff', 'not_approved_for_filing')}")
    blockers = manager_review.get("blockers") if isinstance(manager_review.get("blockers"), list) else []
    for blocker in blockers:
        lines.append(f"- Blocker: {blocker}")
    lines.extend(["", "## Next Steps", ""])
    if next_steps:
        lines.extend(f"- {step}" for step in next_steps)
    else:
        lines.append("- Review the packet with the taxpayer or a qualified preparer.")
    lines.extend(["", "This is a draft review packet, not a filed tax return.", ""])
    return "\n".join(lines)


def _write_final_artifact_pdf(final_artifact: dict[str, Any], path: Path) -> None:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    styles = getSampleStyleSheet()
    title_style = styles["Title"]
    heading_style = styles["Heading2"]
    body_style = styles["BodyText"]
    warning_style = ParagraphStyle(
        "DraftWarning",
        parent=body_style,
        textColor=colors.HexColor("#8A4B00"),
        backColor=colors.HexColor("#FFF3D4"),
        borderColor=colors.HexColor("#D28A00"),
        borderWidth=0.75,
        borderPadding=6,
        spaceAfter=10,
    )

    prepared = final_artifact.get("prepared_form_1040") if isinstance(final_artifact.get("prepared_form_1040"), dict) else {}
    review = final_artifact.get("review") if isinstance(final_artifact.get("review"), dict) else {}
    manager_review = final_artifact.get("manager_review") if isinstance(final_artifact.get("manager_review"), dict) else {}
    line_map = prepared.get("line_map") if isinstance(prepared.get("line_map"), dict) else {}

    story: list[Any] = []
    story.append(Paragraph(_pdf_text(final_artifact.get("title") or "Prepared Form 1040 Draft"), title_style))
    story.append(Paragraph(_pdf_text(final_artifact.get("draft_warning") or "Draft review packet only."), warning_style))
    story.append(Paragraph(_pdf_text(final_artifact.get("advisor_message") or ""), body_style))
    story.append(Spacer(1, 0.18 * inch))

    story.append(Paragraph("Draft Form 1040 Line Map", heading_style))
    line_rows = [["Line", "Draft Value"]]
    for key, value in line_map.items():
        line_rows.append([_pdf_text(key), _pdf_text(value)])
    story.append(_pdf_table(line_rows))

    story.append(Spacer(1, 0.12 * inch))
    story.append(Paragraph("Review Warnings", heading_style))
    warnings = review.get("warnings") if isinstance(review.get("warnings"), list) else []
    story.extend(_pdf_bullets(warnings or ["None"], body_style))

    story.append(Paragraph("Open Questions", heading_style))
    questions = prepared.get("questions_for_user") if isinstance(prepared.get("questions_for_user"), list) else []
    story.extend(_pdf_bullets(questions or ["None"], body_style))

    story.append(Paragraph("Manager Review And Signoff", heading_style))
    manager_rows = [
        ["Review status", manager_review.get("review_status", "manager_review_required")],
        ["Signoff", manager_review.get("manager_signoff", "not_approved_for_filing")],
    ]
    story.append(_pdf_table([[_pdf_text(left), _pdf_text(right)] for left, right in manager_rows]))
    story.append(Paragraph("Reviewer signoff: ________________________________", body_style))
    story.append(Paragraph("Date: ____________________", body_style))
    story.append(Paragraph("This packet is not filing-ready until all open items are reviewed.", warning_style))

    doc = SimpleDocTemplate(
        str(path),
        pagesize=letter,
        title=str(final_artifact.get("title") or "Prepared Form 1040 Draft"),
        rightMargin=0.65 * inch,
        leftMargin=0.65 * inch,
        topMargin=0.65 * inch,
        bottomMargin=0.65 * inch,
    )
    doc.build(story)


def _pdf_text(value: Any) -> str:
    return escape(str(value or ""))


def _pdf_table(rows: list[list[Any]]) -> Any:
    from reportlab.lib import colors
    from reportlab.platypus import Table, TableStyle

    table = Table(rows, hAlign="LEFT", repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E8EEF7")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#10233F")),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#AAB7C4")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return table


def _pdf_bullets(items: list[Any], style: Any) -> list[Any]:
    from reportlab.platypus import Paragraph

    return [Paragraph(f"- {_pdf_text(item)}", style) for item in items]


def _safe_int(value: Any, fallback: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(fallback)


def _as_list(value: Any, fallback: list[Any] | None = None) -> list[Any]:
    if isinstance(value, list):
        return value
    if value in (None, ""):
        return list(fallback or [])
    return [value]


def _combined_warnings(
    audit_review: dict[str, Any],
    manager_review: dict[str, Any],
    final_artifact: dict[str, Any],
) -> list[str]:
    warnings: list[str] = []
    warnings.extend(str(item) for item in _as_list(audit_review.get("warnings"), []))
    warnings.extend(str(item) for item in _as_list(manager_review.get("blockers"), []))
    warnings.extend(str(item) for item in _as_list(final_artifact.get("output_warnings"), []))
    return sorted(set(warnings))


def _document_preparer_summary(doc_type: str) -> str:
    summaries = {
        "W-2": "Employee wage and withholding source for Form 1040 wages and federal withholding.",
        "1099-INT": "Interest income source for taxable interest and possible Schedule B review.",
        "1099-R": "Retirement distribution source that may require rollover, code, and additional tax review.",
        "1099-DIV": "Dividend source that can affect ordinary dividends, qualified dividends, and capital gain distributions.",
        "1099-B": "Brokerage sale source that usually requires basis and Schedule D/Form 8949 review.",
        "1099-NEC": "Nonemployee compensation source that can imply Schedule C and self-employment tax.",
        "1098": "Mortgage interest source that matters only if itemized deductions are reviewed.",
        "1095-A": "Marketplace health insurance source that can require premium tax credit reconciliation.",
        "5498": "IRA information source used for contribution/basis review, not usually direct Form 1040 income.",
        "brokerage_statement": "Consolidated brokerage statement requiring dividend, interest, sale, and basis review.",
    }
    return summaries.get(doc_type, "Unrecognized tax document; human review is required before mapping.")


def _document_routing_notes(doc_type: str) -> list[str]:
    routes = {
        "W-2": ["Form 1040 line 1z wages", "Form 1040 withholding lines"],
        "1099-INT": ["Form 1040 line 2b taxable interest", "Schedule B review when thresholds or special cases apply"],
        "1099-R": ["Form 1040 line 4b taxable amount", "Schedule 2/Form 5329 review for early distributions or exception codes"],
        "1099-DIV": ["Form 1040 line 3b ordinary dividends", "Qualified dividends and capital gain worksheet review"],
        "1099-B": ["Schedule D/Form 8949 review", "Capital gain or loss review before Form 1040 line 7"],
        "1099-NEC": ["Schedule C review", "Schedule SE and Schedule 2 review"],
        "1098": ["Schedule A itemized deduction review"],
        "1095-A": ["Form 8962 premium tax credit reconciliation review"],
        "5498": ["IRA contribution and basis review"],
        "brokerage_statement": ["Dividend, interest, 1099-B, and Schedule D review"],
    }
    return routes.get(doc_type, ["Manual preparer routing required"])


def _money_totals(values: dict[str, Any]) -> dict[str, str]:
    return {key: _money(float(amount)) for key, amount in _numeric_totals(values).items()}


def _numeric_totals(values: dict[str, Any]) -> dict[str, float]:
    keys = [
        "wages",
        "taxable_interest",
        "retirement_taxable",
        "federal_withholding",
        "ordinary_dividends",
        "qualified_dividends",
        "capital_gain_distributions",
        "brokerage_proceeds",
        "nonemployee_compensation",
        "mortgage_interest",
        "advance_premium_tax_credit",
    ]
    return {key: float(values.get(key, 0.0) or 0.0) for key in keys}


def _income_review_items(document_dossier: dict[str, Any], totals: dict[str, float]) -> list[str]:
    items = []
    complex_forms = set(str(item) for item in _as_list(document_dossier.get("complex_or_partially_supported_forms"), []))
    if totals["ordinary_dividends"] or "1099-DIV" in complex_forms:
        items.append("Dividend treatment needs qualified dividend and capital gain distribution review.")
    if totals["brokerage_proceeds"] or "1099-B" in complex_forms or "brokerage_statement" in complex_forms:
        items.append("Brokerage sales need basis and Schedule D/Form 8949 review.")
    if totals["nonemployee_compensation"] or "1099-NEC" in complex_forms:
        items.append("Nonemployee compensation needs Schedule C and self-employment tax review.")
    if not items:
        items.append("No non-core income forms were mapped into the draft beyond supported source lines.")
    return items


def _credits_review_items(source_extraction: dict[str, Any]) -> list[str]:
    totals = source_extraction.get("numeric_totals") if isinstance(source_extraction.get("numeric_totals"), dict) else {}
    items = ["No credits are claimed in this draft without source support and taxpayer confirmation."]
    if float(totals.get("advance_premium_tax_credit", 0.0) or 0.0):
        items.append("Form 1095-A indicates marketplace insurance; Form 8962 premium tax credit reconciliation is required.")
    return items


def _schedule_review_flags(
    source_extraction: dict[str, Any],
    income_workpaper: dict[str, Any],
    deductions_workpaper: dict[str, Any],
) -> list[str]:
    flags = []
    flags.extend(str(item) for item in _as_list(income_workpaper.get("unsupported_or_review_required_income"), []))
    flags.extend(str(item) for item in _as_list(deductions_workpaper.get("credits_review"), []))
    totals = source_extraction.get("numeric_totals") if isinstance(source_extraction.get("numeric_totals"), dict) else {}
    if float(totals.get("mortgage_interest", 0.0) or 0.0):
        flags.append("Schedule A itemized deduction review is required before using mortgage interest.")
    return sorted(set(flag for flag in flags if flag and flag != "None"))


def _normalized_line_map(value: Any, fallback: dict[str, str]) -> dict[str, str]:
    if not isinstance(value, dict):
        return dict(fallback)
    normalized = dict(fallback)
    for key, fallback_value in fallback.items():
        candidate = value.get(key)
        if isinstance(candidate, (str, int, float)) and str(candidate).strip():
            normalized[key] = str(candidate)
        else:
            normalized[key] = fallback_value
    return normalized


def _advisor_message_from_form(intake: dict[str, Any], form_1040: dict[str, Any], review: dict[str, Any]) -> str:
    found = ", ".join(intake.get("found_forms") or []) or "no source forms yet"
    warnings = review.get("warnings") or []
    line_map = form_1040.get("line_map") if isinstance(form_1040.get("line_map"), dict) else {}
    warning_sentence = f" I want to pause on {len(warnings)} review issue(s) before you file." if warnings else ""
    return (
        "I took a first pass through your tax packet and built a draft Form 1040 map from "
        f"{found}. The big picture is AGI {line_map.get('11_adjusted_gross_income', '$0.00')} "
        f"and taxable income {line_map.get('15_taxable_income', '$0.00')}.{warning_sentence} "
        "Before we treat this as ready, I would like you to confirm the missing items and compare each number "
        "against the original PDFs."
    )


def _extract_values(documents: list[dict[str, Any]]) -> dict[str, Any]:
    values = {
        "wages": 0.0,
        "taxable_interest": 0.0,
        "retirement_taxable": 0.0,
        "federal_withholding": 0.0,
        "ordinary_dividends": 0.0,
        "qualified_dividends": 0.0,
        "capital_gain_distributions": 0.0,
        "brokerage_proceeds": 0.0,
        "nonemployee_compensation": 0.0,
        "mortgage_interest": 0.0,
        "advance_premium_tax_credit": 0.0,
        "evidence": [],
        "field_facts": [],
        "extraction_limits": [],
    }
    for document in documents:
        doc_type = str(document.get("document_type") or "")
        text = str(document.get("text") or "")
        if doc_type == "W-2":
            _add_amount(values, "wages", text, ("box 1 wages", "wages"), document, "Form 1040 line 1z")
            _add_amount(values, "federal_withholding", text, ("box 2 federal income tax withheld", "federal income tax withheld"), document, "Form 1040 withholding")
        elif doc_type == "1099-INT":
            _add_amount(values, "taxable_interest", text, ("box 1 interest income", "interest income"), document, "Form 1040 line 2b")
            _add_amount(values, "federal_withholding", text, ("box 4 federal income tax withheld", "federal income tax withheld"), document, "Form 1040 withholding")
        elif doc_type == "1099-R":
            _add_amount(values, "retirement_taxable", text, ("box 2a taxable amount", "taxable amount", "gross distribution"), document, "Form 1040 line 4b")
            _add_amount(values, "federal_withholding", text, ("box 4 federal income tax withheld", "federal income tax withheld"), document, "Form 1040 withholding")
        elif doc_type == "1099-DIV":
            _add_amount(values, "ordinary_dividends", text, ("box 1a total ordinary dividends", "ordinary dividends"), document, "Form 1040 line 3b review")
            _add_amount(values, "qualified_dividends", text, ("box 1b qualified dividends", "qualified dividends"), document, "Form 1040 line 3a review")
            _add_amount(values, "capital_gain_distributions", text, ("box 2a total capital gain distributions", "capital gain distributions"), document, "Schedule D review")
        elif doc_type in {"1099-B", "brokerage_statement"}:
            _add_amount(values, "brokerage_proceeds", text, ("gross proceeds", "proceeds", "sales price"), document, "Schedule D/Form 8949 review")
            values["extraction_limits"].append(f"{doc_type} requires basis and sale detail review before capital gain or loss can be drafted.")
        elif doc_type == "1099-NEC":
            _add_amount(values, "nonemployee_compensation", text, ("box 1 nonemployee compensation", "nonemployee compensation"), document, "Schedule C review")
            values["extraction_limits"].append("1099-NEC income requires Schedule C and self-employment tax review.")
        elif doc_type == "1098":
            _add_amount(values, "mortgage_interest", text, ("box 1 mortgage interest received", "mortgage interest received", "mortgage interest"), document, "Schedule A review")
        elif doc_type == "1095-A":
            _add_amount(values, "advance_premium_tax_credit", text, ("advance payment of premium tax credit", "premium tax credit"), document, "Form 8962 review")
            values["extraction_limits"].append("1095-A requires Form 8962 premium tax credit reconciliation before filing.")
        _record_evidence(values, document, doc_type)
    values["extraction_limits"] = sorted(set(values["extraction_limits"]))
    return values


def _add_amount(
    values: dict[str, Any],
    key: str,
    text: str,
    labels: tuple[str, ...],
    document: dict[str, Any],
    target_line: str,
) -> None:
    amount = _find_amount(text, labels)
    if amount is not None:
        values[key] += amount
        values["field_facts"].append(
            {
                "field": key,
                "amount": _money(amount),
                "source_label": labels[0],
                "target_line": target_line,
                "document_type": document.get("document_type"),
                "filename": document.get("filename"),
                "extraction_method": document.get("extraction_method"),
                "confidence": 0.86 if not document.get("ocr_required") else 0.48,
            }
        )


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
