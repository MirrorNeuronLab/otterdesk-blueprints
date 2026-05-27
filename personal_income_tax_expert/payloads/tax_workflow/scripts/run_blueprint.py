#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import sys
import tempfile
import time
import urllib.error
import urllib.request
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

    class _OllamaLLMClient:
        provider = "ollama"

        def __init__(self) -> None:
            self.model = _env_value("MN_LLM_MODEL", "LITELLM_MODEL", default="ollama/nemotron3:33b")
            if not self.model.startswith("ollama/"):
                self.model = f"ollama/{self.model}"
            self.api_base = _env_value("MN_LLM_API_BASE", "LITELLM_API_BASE", default="http://192.168.4.173:11434").rstrip("/")
            self.timeout_seconds = float(_env_value("MN_LLM_TIMEOUT_SECONDS", "LITELLM_TIMEOUT_SECONDS", default="90"))
            self.max_tokens = int(_env_value("MN_LLM_MAX_TOKENS", "LITELLM_MAX_TOKENS", default="1200"))
            self.num_retries = max(int(_env_value("MN_LLM_NUM_RETRIES", "LITELLM_NUM_RETRIES", default="1")), 0)
            self.retry_backoff_seconds = max(
                float(_env_value("MN_LLM_RETRY_BACKOFF_SECONDS", "LITELLM_RETRY_BACKOFF_SECONDS", default="1.0")),
                0.0,
            )
            self.calls = 0
            self.fallback_calls = 0
            self.prefer_shared_skill = False
            self.strict = True

        def generate_json(
            self,
            *,
            system_prompt: str,
            user_prompt: str,
            fallback: dict[str, Any],
        ) -> dict[str, Any]:
            self.calls += 1
            last_error: Exception | None = None
            for attempt in range(self.num_retries + 1):
                try:
                    text = self._generate_direct(system_prompt, user_prompt)
                    parsed = _parse_json_object(text)
                    parsed.setdefault("provider", self.provider)
                    parsed.setdefault("model", self.model)
                    return parsed
                except Exception as error:
                    last_error = error
                    if attempt < self.num_retries and self.retry_backoff_seconds:
                        time.sleep(self.retry_backoff_seconds * (2**attempt))
            raise RuntimeError(f"Ollama request failed or returned non-JSON: {last_error}") from last_error

        def _generate_direct(self, system_prompt: str, user_prompt: str) -> str:
            payload = {
                "model": self.model.removeprefix("ollama/"),
                "messages": [
                    {
                        "role": "system",
                        "content": f"{system_prompt}\nReturn only valid JSON.",
                    },
                    {"role": "user", "content": user_prompt},
                ],
                "stream": False,
                "format": "json",
                "options": {"num_predict": self.max_tokens, "temperature": 0.1},
            }
            request = urllib.request.Request(
                f"{self.api_base}/api/chat",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                data = json.loads(response.read().decode("utf-8"))
            message = data.get("message") if isinstance(data.get("message"), dict) else {}
            return str(message.get("content") or "")

    def _env_value(primary: str, legacy: str, *, default: str) -> str:
        value = os.environ.get(primary)
        if value is not None:
            return value.strip() or default
        return os.environ.get(legacy, default).strip() or default

    def _parse_json_object(text: str) -> dict[str, Any]:
        cleaned = str(text or "").strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```[a-zA-Z0-9_-]*\n?", "", cleaned)
            cleaned = re.sub(r"\n?```$", "", cleaned).strip()
        try:
            value = json.loads(cleaned)
        except json.JSONDecodeError:
            start = cleaned.find("{")
            end = cleaned.rfind("}")
            if start < 0 or end <= start:
                raise
            value = json.loads(cleaned[start : end + 1])
        if not isinstance(value, dict):
            raise ValueError("LLM response must be a JSON object")
        return value

    def get_llm_client(mode: str | None = None) -> Any:
        selected = str(mode or os.environ.get("MN_BLUEPRINT_LLM_MODE") or "ollama").strip().lower()
        if selected in {"fake", "mock", "deterministic"}:
            return _FakeLLMClient()
        if selected in {"ollama", "live", "real"}:
            return _OllamaLLMClient()
        raise ValueError(f"unknown LLM mode {selected!r}; expected fake or ollama")

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

TAX_TEAM_STAGES = [*SPECIALIST_STAGES, "form_1040_packet_writer"]
TAX_PROGRESS_STEPS = [
    ("initializing", "Initializing tax team", 0, "Preparing the tax co-worker run."),
    ("workspace", "Creating team workspace", 5, "Creating the filesystem workspace and artifact manifest."),
    ("document_intake", "Reading tax documents", 10, "Scanning source folders and registering document artifacts."),
    ("client_intake_coordinator", "Client intake coordinator", 18, "Building the engagement scope and missing-information checklist."),
    ("document_understanding_agent", "Document understanding", 27, "Classifying tax documents and summarizing tax meaning."),
    ("source_field_extractor", "Source field extraction", 36, "Extracting source fields and source evidence references."),
    ("income_preparer", "Income preparation", 45, "Preparing income workpapers and draft Form 1040 income lines."),
    ("deductions_credits_preparer", "Deductions and credits", 54, "Reviewing deduction strategy, credits, and adjustment evidence."),
    ("form_1040_assembler", "Form 1040 assembly", 63, "Assembling supported draft Form 1040 line mappings."),
    ("tax_auditor", "Tax audit review", 72, "Checking assumptions, support gaps, and compliance risks."),
    ("manager_reviewer", "Manager review", 81, "Applying manager signoff gates and filing-readiness blockers."),
    ("advisor_report_writer", "Advisor report", 90, "Writing client-facing advice, risks, and open questions."),
    ("form_1040_packet_writer", "Packet writing", 96, "Compiling the final JSON, Markdown, and PDF packet."),
    ("output_materialization", "Finalizing output files", 99, "Writing local output files and review packet artifacts."),
    ("completed", "Completed", 100, "Tax review packet is ready for inspection."),
]
TAX_PROGRESS_INDEX = {stage_id: index for index, (stage_id, *_rest) in enumerate(TAX_PROGRESS_STEPS)}
TAX_PROGRESS_BY_STAGE = {stage_id: (label, percent, detail) for stage_id, label, percent, detail in TAX_PROGRESS_STEPS}

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

TEAM_ARTIFACT_SNIPPET_CHARS = 700

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
    "llm_api_base",
    "llm_model",
    "ollama_base_url",
    "ollama_model",
    "output_folder",
    "output_folder_path",
    "scenario",
    "tax_document_folder",
    "taxpayer_profile",
    "tax_year",
}


class TaxTeamWorkspace:
    def __init__(self, root: Path, run_id: str) -> None:
        self.root = root
        self.run_id = run_id
        self.dirs = {
            "documents": self.root / "documents",
            "extracts": self.root / "extracts",
            "commands": self.root / "commands",
            "agent_outputs": self.root / "agent_outputs",
            "workpapers": self.root / "workpapers",
            "final": self.root / "final",
        }
        for folder in [self.root, *self.dirs.values()]:
            folder.mkdir(parents=True, exist_ok=True)
        self.manifest_path = self.root / "artifact_manifest.json"
        self.artifacts: dict[str, dict[str, Any]] = {}
        self.document_refs: list[str] = []
        self.manifest: dict[str, Any] = {
            "version": "mn.tax_team.artifact_manifest.v1",
            "run_id": run_id,
            "root": str(self.root),
            "created_at": utc_now_iso(),
            "transport_policy": "Commands carry task metadata and artifact refs only; PDFs, OCR text, and large workpapers stay on disk.",
            "artifacts": self.artifacts,
        }
        self._write_manifest()

    def path_for(self, folder_key: str, filename: str) -> Path:
        return self.dirs[folder_key] / filename

    def summary(self) -> dict[str, Any]:
        return {
            "root": str(self.root),
            "artifact_manifest_path": str(self.manifest_path),
            "commands_dir": str(self.dirs["commands"]),
            "agent_outputs_dir": str(self.dirs["agent_outputs"]),
            "workpapers_dir": str(self.dirs["workpapers"]),
            "artifact_count": len(self.artifacts),
            "team_stage_count": len(TAX_TEAM_STAGES),
            "team_stages": list(TAX_TEAM_STAGES),
            "transport_policy": self.manifest["transport_policy"],
        }

    def register_documents(self, documents: list[dict[str, Any]]) -> list[str]:
        records = []
        for index, document in enumerate(documents, start=1):
            doc_id = f"doc_{index:03d}"
            filename = str(document.get("filename") or f"{doc_id}.txt")
            stem = _safe_filename(Path(filename).stem or doc_id)
            original_path = str(document.get("path") or "")
            original_size = _safe_file_size(original_path)
            text = redact_tax_identifiers(str(document.get("text") or ""))
            metadata = {key: value for key, value in document.items() if key != "text"}
            metadata.update(
                {
                    "document_id": doc_id,
                    "original_path": original_path,
                    "original_size_bytes": original_size,
                    "redaction_status": "redacted",
                }
            )
            text_ref = self.write_text_artifact(
                f"document_text.{doc_id}",
                "documents",
                f"{doc_id}-{stem}.txt",
                text,
                kind="document_text",
                summary=_truncate_string(text, TEAM_ARTIFACT_SNIPPET_CHARS),
                metadata={
                    "document_id": doc_id,
                    "filename": filename,
                    "document_type": document.get("document_type"),
                    "extraction_method": document.get("extraction_method"),
                    "ocr_required": bool(document.get("ocr_required")),
                    "original_path": original_path,
                    "original_size_bytes": original_size,
                },
                redaction_status="redacted",
            )
            metadata["text_artifact_ref"] = text_ref
            metadata_ref = self.write_json_artifact(
                f"document_metadata.{doc_id}",
                "documents",
                f"{doc_id}-{stem}-metadata.json",
                metadata,
                kind="document_metadata",
                summary=f"{filename} metadata",
                metadata={
                    "document_id": doc_id,
                    "filename": filename,
                    "document_type": document.get("document_type"),
                },
                redaction_status="metadata_only",
            )
            records.append(
                {
                    "document_id": doc_id,
                    "filename": filename,
                    "document_type": document.get("document_type"),
                    "metadata_ref": metadata_ref,
                    "text_ref": text_ref,
                    "ocr_required": bool(document.get("ocr_required")),
                }
            )
        index_ref = self.write_json_artifact(
            "document_index",
            "documents",
            "document_index.json",
            {"document_summary": _document_summary(documents), "documents": records},
            kind="document_index",
            summary="Index of source tax documents and extracted text artifacts.",
            redaction_status="metadata_only",
        )
        self.document_refs = [index_ref, *[str(record["text_ref"]) for record in records]]
        return list(self.document_refs)

    def write_json_artifact(
        self,
        artifact_id: str,
        folder_key: str,
        filename: str,
        payload: Any,
        *,
        kind: str,
        summary: str = "",
        metadata: dict[str, Any] | None = None,
        redaction_status: str = "redacted",
    ) -> str:
        path = self.path_for(folder_key, filename)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
        self._register_artifact(
            artifact_id,
            path,
            kind=kind,
            summary=summary,
            metadata=metadata,
            redaction_status=redaction_status,
        )
        return artifact_id

    def write_text_artifact(
        self,
        artifact_id: str,
        folder_key: str,
        filename: str,
        payload: str,
        *,
        kind: str,
        summary: str = "",
        metadata: dict[str, Any] | None = None,
        redaction_status: str = "redacted",
    ) -> str:
        path = self.path_for(folder_key, filename)
        path.write_text(payload, encoding="utf-8")
        self._register_artifact(
            artifact_id,
            path,
            kind=kind,
            summary=summary,
            metadata=metadata,
            redaction_status=redaction_status,
        )
        return artifact_id

    def read_json_artifact(self, artifact_id: str) -> Any:
        entry = self.artifacts[artifact_id]
        return json.loads(Path(str(entry["path"])).read_text(encoding="utf-8"))

    def write_command(
        self,
        *,
        stage: str,
        role: str,
        responsibilities: list[str],
        input_artifact_refs: list[str],
        output_paths: dict[str, str],
    ) -> str:
        command = {
            "task_id": f"{self.run_id}-{stage}",
            "agent_id": stage,
            "role": role,
            "instructions": list(responsibilities),
            "input_artifact_refs": list(input_artifact_refs),
            "output_paths": dict(output_paths),
            "status": "running",
            "created_at": utc_now_iso(),
            "blob_transport": "filesystem_refs_only",
        }
        return self.write_json_artifact(
            f"command.{stage}",
            "commands",
            f"{_safe_filename(stage)}.json",
            command,
            kind="agent_command",
            summary=f"Command envelope for {stage}.",
            redaction_status="metadata_only",
        )

    def finish_command(
        self,
        *,
        stage: str,
        output_artifact_refs: list[str],
        status: str = "completed",
        error: str | None = None,
        llm: Any | None = None,
    ) -> None:
        command_ref = f"command.{stage}"
        command = self.read_json_artifact(command_ref)
        command.update(
            {
                "status": status,
                "completed_at": utc_now_iso(),
                "output_artifact_refs": list(output_artifact_refs),
                "llm_provider": getattr(llm, "provider", "unknown") if llm is not None else "none",
                "llm_model": getattr(llm, "model", "unknown") if llm is not None else "none",
            }
        )
        if error:
            command["error"] = error
        self.write_json_artifact(
            command_ref,
            "commands",
            f"{_safe_filename(stage)}.json",
            command,
            kind="agent_command",
            summary=f"Command envelope for {stage}.",
            redaction_status="metadata_only",
        )

    def _register_artifact(
        self,
        artifact_id: str,
        path: Path,
        *,
        kind: str,
        summary: str = "",
        metadata: dict[str, Any] | None = None,
        redaction_status: str = "redacted",
    ) -> None:
        stat = path.stat()
        entry = {
            "artifact_id": artifact_id,
            "kind": kind,
            "path": str(path),
            "relative_path": str(path.relative_to(self.root)),
            "size_bytes": stat.st_size,
            "sha256": _sha256_file(path),
            "updated_at": utc_now_iso(),
            "redaction_status": redaction_status,
            "summary": summary,
        }
        if metadata:
            entry.update(metadata)
        self.artifacts[artifact_id] = entry
        self._write_manifest()

    def _write_manifest(self) -> None:
        self.manifest["updated_at"] = utc_now_iso()
        self.manifest["artifacts"] = self.artifacts
        self.manifest_path.write_text(json.dumps(self.manifest, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def _create_tax_team_workspace(
    context: Any,
    config: dict[str, Any],
    runtime_inputs: dict[str, Any],
) -> TaxTeamWorkspace:
    run_id = str(getattr(context, "run_id", "") or (config.get("identity") or {}).get("run_id") or f"tax-{uuid.uuid4().hex[:8]}")
    run_dir = getattr(context, "run_dir", None)
    if run_dir:
        root = Path(run_dir) / "tax_team"
    else:
        output_folder = _output_folder_value(config, runtime_inputs)
        base = _expand_output_folder(output_folder, config) if output_folder else Path(tempfile.gettempdir())
        root = base / f"{_safe_filename(run_id)}-tax_team"
    return TaxTeamWorkspace(root, run_id)


def _emit_progress(
    context: Any,
    stage_id: str,
    *,
    status: str = "running",
    message: str | None = None,
    percent: int | None = None,
) -> None:
    label, default_percent, default_message = TAX_PROGRESS_BY_STAGE.get(
        stage_id,
        (stage_id.replace("_", " ").title(), 0, "Tax co-worker is running."),
    )
    progress_percent = max(0, min(100, int(default_percent if percent is None else percent)))
    step_index = TAX_PROGRESS_INDEX.get(stage_id, 0)
    is_run_complete = status == "completed" and stage_id == "completed"
    detail = message or default_message
    payload = {
        "schema": "otterdesk.batch_progress.v1",
        "blueprint_id": BLUEPRINT_ID,
        "stage_id": stage_id,
        "stage_label": label,
        "label": label,
        "status": status,
        "message": detail,
        "detail": detail,
        "progress_percent": progress_percent,
        "percent": progress_percent,
        "progress": progress_percent,
        "completed_steps": len(TAX_PROGRESS_STEPS) - 1 if is_run_complete else step_index,
        "total_steps": len(TAX_PROGRESS_STEPS) - 1,
        "estimated": True,
        "updated_at": utc_now_iso(),
    }
    context.event("progress", payload)


def _safe_file_size(path_value: str) -> int | None:
    if not path_value:
        return None
    try:
        path = Path(path_value)
        return path.stat().st_size if path.exists() else None
    except OSError:
        return None


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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
    _apply_runtime_llm_overrides(resolved_config, runtime_inputs)
    llm = llm_client or _resolve_llm_client(resolved_config)
    context = create_runtime_context(blueprint_id, resolved_config, runtime_inputs, input_source)
    started_at = utc_now_iso()
    context.start()
    progress_stage = "initializing"
    _emit_progress(context, progress_stage)
    try:
        progress_stage = "workspace"
        _emit_progress(context, progress_stage)
        tax_team = _create_tax_team_workspace(context, resolved_config, runtime_inputs)
        context.event("tax_team_workspace_ready", tax_team.summary())

        progress_stage = "document_intake"
        _emit_progress(context, progress_stage)
        documents = _load_documents(resolved_config, runtime_inputs)
        document_refs = tax_team.register_documents(documents)
        context.event("tax_document_intake_completed", _document_summary(documents))

        progress_stage = "client_intake_coordinator"
        _emit_progress(context, progress_stage)
        client_intake = _client_intake_coordinator(documents, resolved_config, runtime_inputs, llm, tax_team, document_refs)
        context.event("client_intake_coordinator_completed", client_intake)

        progress_stage = "document_understanding_agent"
        _emit_progress(context, progress_stage)
        document_dossier = _document_understanding_agent(
            documents,
            client_intake,
            resolved_config,
            llm,
            tax_team,
            _team_refs(document_refs, client_intake),
        )
        context.event("document_understanding_agent_completed", document_dossier)

        progress_stage = "source_field_extractor"
        _emit_progress(context, progress_stage)
        source_extraction = _source_field_extractor(
            documents,
            document_dossier,
            resolved_config,
            llm,
            tax_team,
            _team_refs(document_refs, document_dossier),
        )
        context.event("source_field_extractor_completed", source_extraction)

        progress_stage = "income_preparer"
        _emit_progress(context, progress_stage)
        income_workpaper = _income_preparer(
            source_extraction,
            document_dossier,
            client_intake,
            resolved_config,
            llm,
            tax_team,
            _team_refs(source_extraction, document_dossier, client_intake),
        )
        context.event("income_preparer_completed", income_workpaper)

        progress_stage = "deductions_credits_preparer"
        _emit_progress(context, progress_stage)
        deductions_workpaper = _deductions_credits_preparer(
            source_extraction,
            client_intake,
            resolved_config,
            runtime_inputs,
            llm,
            tax_team,
            _team_refs(source_extraction, client_intake),
        )
        context.event("deductions_credits_preparer_completed", deductions_workpaper)

        progress_stage = "form_1040_assembler"
        _emit_progress(context, progress_stage)
        form_1040 = _form_1040_assembler(
            source_extraction,
            income_workpaper,
            deductions_workpaper,
            client_intake,
            resolved_config,
            llm,
            tax_team,
            _team_refs(source_extraction, income_workpaper, deductions_workpaper, client_intake),
        )
        context.event("form_1040_assembler_completed", form_1040)

        progress_stage = "tax_auditor"
        _emit_progress(context, progress_stage)
        audit_review = _tax_auditor(
            documents,
            source_extraction,
            form_1040,
            resolved_config,
            runtime_inputs,
            llm,
            tax_team,
            _team_refs(document_refs, source_extraction, form_1040),
        )
        context.event("tax_auditor_completed", audit_review)

        progress_stage = "manager_reviewer"
        _emit_progress(context, progress_stage)
        manager_review = _manager_reviewer(
            form_1040,
            audit_review,
            client_intake,
            resolved_config,
            llm,
            tax_team,
            _team_refs(form_1040, audit_review, client_intake),
        )
        context.event("manager_reviewer_completed", manager_review)

        progress_stage = "advisor_report_writer"
        _emit_progress(context, progress_stage)
        advisor_report = _advisor_report_writer(
            client_intake,
            document_dossier,
            form_1040,
            audit_review,
            manager_review,
            resolved_config,
            llm,
            tax_team,
            _team_refs(client_intake, document_dossier, form_1040, audit_review, manager_review),
        )
        context.event("advisor_report_writer_completed", advisor_report)

        llm_metadata = _llm_metadata(llm, resolved_config)
        progress_stage = "form_1040_packet_writer"
        _emit_progress(context, progress_stage)
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
            tax_team,
            _team_refs(
                document_refs,
                client_intake,
                document_dossier,
                source_extraction,
                income_workpaper,
                deductions_workpaper,
                form_1040,
                audit_review,
                manager_review,
                advisor_report,
            ),
        )
        progress_summary = {
            "schema": "otterdesk.batch_progress.v1",
            "blueprint_id": BLUEPRINT_ID,
            "stage_id": "completed",
            "stage_label": "Completed",
            "label": "Completed",
            "progress_percent": 100,
            "percent": 100,
            "status": "completed",
            "message": "Tax review packet is ready for inspection.",
            "detail": "Tax review packet is ready for inspection.",
            "estimated": True,
        }
        final_artifact["progress"] = progress_summary
        progress_stage = "output_materialization"
        _emit_progress(context, progress_stage)
        output_files = _write_output_folder_artifacts(final_artifact, resolved_config, runtime_inputs)
        if output_files:
            final_artifact["output_files"] = output_files
        final_artifact_ref = tax_team.write_json_artifact(
            "final_artifact.packet",
            "final",
            "final_artifact.json",
            final_artifact,
            kind="final_artifact_json",
            summary="Final prepared Form 1040 review packet.",
            redaction_status="redacted",
        )
        final_artifact["team_workspace"] = tax_team.summary()
        final_artifact["team_workspace"]["final_artifact_ref"] = final_artifact_ref
        tax_team.write_json_artifact(
            "final_artifact.packet",
            "final",
            "final_artifact.json",
            final_artifact,
            kind="final_artifact_json",
            summary="Final prepared Form 1040 review packet.",
            redaction_status="redacted",
        )
        _refresh_output_final_artifact_json(final_artifact)
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

        result_progress = dict(progress_summary)
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
            "team_workspace": tax_team.summary(),
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
            "progress": result_progress,
        }
        transport_result = _compact_result_for_transport(result)
        _emit_progress(context, "completed", status="completed")
        context.finish(transport_result)
        return transport_result
    except Exception as error:
        _emit_progress(
            context,
            progress_stage,
            status="failed",
            message=f"Tax co-worker failed during {progress_stage.replace('_', ' ')}: {error}",
        )
        context.fail(error)
        raise


def _resolve_llm_client(config: dict[str, Any]) -> Any:
    llm_config = config.get("llm") if isinstance(config.get("llm"), dict) else {}
    if llm_config.get("enabled") is False:
        return get_llm_client("fake")
    mode = str(llm_config.get("mode") or os.environ.get("MN_BLUEPRINT_LLM_MODE") or "ollama").strip().lower()
    if (
        os.environ.get("MN_BLUEPRINT_QUICK_TEST", "").strip().lower() in {"1", "true", "yes", "on"}
        and bool(llm_config.get("quick_test_uses_fake", False))
    ):
        return get_llm_client("fake")
    if mode in {"fake", "mock", "deterministic"}:
        return get_llm_client("fake")
    if mode in {"ollama", "live", "real"}:
        _apply_llm_config_env(llm_config)
        client = get_llm_client("ollama")
        if hasattr(client, "prefer_shared_skill"):
            client.prefer_shared_skill = bool(llm_config.get("prefer_shared_skill", False))
        if hasattr(client, "strict"):
            client.strict = bool(llm_config.get("strict_json", True))
        return client
    return get_llm_client(mode or None)


def _apply_runtime_llm_overrides(config: dict[str, Any], runtime_inputs: dict[str, Any]) -> None:
    api_base = runtime_inputs.get("ollama_base_url") or runtime_inputs.get("llm_api_base")
    model = runtime_inputs.get("ollama_model") or runtime_inputs.get("llm_model")
    if not api_base and not model:
        return
    llm_config = config.setdefault("llm", {})
    primary = llm_config.setdefault("configs", {}).setdefault(str(llm_config.get("default_config") or "primary"), {})
    if api_base:
        llm_config["api_base"] = str(api_base).rstrip("/")
        primary["api_base"] = str(api_base).rstrip("/")
    if model:
        normalized_model = _normalize_ollama_model(str(model))
        llm_config["model"] = normalized_model
        primary["model"] = normalized_model


def _apply_llm_config_env(llm_config: dict[str, Any]) -> None:
    primary = {}
    configs = llm_config.get("configs") if isinstance(llm_config.get("configs"), dict) else {}
    default_config = str(llm_config.get("default_config") or "primary")
    if isinstance(configs.get(default_config), dict):
        primary = configs[default_config]
    values = {
        "MN_LLM_API_BASE": llm_config.get("api_base") or primary.get("api_base"),
        "MN_LLM_MODEL": llm_config.get("model") or primary.get("model"),
        "MN_LLM_TIMEOUT_SECONDS": llm_config.get("timeout_seconds") or primary.get("timeout_seconds"),
        "MN_LLM_MAX_TOKENS": llm_config.get("max_tokens") or primary.get("max_tokens"),
        "MN_LLM_NUM_RETRIES": llm_config.get("num_retries") or primary.get("num_retries"),
    }
    for env_name, value in values.items():
        if value not in (None, ""):
            os.environ[env_name] = str(value)


def _normalize_ollama_model(model: str) -> str:
    value = model.strip()
    if not value:
        return "ollama/nemotron3:33b"
    return value if value.startswith("ollama/") else f"ollama/{value}"


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
        "team_stage_count": len(TAX_TEAM_STAGES),
        "team_stages": list(TAX_TEAM_STAGES),
    }


def _call_tax_specialist(
    llm: Any,
    *,
    stage: str,
    role: str,
    responsibilities: list[str],
    payload: dict[str, Any],
    fallback: dict[str, Any],
    team: TaxTeamWorkspace | None = None,
    input_refs: list[str] | None = None,
) -> dict[str, Any]:
    if team is not None:
        return run_tax_agent(
            team,
            llm,
            stage=stage,
            role=role,
            responsibilities=responsibilities,
            payload=payload,
            fallback=fallback,
            input_refs=input_refs or [],
        )
    return _generate_tax_specialist_result(
        llm,
        stage=stage,
        role=role,
        responsibilities=responsibilities,
        payload=payload,
        fallback=fallback,
    )


def run_tax_agent(
    team: TaxTeamWorkspace,
    llm: Any,
    *,
    stage: str,
    role: str,
    responsibilities: list[str],
    payload: dict[str, Any],
    fallback: dict[str, Any],
    input_refs: list[str],
) -> dict[str, Any]:
    safe_stage = _safe_filename(stage)
    payload_ref = team.write_json_artifact(
        f"agent_input.{stage}",
        "workpapers",
        f"{safe_stage}-input.json",
        _compact_json_value(payload, string_limit=8000, list_limit=180, dict_key_limit=180),
        kind="agent_input",
        summary=f"Bounded input payload for {stage}.",
        redaction_status="redacted",
    )
    fallback_ref = team.write_json_artifact(
        f"agent_fallback.{stage}",
        "workpapers",
        f"{safe_stage}-fallback.json",
        _compact_json_value(fallback, string_limit=8000, list_limit=180, dict_key_limit=180),
        kind="agent_fallback",
        summary=f"Deterministic fallback schema for {stage}.",
        redaction_status="redacted",
    )
    all_input_refs = _dedupe_strings([*input_refs, payload_ref, fallback_ref])
    output_ref = f"agent_output.{stage}"
    workpaper_ref = f"agent_workpaper.{stage}"
    command_ref = team.write_command(
        stage=stage,
        role=role,
        responsibilities=responsibilities,
        input_artifact_refs=all_input_refs,
        output_paths={
            "agent_output": str(team.path_for("agent_outputs", f"{safe_stage}.json")),
            "workpaper": str(team.path_for("workpapers", f"{safe_stage}-workpaper.json")),
        },
    )
    try:
        payload_for_prompt = team.read_json_artifact(payload_ref)
        fallback_for_prompt = team.read_json_artifact(fallback_ref)
        result = _generate_tax_specialist_result(
            llm,
            stage=stage,
            role=role,
            responsibilities=responsibilities,
            payload=payload_for_prompt,
            fallback=fallback_for_prompt,
        )
        result["team_artifacts"] = {
            "command": command_ref,
            "input": payload_ref,
            "fallback": fallback_ref,
            "input_refs": all_input_refs,
            "output": output_ref,
            "workpaper": workpaper_ref,
        }
        team.write_json_artifact(
            output_ref,
            "agent_outputs",
            f"{safe_stage}.json",
            result,
            kind="agent_output",
            summary=f"Structured output from {stage}.",
            redaction_status="redacted",
        )
        team.write_json_artifact(
            workpaper_ref,
            "workpapers",
            f"{safe_stage}-workpaper.json",
            {
                "stage": stage,
                "role": role,
                "responsibilities": responsibilities,
                "input_artifact_refs": all_input_refs,
                "output_artifact_ref": output_ref,
                "result": result,
            },
            kind="agent_workpaper",
            summary=f"Reviewable workpaper for {stage}.",
            redaction_status="redacted",
        )
        team.finish_command(stage=stage, output_artifact_refs=[output_ref, workpaper_ref], llm=llm)
        return result
    except Exception as error:
        team.finish_command(stage=stage, output_artifact_refs=[], status="failed", error=str(error), llm=llm)
        raise


def _generate_tax_specialist_result(
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


def _team_refs(*values: Any) -> list[str]:
    refs: list[str] = []
    for value in values:
        if isinstance(value, str):
            refs.append(value)
        elif isinstance(value, list):
            refs.extend(_team_refs(*value))
        elif isinstance(value, dict):
            artifacts = value.get("team_artifacts")
            if isinstance(artifacts, dict):
                for key in ("output", "workpaper", "input", "fallback", "command"):
                    artifact_ref = artifacts.get(key)
                    if isinstance(artifact_ref, str):
                        refs.append(artifact_ref)
    return _dedupe_strings(refs)


def _dedupe_strings(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


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
        "risk_register": _compact_json_value(final_artifact.get("risk_register", []), string_limit=1400, list_limit=20, dict_key_limit=30),
        "advisor_recommendations": _compact_json_value(final_artifact.get("advisor_recommendations", []), string_limit=1400, list_limit=20, dict_key_limit=30),
        "filing_readiness": _compact_json_value(final_artifact.get("filing_readiness", {}), string_limit=1200, list_limit=20, dict_key_limit=30),
        "open_questions": _compact_json_value(final_artifact.get("open_questions", []), string_limit=1200, list_limit=20, dict_key_limit=20),
        "source_evidence_index": _compact_json_value(final_artifact.get("source_evidence_index", []), string_limit=1400, list_limit=20, dict_key_limit=30),
        "strategic_review": _compact_json_value(final_artifact.get("strategic_review", {}), string_limit=1800, list_limit=30, dict_key_limit=40),
        "team_workspace": _compact_json_value(final_artifact.get("team_workspace", {}), string_limit=1000, list_limit=20, dict_key_limit=30),
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
    team: TaxTeamWorkspace | None = None,
    input_refs: list[str] | None = None,
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
        team=team,
        input_refs=input_refs,
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
    team: TaxTeamWorkspace | None = None,
    input_refs: list[str] | None = None,
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
        team=team,
        input_refs=input_refs,
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
    team: TaxTeamWorkspace | None = None,
    input_refs: list[str] | None = None,
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
        team=team,
        input_refs=input_refs,
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
    team: TaxTeamWorkspace | None = None,
    input_refs: list[str] | None = None,
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
        team=team,
        input_refs=input_refs,
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
    team: TaxTeamWorkspace | None = None,
    input_refs: list[str] | None = None,
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
        team=team,
        input_refs=input_refs,
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
    team: TaxTeamWorkspace | None = None,
    input_refs: list[str] | None = None,
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
        team=team,
        input_refs=input_refs,
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
    team: TaxTeamWorkspace | None = None,
    input_refs: list[str] | None = None,
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
        team=team,
        input_refs=input_refs,
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
    team: TaxTeamWorkspace | None = None,
    input_refs: list[str] | None = None,
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
        team=team,
        input_refs=input_refs,
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
    team: TaxTeamWorkspace | None = None,
    input_refs: list[str] | None = None,
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
        team=team,
        input_refs=input_refs,
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
    team: TaxTeamWorkspace | None = None,
    input_refs: list[str] | None = None,
) -> dict[str, Any]:
    tax_year = intake["tax_year"]
    advisor_message = str(advisor_report.get("advisor_message") or _advisor_message_from_form(intake, form_1040, audit_review))
    risk_register = _build_risk_register(documents, intake, source_extraction, form_1040, audit_review, manager_review)
    advisor_recommendations = _build_advisor_recommendations(advisor_report, risk_register, form_1040)
    filing_readiness = _build_filing_readiness(audit_review, manager_review, risk_register)
    open_questions = _build_open_questions(intake, form_1040, manager_review)
    source_evidence_index = _build_source_evidence_index(form_1040, source_extraction, team)
    strategic_review = _build_strategic_review(
        documents,
        intake,
        document_dossier,
        source_extraction,
        income_workpaper,
        deductions_workpaper,
        form_1040,
        audit_review,
        manager_review,
        advisor_report,
        risk_register,
        advisor_recommendations,
        filing_readiness,
        source_evidence_index,
        config,
        runtime_inputs,
    )
    artifact = {
        "type": "prepared_1040_tax_packet",
        "title": f"Personal Income Tax Preparation & Strategic Review | Tax Year {tax_year}",
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
        "risk_register": risk_register,
        "advisor_recommendations": advisor_recommendations,
        "filing_readiness": filing_readiness,
        "open_questions": open_questions,
        "source_evidence_index": source_evidence_index,
        "strategic_review": strategic_review,
        "expert_team": {
            "model": llm_metadata.get("model"),
            "provider": llm_metadata.get("provider"),
            "stages": list(TAX_TEAM_STAGES),
            "handoff_mode": "filesystem_artifact_refs",
        },
        "llm": llm_metadata,
        "knowledge_sources": list((config.get("knowledge") or {}).get("irs_sources") or []),
    }
    if team is not None:
        artifact["team_workspace"] = team.summary()
        artifact = _record_packet_writer_agent(team, artifact, input_refs or [])
    return artifact


def _record_packet_writer_agent(
    team: TaxTeamWorkspace,
    final_artifact: dict[str, Any],
    input_refs: list[str],
) -> dict[str, Any]:
    stage = "form_1040_packet_writer"
    safe_stage = _safe_filename(stage)
    output_ref = f"agent_output.{stage}"
    workpaper_ref = f"agent_workpaper.{stage}"
    command_ref = team.write_command(
        stage=stage,
        role="Form 1040 Packet Writer",
        responsibilities=[
            "assemble the final review packet",
            "preserve artifact references",
            "keep large workpapers in the run-store workspace",
        ],
        input_artifact_refs=_dedupe_strings(input_refs),
        output_paths={
            "agent_output": str(team.path_for("agent_outputs", f"{safe_stage}.json")),
            "workpaper": str(team.path_for("workpapers", f"{safe_stage}-workpaper.json")),
        },
    )
    final_artifact["team_artifacts"] = {
        "command": command_ref,
        "input_refs": _dedupe_strings(input_refs),
        "output": output_ref,
        "workpaper": workpaper_ref,
    }
    team.write_json_artifact(
        output_ref,
        "agent_outputs",
        f"{safe_stage}.json",
        final_artifact,
        kind="agent_output",
        summary="Packet writer final artifact output.",
        redaction_status="redacted",
    )
    team.write_json_artifact(
        workpaper_ref,
        "workpapers",
        f"{safe_stage}-workpaper.json",
        {
            "stage": stage,
            "input_artifact_refs": _dedupe_strings(input_refs),
            "final_artifact_ref": output_ref,
            "filing_readiness": final_artifact.get("filing_readiness"),
            "risk_count": len(final_artifact.get("risk_register") or []),
            "output_files": final_artifact.get("output_files", []),
        },
        kind="agent_workpaper",
        summary="Packet writer workpaper and final packet metadata.",
        redaction_status="redacted",
    )
    team.finish_command(stage=stage, output_artifact_refs=[output_ref, workpaper_ref], llm=None)
    return final_artifact


def _build_risk_register(
    documents: list[dict[str, Any]],
    intake: dict[str, Any],
    source_extraction: dict[str, Any],
    form_1040: dict[str, Any],
    audit_review: dict[str, Any],
    manager_review: dict[str, Any],
) -> list[dict[str, Any]]:
    risks: list[dict[str, Any]] = []
    if not documents:
        risks.append(
            _risk_item(
                "high",
                "missing_documents",
                "No real local tax document folder was processed.",
                ["document_index"],
                "Point the worker at the complete source document folder before relying on the draft.",
                "client_intake_coordinator",
                True,
            )
        )
    ocr_docs = [str(document.get("filename")) for document in documents if document.get("ocr_required")]
    if ocr_docs:
        risks.append(
            _risk_item(
                "medium",
                "ocr_quality",
                f"{len(ocr_docs)} document(s) require OCR review.",
                ocr_docs,
                "Compare every OCR-derived amount against the original PDF before filing.",
                "document_understanding_agent",
                True,
            )
        )
    evidence = source_extraction.get("evidence") if isinstance(source_extraction.get("evidence"), list) else []
    if not evidence:
        risks.append(
            _risk_item(
                "high",
                "source_support",
                "No source evidence was extracted for the draft line map.",
                [],
                "Treat this as a demo packet until source-backed evidence exists.",
                "source_field_extractor",
                True,
            )
        )
    for flag in _as_list(form_1040.get("schedule_review_flags"), []):
        risks.append(
            _risk_item(
                "medium",
                "schedule_review",
                str(flag),
                _team_refs(form_1040),
                "Resolve the schedule-specific review item with the taxpayer or a qualified preparer.",
                "income_preparer",
                True,
            )
        )
    for warning in _as_list(audit_review.get("warnings"), []):
        risks.append(
            _risk_item(
                "medium",
                "audit_warning",
                str(warning),
                _team_refs(audit_review),
                "Clear the auditor warning before moving the numbers into tax software.",
                "tax_auditor",
                True,
            )
        )
    for blocker in _as_list(manager_review.get("blockers"), []):
        risks.append(
            _risk_item(
                "high",
                "manager_blocker",
                str(blocker),
                _team_refs(manager_review),
                "Do not file until this manager blocker is resolved.",
                "manager_reviewer",
                True,
            )
        )
    if not risks:
        risks.append(
            _risk_item(
                "low",
                "human_review_required",
                "No blocking automated risk was detected, but this remains a draft review packet.",
                _team_refs(form_1040, audit_review, manager_review),
                "Review the draft with the taxpayer or a qualified preparer before filing.",
                "manager_reviewer",
                True,
            )
        )
    return _dedupe_risks(risks)


def _risk_item(
    severity: str,
    category: str,
    finding: str,
    evidence_refs: list[str],
    advice: str,
    owner: str,
    blocker: bool,
) -> dict[str, Any]:
    return {
        "severity": severity,
        "category": category,
        "finding": finding,
        "evidence_refs": _dedupe_strings([str(item) for item in evidence_refs if item]),
        "advice": advice,
        "owner": owner,
        "blocker": blocker,
    }


def _dedupe_risks(risks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    result = []
    for risk in risks:
        key = (risk.get("severity"), risk.get("category"), risk.get("finding"))
        if key in seen:
            continue
        seen.add(key)
        result.append(risk)
    return result


def _build_advisor_recommendations(
    advisor_report: dict[str, Any],
    risk_register: list[dict[str, Any]],
    form_1040: dict[str, Any],
) -> list[dict[str, Any]]:
    recommendations = []
    for index, risk in enumerate([item for item in risk_register if item.get("blocker")], start=1):
        recommendations.append(
            {
                "priority": index,
                "action": risk.get("advice"),
                "reason": risk.get("finding"),
                "owner": risk.get("owner"),
                "risk_category": risk.get("category"),
            }
        )
    for step in _as_list(advisor_report.get("next_steps"), []):
        if not any(item.get("action") == step for item in recommendations):
            recommendations.append(
                {
                    "priority": len(recommendations) + 1,
                    "action": str(step),
                    "reason": "Advisor next step",
                    "owner": "advisor_report_writer",
                    "risk_category": "next_step",
                }
            )
    for question in _as_list(form_1040.get("questions_for_user"), []):
        recommendations.append(
            {
                "priority": len(recommendations) + 1,
                "action": f"Answer: {question}",
                "reason": "Open taxpayer question",
                "owner": "client_intake_coordinator",
                "risk_category": "open_question",
            }
        )
    return recommendations


def _build_filing_readiness(
    audit_review: dict[str, Any],
    manager_review: dict[str, Any],
    risk_register: list[dict[str, Any]],
) -> dict[str, Any]:
    blockers = sorted(
        set(
            str(item)
            for item in [
                *[risk.get("finding") for risk in risk_register if risk.get("blocker")],
                *_as_list(manager_review.get("blockers"), []),
            ]
            if item
        )
    )
    return {
        "status": "not_ready_for_filing",
        "review_required": True,
        "manager_signoff": manager_review.get("manager_signoff", "not_approved_for_filing"),
        "blockers": blockers,
        "confidence": min(float(manager_review.get("quality_score", 0.6) or 0.6), 0.85),
        "do_not_file_until": _as_list(audit_review.get("do_not_file_until"), [])
        or [
            "Identity, filing status, address, dependents, and signatures are confirmed.",
            "All source PDFs have been checked against the draft line map.",
            "A qualified preparer or the taxpayer reviews the final return.",
        ],
    }


def _build_open_questions(
    intake: dict[str, Any],
    form_1040: dict[str, Any],
    manager_review: dict[str, Any],
) -> list[str]:
    questions = []
    questions.extend(str(item) for item in _as_list(form_1040.get("questions_for_user"), []))
    questions.extend(f"Confirm missing or unconfirmed item: {item}" for item in _as_list(intake.get("missing_or_unconfirmed"), []))
    for blocker in _as_list(manager_review.get("blockers"), []):
        if "question" in str(blocker).lower() or "confirm" in str(blocker).lower():
            questions.append(str(blocker))
    return sorted(set(item for item in questions if item))


def _build_source_evidence_index(
    form_1040: dict[str, Any],
    source_extraction: dict[str, Any],
    team: TaxTeamWorkspace | None,
) -> list[dict[str, Any]]:
    line_map = form_1040.get("line_map") if isinstance(form_1040.get("line_map"), dict) else {}
    fields = source_extraction.get("source_fields") if isinstance(source_extraction.get("source_fields"), list) else []
    document_refs_by_filename = _document_refs_by_filename(team)
    index = []
    for line, draft_value in line_map.items():
        sources = []
        for field in fields:
            target = str(field.get("target_line") or "")
            if _line_key_matches_target(line, target):
                filename = str(field.get("filename") or "")
                sources.append(
                    {
                        "field": field.get("field"),
                        "amount": field.get("amount"),
                        "filename": filename,
                        "document_type": field.get("document_type"),
                        "confidence": field.get("confidence"),
                        "artifact_ref": document_refs_by_filename.get(filename),
                    }
                )
        index.append(
            {
                "line": line,
                "draft_value": draft_value,
                "sources": sources,
                "support_status": "source_supported" if sources else "review_required",
            }
        )
    return index


def _document_refs_by_filename(team: TaxTeamWorkspace | None) -> dict[str, str]:
    if team is None:
        return {}
    refs = {}
    try:
        index = team.read_json_artifact("document_index")
    except Exception:
        return refs
    for document in index.get("documents", []):
        filename = str(document.get("filename") or "")
        text_ref = str(document.get("text_ref") or "")
        if filename and text_ref:
            refs[filename] = text_ref
    return refs


def _line_key_matches_target(line_key: str, target_line: str) -> bool:
    line_number = line_key.split("_", 1)[0].lower()
    lowered_target = target_line.lower()
    if line_number and line_number in lowered_target:
        return True
    lowered_line = line_key.lower()
    return "withheld" in lowered_line and "withholding" in lowered_target


def _build_strategic_review(
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
    risk_register: list[dict[str, Any]],
    advisor_recommendations: list[dict[str, Any]],
    filing_readiness: dict[str, Any],
    source_evidence_index: list[dict[str, Any]],
    config: dict[str, Any],
    runtime_inputs: dict[str, Any],
) -> dict[str, Any]:
    tax_year = _safe_int(intake.get("tax_year"), 2025)
    return {
        "title": "Personal Income Tax Preparation & Strategic Review",
        "tax_year": tax_year,
        "executive_engagement_summary": _build_executive_engagement_summary(
            documents,
            intake,
            source_extraction,
            form_1040,
            risk_register,
            runtime_inputs,
        ),
        "intake_tracker": _build_intake_tracker(documents, intake, document_dossier, source_extraction),
        "income_reconstruction": _build_income_reconstruction(
            intake,
            document_dossier,
            source_extraction,
            income_workpaper,
            form_1040,
        ),
        "deductions_credits_optimization": _build_deductions_credits_optimization(
            source_extraction,
            deductions_workpaper,
            form_1040,
            config,
        ),
        "executive_financial_leaf": _build_executive_financial_leaf(form_1040, source_extraction, filing_readiness),
        "forward_planning": _build_forward_planning(tax_year, form_1040, source_extraction),
        "premium_compliance_risk_assessment": _build_premium_compliance_risk_assessment(
            risk_register,
            source_extraction,
            document_dossier,
            source_evidence_index,
        ),
        "execution_authorization_timeline": _build_execution_authorization_timeline(),
        "strategic_post_mortem_advisory": _build_strategic_post_mortem_advisory(
            advisor_report,
            advisor_recommendations,
            source_extraction,
            document_dossier,
            manager_review,
        ),
    }


def _build_executive_engagement_summary(
    documents: list[dict[str, Any]],
    intake: dict[str, Any],
    source_extraction: dict[str, Any],
    form_1040: dict[str, Any],
    risk_register: list[dict[str, Any]],
    runtime_inputs: dict[str, Any],
) -> dict[str, Any]:
    line_map = form_1040.get("line_map") if isinstance(form_1040.get("line_map"), dict) else {}
    doc_types = sorted({str(document.get("document_type") or "unknown_tax_document") for document in documents})
    review_categories = sorted({str(risk.get("category")) for risk in risk_register if isinstance(risk, dict) and risk.get("category")})
    profile = runtime_inputs.get("taxpayer_profile") if isinstance(runtime_inputs.get("taxpayer_profile"), dict) else {}
    overview_parts = [
        f"Draft federal Form 1040 review for tax year {intake.get('tax_year', 2025)}",
        f"filing status treated as {str(intake.get('filing_status') or 'single').replace('_', ' ')} pending taxpayer confirmation",
        f"AGI currently maps to {line_map.get('11_adjusted_gross_income', '$0.00')}",
        f"taxable income currently maps to {line_map.get('15_taxable_income', '$0.00')}",
    ]
    if doc_types:
        overview_parts.append(f"source set includes {', '.join(doc_types)}")
    if review_categories:
        overview_parts.append(f"active risk workstreams: {', '.join(review_categories)}")
    return {
        "taxpayer_names": profile.get("taxpayer_names") or "Unconfirmed - populate during intake",
        "filing_status": intake.get("filing_status", "single"),
        "primary_cpa_or_advisor": profile.get("primary_advisor") or "Unassigned",
        "client_data_input_method": _client_data_input_method(documents),
        "executive_tax_regime_overview": ". ".join(overview_parts) + ".",
        "engagement_posture": "Strategic preparation review; not an official return, e-file authorization, or legal tax opinion.",
    }


def _client_data_input_method(documents: list[dict[str, Any]]) -> str:
    methods = {str(document.get("extraction_method") or "").lower() for document in documents}
    if not documents:
        return "Demo sample records - client source folder still required"
    if any("ocr" in method or "pdf" in method for method in methods):
        return "Dynamic/flexible receipts and PDF summaries"
    if methods == {"fallback"}:
        return "Flexible local folder text/PDF scan"
    return "Hybrid source documents and extracted summaries"


def _build_intake_tracker(
    documents: list[dict[str, Any]],
    intake: dict[str, Any],
    document_dossier: dict[str, Any],
    source_extraction: dict[str, Any],
) -> list[dict[str, Any]]:
    doc_types = {str(document.get("document_type") or "unknown_tax_document") for document in documents}
    complex_forms = set(str(item) for item in _as_list(document_dossier.get("complex_or_partially_supported_forms"), []))
    totals = source_extraction.get("numeric_totals") if isinstance(source_extraction.get("numeric_totals"), dict) else {}
    return [
        _tracker_row(
            "Identity & Dependents",
            "Taxpayer profile / organizer",
            "partial" if intake.get("missing_or_unconfirmed") else "complete",
            "Confirm legal names, SSNs, address, dependents, custody agreements, and care providers.",
            "Verify age, residency, relationship, support tests, and 2025 dependent thresholds.",
        ),
        _tracker_row(
            "Earned & Retirement Income",
            _source_format_for(doc_types, {"W-2", "1099-R", "SSA-1099"}),
            "complete" if doc_types & {"W-2", "1099-R", "SSA-1099"} else "missing",
            "Disclose short-term employment, retirement rollovers, Roth activity, and withholding forms.",
            "Reconcile wages, pre-tax deferrals, retirement codes, withholding, and rollover exceptions.",
        ),
        _tracker_row(
            "Liquid Investment Portfolios",
            _source_format_for(doc_types, {"1099-B", "1099-DIV", "1099-INT", "brokerage_statement"}),
            "review" if doc_types & {"1099-B", "1099-DIV", "brokerage_statement"} else ("complete" if "1099-INT" in doc_types else "missing"),
            "Provide final brokerage statements and confirm year-end corrected 1099s.",
            "Identify wash sales, qualified dividend splits, basis gaps, and Schedule D/Form 8949 needs.",
        ),
        _tracker_row(
            "Digital Assets & Web3",
            "API sync / CSV ledger / wallet history requested",
            "missing",
            "Provide exchange CSVs, wallet addresses, staking rewards, NFTs, and off-chain cost-basis history.",
            "Map token-to-token trades, gas fees, staking income, and missing basis before return preparation.",
        ),
        _tracker_row(
            "Business / Self-Employment",
            _source_format_for(doc_types, {"1099-NEC", "1099-K"}),
            "review" if doc_types & {"1099-NEC", "1099-K"} or float(totals.get("nonemployee_compensation", 0.0) or 0.0) else "missing",
            "Affirm business-purpose expenses, separate bank activity, mileage logs, and home office support.",
            "Cross-reference gross receipts, 1099-K/NEC reporting, Schedule C expenses, and self-employment tax.",
        ),
        _tracker_row(
            "Pass-Through Entities",
            _source_format_for(doc_types, {"K-1", "1065 K-1", "1120S K-1", "1041 K-1"}),
            "review" if any("K-1" in item for item in doc_types | complex_forms) else "missing",
            "Flag late or amended K-1s immediately.",
            "Track basis, at-risk limits, passive activity loss limits, and state-source allocations.",
        ),
        _tracker_row(
            "Itemized Deductions & Credits",
            _source_format_for(doc_types, {"1098", "1095-A"}),
            "review" if doc_types & {"1098", "1095-A"} else "partial",
            "Provide SALT records, charitable acknowledgments, medical summaries, Form 1098, and 1095-A.",
            "Compare Schedule A vs standard deduction and reconcile Form 8962 where required.",
        ),
    ]


def _tracker_row(category: str, source_format: str, status: str, taxpayer_action: str, preparer_action: str) -> dict[str, str]:
    status_labels = {
        "complete": "Source-backed / ready for review",
        "partial": "Partial / taxpayer confirmation needed",
        "review": "Present / specialist review required",
        "missing": "Missing / request from taxpayer",
    }
    return {
        "category": category,
        "data_source_format_provided": source_format,
        "completeness_status": status_labels.get(status, status),
        "taxpayer_action": taxpayer_action,
        "preparer_action": preparer_action,
    }


def _source_format_for(doc_types: set[str], target_types: set[str]) -> str:
    matched = sorted(doc_types & target_types)
    if matched:
        return "Extracted local source documents: " + ", ".join(matched)
    return "Not yet provided"


def _build_income_reconstruction(
    intake: dict[str, Any],
    document_dossier: dict[str, Any],
    source_extraction: dict[str, Any],
    income_workpaper: dict[str, Any],
    form_1040: dict[str, Any],
) -> dict[str, Any]:
    totals = source_extraction.get("numeric_totals") if isinstance(source_extraction.get("numeric_totals"), dict) else {}
    line_map = form_1040.get("line_map") if isinstance(form_1040.get("line_map"), dict) else {}
    complex_forms = _as_list(document_dossier.get("complex_or_partially_supported_forms"), [])
    return {
        "cash_flow_architecture": [
            {
                "area": "Active income analysis",
                "finding": (
                    f"W-2 wage support currently maps to {line_map.get('1z_wages', '$0.00')}. "
                    "Confirm all gap employment, bonuses, RSU wage inclusion, and statutory deferrals before filing."
                ),
            },
            {
                "area": "Retirement and annuity flows",
                "finding": (
                    f"Taxable retirement distributions currently map to {line_map.get('4b_taxable_ira_pensions_annuities', '$0.00')}. "
                    "Review rollover treatment, distribution codes, early-distribution exceptions, and withholding."
                ),
            },
            {
                "area": "Investment and portfolio income",
                "finding": (
                    f"Interest/dividend/brokerage signals include taxable interest {_money(float(totals.get('taxable_interest', 0.0) or 0.0))}, "
                    f"ordinary dividends {_money(float(totals.get('ordinary_dividends', 0.0) or 0.0))}, and brokerage proceeds "
                    f"{_money(float(totals.get('brokerage_proceeds', 0.0) or 0.0))}. "
                    "Brokerage proceeds require basis and wash-sale review before capital gain treatment."
                ),
            },
            {
                "area": "Business / Schedule C dynamics",
                "finding": (
                    f"Nonemployee compensation signal: {_money(float(totals.get('nonemployee_compensation', 0.0) or 0.0))}. "
                    "If present, reconstruct gross receipts, ordinary and necessary expenses, mileage, home office, and SE tax."
                ),
            },
            {
                "area": "Passive, entity, and complex income",
                "finding": (
                    "Complex or partially supported forms flagged: "
                    + (", ".join(str(item) for item in complex_forms) if complex_forms else "none in current source set")
                    + ". Passive losses, K-1 basis, rental depreciation, and multi-state sourcing remain review gates when applicable."
                ),
            },
        ],
        "roles_and_responsibilities": {
            "taxpayer": [
                "Declare that all worldwide income streams, cash apps, bartering, foreign accounts, crypto, and business receipts have been disclosed.",
                "Provide final corrected forms, source ledgers, and explanations for unusual or one-time transactions.",
            ],
            "tax_professional": [
                "Classify income into the correct tax categories and preserve source evidence for every supported line.",
                "Identify lower-rate treatment opportunities such as qualified dividends, long-term capital gains, retirement rollover exclusions, and business deduction substantiation.",
            ],
        },
        "income_workpaper_flags": _as_list(income_workpaper.get("unsupported_or_review_required_income"), []),
    }


def _build_deductions_credits_optimization(
    source_extraction: dict[str, Any],
    deductions_workpaper: dict[str, Any],
    form_1040: dict[str, Any],
    config: dict[str, Any],
) -> dict[str, Any]:
    tax_knowledge = config.get("tax_knowledge") if isinstance(config.get("tax_knowledge"), dict) else {}
    standard_table = tax_knowledge.get("standard_deduction_2025") if isinstance(tax_knowledge.get("standard_deduction_2025"), dict) else STANDARD_DEDUCTION_2025
    totals = source_extraction.get("numeric_totals") if isinstance(source_extraction.get("numeric_totals"), dict) else {}
    return {
        "above_the_line_adjustments": [
            {
                "optimization_vector": "Traditional IRA contributions",
                "statutory_limit": "$7,000, plus $1,000 age-50 catch-up; confirm deductibility phase-out.",
                "client_data_provided": "Not confirmed in current source set.",
                "strategic_advisory": "Check earned compensation, workplace retirement coverage, spouse coverage, and backdoor Roth/Form 8606 facts.",
            },
            {
                "optimization_vector": "Health Savings Account (HSA)",
                "statutory_limit": "2025 IRS limit: self-only $4,300 / family $8,550, plus age-55 catch-up where eligible.",
                "client_data_provided": "Not confirmed in current source set.",
                "strategic_advisory": "Confirm HDHP eligibility, employer contributions, payroll vs direct contributions, and Form 8889 reporting.",
            },
            {
                "optimization_vector": "Self-employed retirement",
                "statutory_limit": "SEP-IRA / Solo 401(k) depends on net earnings and plan timing.",
                "client_data_provided": "Review required if Schedule C or 1099-NEC activity is present.",
                "strategic_advisory": "Compute net earnings ceiling before recommending SEP, Solo 401(k), or cash balance plan funding.",
            },
        ],
        "standard_deduction_baseline": {
            key: _money(float(value)) for key, value in standard_table.items()
        },
        "schedule_a_tracker": [
            {
                "item": "State & local taxes (SALT)",
                "gross_amount": "Unconfirmed",
                "proof_needed": "Collect state withholding, real estate tax, personal property tax, and evaluate SALT cap/PTET planning where applicable.",
            },
            {
                "item": "Qualifying mortgage interest",
                "gross_amount": _money(float(totals.get("mortgage_interest", 0.0) or 0.0)),
                "proof_needed": "Verify Form 1098, acquisition debt limits, refinances, points, and secured debt rules.",
            },
            {
                "item": "Charitable contributions",
                "gross_amount": "Unconfirmed",
                "proof_needed": "Secure written acknowledgments for gifts over $250 and evaluate appreciated stock versus cash limits.",
            },
            {
                "item": "Medical & dental expenses",
                "gross_amount": "Unconfirmed",
                "proof_needed": "Reconstruct deductible amounts above the 7.5% AGI floor and exclude reimbursed items.",
            },
            {
                "item": "Premium tax credit reconciliation",
                "gross_amount": _money(float(totals.get("advance_premium_tax_credit", 0.0) or 0.0)),
                "proof_needed": "If Form 1095-A is present, complete Form 8962 before filing.",
            },
        ],
        "draft_strategy": {
            "method": deductions_workpaper.get("deduction_method", "standard_deduction_pending_itemized_review"),
            "draft_deduction": form_1040.get("line_map", {}).get("12_standard_deduction", deductions_workpaper.get("standard_deduction", "$0.00")),
            "credits_review": _as_list(deductions_workpaper.get("credits_review"), []),
        },
    }


def _build_executive_financial_leaf(
    form_1040: dict[str, Any],
    source_extraction: dict[str, Any],
    filing_readiness: dict[str, Any],
) -> dict[str, Any]:
    line_map = form_1040.get("line_map") if isinstance(form_1040.get("line_map"), dict) else {}
    totals = source_extraction.get("numeric_totals") if isinstance(source_extraction.get("numeric_totals"), dict) else {}
    payments = float(totals.get("federal_withholding", 0.0) or 0.0)
    rows = [
        _leaf_row("A", "Gross domestic & worldwide income", line_map.get("11_adjusted_gross_income", "$0.00"), "AGI proxy from supported source lines; worldwide income confirmation still required."),
        _leaf_row("B", "Less: total above-the-line adjustments", "Unconfirmed", "IRA, HSA, self-employed retirement, educator, student loan, and other adjustments require taxpayer facts."),
        _leaf_row("C", "Adjusted gross income (AGI)", line_map.get("11_adjusted_gross_income", "$0.00"), "Draft AGI from extracted source facts."),
        _leaf_row("D", "Less: deduction strategy applied", line_map.get("12_standard_deduction", "$0.00"), "Standard deduction used unless Schedule A support beats the baseline."),
        _leaf_row("E", "Total taxable income base", line_map.get("15_taxable_income", "$0.00"), "Draft taxable income before unsupported tax calculations."),
        _leaf_row("F", "Tentative progressive tax liability", "Requires tax software calculation", "Run after all income, credits, QBI, capital gain worksheets, and AMT facts are complete."),
        _leaf_row("G", "Less: total non-refundable credits", "Unconfirmed", "Dependent, education, energy, foreign tax, and premium credits require source support."),
        _leaf_row("H", "Plus: self-employment / other taxes", "Review required", "Schedule C, Form 8959, NIIT, early distribution, and household employment tax checks remain open."),
        _leaf_row("I", "Total statutory tax liability", "Not filing-ready", "Blocked until tax calculation and manager review are complete."),
        _leaf_row("J", "Less: total payments & withholdings", _money(payments), "Includes extracted W-2/1099 withholding only; estimated payments and prior-year credits unconfirmed."),
        _leaf_row("K", "Final net cash outcome", "Undetermined", "Refund or balance due cannot be finalized until liability, payments, and credits are complete."),
    ]
    return {
        "rows": rows,
        "withholding_breakdown": {
            "w2_1099_direct_withholding": _money(payments),
            "estimated_tax_paid": "Unconfirmed",
            "prior_year_overpayment_applied": "Unconfirmed",
        },
        "readiness_status": filing_readiness.get("status", "not_ready_for_filing"),
    }


def _leaf_row(code: str, label: str, amount: str, note: str) -> dict[str, str]:
    return {"code": code, "label": label, "amount": amount, "note": note}


def _build_forward_planning(tax_year: int, form_1040: dict[str, Any], source_extraction: dict[str, Any]) -> dict[str, Any]:
    next_year = tax_year + 1
    following_year = tax_year + 2
    line_map = form_1040.get("line_map") if isinstance(form_1040.get("line_map"), dict) else {}
    totals = source_extraction.get("numeric_totals") if isinstance(source_extraction.get("numeric_totals"), dict) else {}
    return {
        "safe_harbor_targets": [
            "Compute 90% of current-year tax after final liability is known.",
            f"Compute 100% or 110% of {tax_year} liability depending on AGI threshold and client profile.",
            f"Compare target to current withholding of {_money(float(totals.get('federal_withholding', 0.0) or 0.0))} and projected {next_year} income.",
        ],
        "estimated_tax_schedule": [
            {"voucher": "1", "due_date": f"April 15, {next_year}", "amount": "To calculate after final liability"},
            {"voucher": "2", "due_date": f"June 15, {next_year}", "amount": "To calculate after final liability"},
            {"voucher": "3", "due_date": f"September 15, {next_year}", "amount": "To calculate after final liability"},
            {"voucher": "4", "due_date": f"January 15, {following_year}", "amount": "To calculate after final liability"},
        ],
        "planning_notes": [
            f"Use draft AGI of {line_map.get('11_adjusted_gross_income', '$0.00')} only as a planning placeholder.",
            "Re-run safe harbor after final credits, capital gains, self-employment tax, and state tax are known.",
        ],
    }


def _build_premium_compliance_risk_assessment(
    risk_register: list[dict[str, Any]],
    source_extraction: dict[str, Any],
    document_dossier: dict[str, Any],
    source_evidence_index: list[dict[str, Any]],
) -> dict[str, Any]:
    totals = source_extraction.get("numeric_totals") if isinstance(source_extraction.get("numeric_totals"), dict) else {}
    doc_flags = set(str(item) for item in _as_list(document_dossier.get("complex_or_partially_supported_forms"), []))
    unsupported_lines = [item for item in source_evidence_index if isinstance(item, dict) and item.get("support_status") != "source_supported"]
    return {
        "red_flag_diagnostics": [
            {
                "check": "Schedule C structural evaluation",
                "status": "Triggered" if float(totals.get("nonemployee_compensation", 0.0) or 0.0) or "1099-NEC" in doc_flags else "Not triggered by current source set",
                "action": "Assess profit motive, business/personal separation, mileage, home office, and recurring loss profile if Schedule C exists.",
            },
            {
                "check": "Outlier charitable giving profile",
                "status": "Open",
                "action": "Compare charitable gifts to AGI and retain acknowledgments for gifts over $250.",
            },
            {
                "check": "Form 8606 / backdoor Roth validation",
                "status": "Open",
                "action": "Ask about nondeductible IRA contributions, conversions, basis, and year-end IRA balances.",
            },
            {
                "check": "Unsupported line evidence",
                "status": f"{len(unsupported_lines)} line(s) require review",
                "action": "Do not move unsupported lines into filing software without source evidence or preparer override.",
            },
        ],
        "state_residency_and_multi_jurisdiction": "Ask about remote work states, resident/nonresident moves, rental locations, and pass-through state-source income.",
        "international_disclosures": "Ask whether foreign accounts or assets crossed FBAR/FATCA thresholds at any time during the tax year.",
        "risk_register": risk_register,
    }


def _build_execution_authorization_timeline() -> list[dict[str, str]]:
    return [
        {
            "step": "Draft presentation",
            "owner": "Preparer",
            "action": "Build the tax software copy, generate final review files, and post them to the secure portal.",
        },
        {
            "step": "Client verification audit",
            "owner": "Taxpayer",
            "action": "Review identifiers, dependents, spelling, direct deposit, income, deductions, and open questions.",
        },
        {
            "step": "Legal submission authorization",
            "owner": "Taxpayer",
            "action": "Sign and return IRS Form 8879; no electronic return can be transmitted without authorization.",
        },
        {
            "step": "E-file transmission",
            "owner": "Preparer",
            "action": "Transmit authorized federal and state returns after all blockers are cleared.",
        },
        {
            "step": "Receipt confirmation",
            "owner": "Preparer",
            "action": "Monitor acknowledgments and provide IRS/state acceptance records for permanent retention.",
        },
    ]


def _build_strategic_post_mortem_advisory(
    advisor_report: dict[str, Any],
    advisor_recommendations: list[dict[str, Any]],
    source_extraction: dict[str, Any],
    document_dossier: dict[str, Any],
    manager_review: dict[str, Any],
) -> dict[str, Any]:
    totals = source_extraction.get("numeric_totals") if isinstance(source_extraction.get("numeric_totals"), dict) else {}
    complex_forms = set(str(item) for item in _as_list(document_dossier.get("complex_or_partially_supported_forms"), []))
    return {
        "high_impact_structural_pivots": [
            {
                "option": "W-4 withholding rebalancing",
                "trigger": "Always useful after refund/balance-due variance is known.",
                "advisor_note": "Adjust current pay stubs to narrow withholding variance while preserving household cash flow.",
            },
            {
                "option": "S-Corporation feasibility review",
                "trigger": "Triggered if Schedule C profit or recurring 1099-NEC consulting income is confirmed.",
                "advisor_note": "Compare payroll compliance costs against potential self-employment tax savings.",
            },
            {
                "option": "Retirement plan implementation",
                "trigger": "Triggered by Schedule C income, high AGI, or underfunded retirement profile.",
                "advisor_note": "Model SEP-IRA, Solo 401(k), and cash balance plan options before year-end.",
            },
            {
                "option": "Investment tax hygiene",
                "trigger": "Triggered" if {"1099-B", "1099-DIV", "brokerage_statement"} & complex_forms else "Review if brokerage activity exists.",
                "advisor_note": "Track wash sales, holding periods, qualified dividends, tax-loss harvesting, and basis records.",
            },
            {
                "option": "Permanent document architecture",
                "trigger": "Always recommended.",
                "advisor_note": "Keep raw logs, receipts, mileage, basis records, and return copies for at least 3 to 7 years in encrypted storage.",
            },
        ],
        "advisor_next_steps": advisor_recommendations[:12] or _as_list(advisor_report.get("next_steps"), []),
        "manager_posture": manager_review.get("manager_signoff", "not_approved_for_filing"),
        "data_gaps_to_close": _as_list(manager_review.get("blockers"), []),
        "cash_flow_planning_watchpoints": [
            f"Current draft withholding support: {_money(float(totals.get('federal_withholding', 0.0) or 0.0))}.",
            "Finalize estimated tax and safe harbor planning after total statutory tax liability is computed.",
        ],
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
        _write_basic_final_artifact_pdf(final_artifact, pdf_path)
        output_files.append({"kind": "tax_review_packet_pdf", "path": str(pdf_path)})
        final_artifact.setdefault("output_warnings", []).append(
            f"PDF review packet used the built-in renderer because reportlab is unavailable: {error}"
        )
    except OSError as error:
        final_artifact.setdefault("output_warnings", []).append(
            f"Could not write PDF review packet to {pdf_path}: {error}"
        )
    except Exception as error:
        try:
            _write_basic_final_artifact_pdf(final_artifact, pdf_path)
            output_files.append({"kind": "tax_review_packet_pdf", "path": str(pdf_path)})
            final_artifact.setdefault("output_warnings", []).append(
                f"PDF review packet used the built-in renderer after reportlab failed: {error}"
            )
        except OSError as fallback_error:
            final_artifact.setdefault("output_warnings", []).append(
                f"Could not render PDF review packet: {error}; built-in renderer also failed: {fallback_error}"
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


def _refresh_output_final_artifact_json(final_artifact: dict[str, Any]) -> None:
    output_files = final_artifact.get("output_files") if isinstance(final_artifact.get("output_files"), list) else []
    for item in output_files:
        if not isinstance(item, dict) or item.get("kind") != "final_artifact_json":
            continue
        path = Path(str(item.get("path") or ""))
        if not path:
            continue
        try:
            path.write_text(json.dumps(final_artifact, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
        except OSError:
            final_artifact.setdefault("output_warnings", []).append(f"Could not refresh final artifact JSON at {path}")


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
    line_map = prepared.get("line_map") if isinstance(prepared.get("line_map"), dict) else {}
    strategic = final_artifact.get("strategic_review") if isinstance(final_artifact.get("strategic_review"), dict) else {}
    tax_year = strategic.get("tax_year") or final_artifact.get("tax_year") or 2025
    executive = strategic.get("executive_engagement_summary") if isinstance(strategic.get("executive_engagement_summary"), dict) else {}
    deductions = strategic.get("deductions_credits_optimization") if isinstance(strategic.get("deductions_credits_optimization"), dict) else {}
    financial_leaf = strategic.get("executive_financial_leaf") if isinstance(strategic.get("executive_financial_leaf"), dict) else {}
    forward = strategic.get("forward_planning") if isinstance(strategic.get("forward_planning"), dict) else {}
    compliance = strategic.get("premium_compliance_risk_assessment") if isinstance(strategic.get("premium_compliance_risk_assessment"), dict) else {}
    post_mortem = strategic.get("strategic_post_mortem_advisory") if isinstance(strategic.get("strategic_post_mortem_advisory"), dict) else {}
    income = strategic.get("income_reconstruction") if isinstance(strategic.get("income_reconstruction"), dict) else {}

    lines = [
        f"# Personal Income Tax Preparation & Strategic Review | Tax Year {tax_year}",
        "",
        f"**Draft warning:** {final_artifact.get('draft_warning') or 'Draft review packet only.'}",
        "",
        str(final_artifact.get("advisor_message") or "").strip(),
        "",
        "## 0. Executive Engagement Summary",
        "",
    ]

    lines.extend(
        [
            f"- **Taxpayer Name(s):** {executive.get('taxpayer_names', 'Unconfirmed - populate during intake')}",
            f"- **Filing Status:** {str(executive.get('filing_status', prepared.get('filing_status', 'single'))).replace('_', ' ')}",
            f"- **Primary CPA / Advisor:** {executive.get('primary_cpa_or_advisor', 'Unassigned')}",
            f"- **Client Data Input Method:** {executive.get('client_data_input_method', 'Hybrid source documents and extracted summaries')}",
            "",
            "> **Executive Tax Regime Overview:**",
            f"> {executive.get('executive_tax_regime_overview', 'Draft strategic review pending complete source documents.')}",
            "",
            f"**Engagement posture:** {executive.get('engagement_posture', 'Draft review only.')}",
            "",
            "## 1. Flexible Document & Data Intake Tracker",
            "",
        ]
    )
    tracker_rows = strategic.get("intake_tracker") if isinstance(strategic.get("intake_tracker"), list) else []
    lines.extend(
        _markdown_table(
            ["Income / Expense Category", "Data Source Format Provided", "Completeness Status", "Verification & Action Notes"],
            [
                [
                    row.get("category", ""),
                    row.get("data_source_format_provided", ""),
                    row.get("completeness_status", ""),
                    f"Taxpayer: {row.get('taxpayer_action', '')}<br>Preparer: {row.get('preparer_action', '')}",
                ]
                for row in tracker_rows
                if isinstance(row, dict)
            ],
        )
    )
    lines.extend(["", "## 2. Income Reconstruction & Narrative", "", "### 2.1 Cash Flow Architecture", ""])
    for item in _as_list(income.get("cash_flow_architecture"), []):
        if isinstance(item, dict):
            lines.append(f"- **{item.get('area', 'Review area')}:** {item.get('finding', '')}")
    roles = income.get("roles_and_responsibilities") if isinstance(income.get("roles_and_responsibilities"), dict) else {}
    lines.extend(["", "### 2.2 Roles & Responsibilities", ""])
    lines.append("**The Taxpayer**")
    lines.extend(f"- {item}" for item in _as_list(roles.get("taxpayer"), []))
    lines.extend(["", "**The Tax Professional**"])
    lines.extend(f"- {item}" for item in _as_list(roles.get("tax_professional"), []))

    lines.extend(["", "## 3. Deductions & Tax Credits Optimization Matrix", "", "### 3.1 Above-the-Line Adjustments", ""])
    lines.extend(
        _markdown_table(
            ["Optimization Vector", "2025 Limit / Rule", "Client Data Provided", "Strategic Advisory & Action Items"],
            [
                [
                    row.get("optimization_vector", ""),
                    row.get("statutory_limit", ""),
                    row.get("client_data_provided", ""),
                    row.get("strategic_advisory", ""),
                ]
                for row in _as_list(deductions.get("above_the_line_adjustments"), [])
                if isinstance(row, dict)
            ],
        )
    )
    standard_baseline = deductions.get("standard_deduction_baseline") if isinstance(deductions.get("standard_deduction_baseline"), dict) else {}
    lines.extend(["", "### 3.2 Deductions Strategy: Standard vs. Itemized (Schedule A)", ""])
    if standard_baseline:
        baseline = " | ".join(f"{key.replace('_', ' ').title()}: **{value}**" for key, value in standard_baseline.items())
        lines.append(f"**2025 Baseline Standard Deductions:** {baseline}")
        lines.append("")
    lines.extend(
        _markdown_table(
            ["Itemized Deductions Tracker", "Gross Amount", "Qualification Criteria & Proof Needed"],
            [
                [row.get("item", ""), row.get("gross_amount", ""), row.get("proof_needed", "")]
                for row in _as_list(deductions.get("schedule_a_tracker"), [])
                if isinstance(row, dict)
            ],
        )
    )

    lines.extend(["", "## 4. Executive Financial Output Summary", ""])
    lines.append("```text")
    lines.append("=" * 80)
    lines.append(f"{tax_year} TAX LIABILITY & CASH OUTCOME FINANCIAL LEAF")
    for row in _as_list(financial_leaf.get("rows"), []):
        if not isinstance(row, dict):
            continue
        lines.append(f"[{row.get('code')}] {str(row.get('label', '')).upper():45} {row.get('amount', '')}")
        note = str(row.get("note") or "").strip()
        if note:
            lines.append(f"    Note: {note}")
    withholding = financial_leaf.get("withholding_breakdown") if isinstance(financial_leaf.get("withholding_breakdown"), dict) else {}
    lines.append("")
    lines.append(f"- W-2 / 1099 Direct Withholding: {withholding.get('w2_1099_direct_withholding', 'Unconfirmed')}")
    lines.append(f"- 2025 Quarterly Estimated Paid: {withholding.get('estimated_tax_paid', 'Unconfirmed')}")
    lines.append(f"- Prior Year Overpayment Applied: {withholding.get('prior_year_overpayment_applied', 'Unconfirmed')}")
    lines.append("=" * 80)
    lines.append("```")

    lines.extend(["", "## 5. Mid-Year 2026 Forward-Looking Planning & Safe Harbors", ""])
    lines.extend(f"- {item}" for item in _as_list(forward.get("safe_harbor_targets"), []))
    lines.extend(["", "**Customized Estimated Tax Payment Schedule**", ""])
    lines.extend(
        _markdown_table(
            ["Voucher", "Due Date", "Amount"],
            [
                [row.get("voucher", ""), row.get("due_date", ""), row.get("amount", "")]
                for row in _as_list(forward.get("estimated_tax_schedule"), [])
                if isinstance(row, dict)
            ],
        )
    )

    lines.extend(["", "## 6. Premium Compliance & Risk Assessment (Audit Defense)", ""])
    for item in _as_list(compliance.get("red_flag_diagnostics"), []):
        if isinstance(item, dict):
            lines.append(f"- **{item.get('check', '')}:** {item.get('status', '')}. {item.get('action', '')}")
    lines.extend(
        [
            f"- **State Residency & Multi-Jurisdiction Allocation:** {compliance.get('state_residency_and_multi_jurisdiction', '')}",
            f"- **International Disclosures:** {compliance.get('international_disclosures', '')}",
            "",
            "### Risk Register",
            "",
        ]
    )
    lines.extend(
        _markdown_table(
            ["Severity", "Category", "Finding", "Advice", "Owner"],
            [
                [risk.get("severity", ""), risk.get("category", ""), risk.get("finding", ""), risk.get("advice", ""), risk.get("owner", "")]
                for risk in _as_list(final_artifact.get("risk_register"), [])
                if isinstance(risk, dict)
            ],
        )
    )

    lines.extend(["", "## 7. Execution, Authorization, and E-File Timeline", ""])
    for index, step in enumerate(_as_list(strategic.get("execution_authorization_timeline"), []), start=1):
        if isinstance(step, dict):
            lines.append(f"{index}. **{step.get('step', '')} ({step.get('owner', '')}):** {step.get('action', '')}")

    lines.extend(["", "## 8. Strategic Post-Mortem Advisory", ""])
    for option in _as_list(post_mortem.get("high_impact_structural_pivots"), []):
        if isinstance(option, dict):
            lines.append(f"- **{option.get('option', '')}:** {option.get('advisor_note', '')} Trigger: {option.get('trigger', '')}")
    lines.extend(["", "### Advisor Next Steps", ""])
    for item in _as_list(post_mortem.get("advisor_next_steps"), []):
        if isinstance(item, dict):
            lines.append(f"- P{item.get('priority')}: {item.get('action')} ({item.get('reason')})")
        else:
            lines.append(f"- {item}")

    lines.extend(["", "## Source Evidence Index", ""])
    lines.extend(
        _markdown_table(
            ["Line", "Draft Value", "Support Status", "Source Documents"],
            [
                [
                    item.get("line", ""),
                    item.get("draft_value", ""),
                    item.get("support_status", ""),
                    ", ".join(
                        str(source.get("filename"))
                        for source in _as_list(item.get("sources"), [])
                        if isinstance(source, dict) and source.get("filename")
                    )
                    or "No direct source",
                ]
                for item in _as_list(final_artifact.get("source_evidence_index"), [])
                if isinstance(item, dict)
            ],
        )
    )

    lines.extend(["", "## Manager Review", ""])
    lines.append(f"- Review status: {manager_review.get('review_status', 'manager_review_required')}")
    lines.append(f"- Signoff: {manager_review.get('manager_signoff', 'not_approved_for_filing')}")
    blockers = manager_review.get("blockers") if isinstance(manager_review.get("blockers"), list) else []
    for blocker in blockers:
        lines.append(f"- Blocker: {blocker}")
    lines.extend(["", "This is a draft review packet, not a filed tax return.", ""])
    return "\n".join(lines)


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


def _write_basic_final_artifact_pdf(final_artifact: dict[str, Any], path: Path) -> None:
    prepared = final_artifact.get("prepared_form_1040") if isinstance(final_artifact.get("prepared_form_1040"), dict) else {}
    review = final_artifact.get("review") if isinstance(final_artifact.get("review"), dict) else {}
    readiness = final_artifact.get("filing_readiness") if isinstance(final_artifact.get("filing_readiness"), dict) else {}
    line_map = prepared.get("line_map") if isinstance(prepared.get("line_map"), dict) else {}
    lines = [
        str(final_artifact.get("title") or "Personal Income Tax Preparation & Strategic Review"),
        "",
        f"Draft warning: {final_artifact.get('draft_warning') or 'Draft review packet only.'}",
        str(final_artifact.get("advisor_message") or ""),
        "",
        "Filing Readiness",
        f"Status: {readiness.get('status', 'not_ready_for_filing')}",
        f"Manager signoff: {readiness.get('manager_signoff', 'not_approved_for_filing')}",
        "",
        "Draft Form 1040 Line Map",
    ]
    lines.extend(f"{key}: {value}" for key, value in line_map.items())
    lines.extend(["", "Risk Register"])
    for risk in _as_list(final_artifact.get("risk_register"), [])[:20]:
        if isinstance(risk, dict):
            lines.append(f"{risk.get('severity', 'review').upper()} / {risk.get('category', 'risk')}: {risk.get('finding', '')}")
        else:
            lines.append(str(risk))
    lines.extend(["", "Review Warnings"])
    lines.extend(str(item) for item in (_as_list(review.get("warnings"), []) or ["None"]))
    lines.extend(["", "Advisor Recommendations"])
    for item in _as_list(final_artifact.get("advisor_recommendations"), [])[:20]:
        if isinstance(item, dict):
            lines.append(f"P{item.get('priority', '')}: {item.get('action', '')}")
        else:
            lines.append(str(item))
    lines.extend(["", "This packet is not filing-ready until all open items are reviewed."])
    _write_basic_pdf(path, lines)


def _write_basic_pdf(path: Path, lines: list[str]) -> None:
    wrapped: list[str] = []
    for line in lines:
        wrapped.extend(_wrap_pdf_line(line))
    pages = [wrapped[index : index + 48] for index in range(0, max(len(wrapped), 1), 48)] or [[]]

    objects: dict[int, bytes] = {
        1: b"<< /Type /Catalog /Pages 2 0 R >>",
        3: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    }
    page_ids: list[int] = []
    next_id = 4
    for page_index, page_lines in enumerate(pages, start=1):
        page_id = next_id
        content_id = next_id + 1
        next_id += 2
        page_ids.append(page_id)
        content_lines = ["BT", "/F1 10 Tf", "50 750 Td", "14 TL"]
        for text in page_lines:
            content_lines.append(f"({_pdf_literal(text)}) Tj")
            content_lines.append("T*")
        content_lines.append(f"(Page {page_index} of {len(pages)}) Tj")
        content_lines.append("ET")
        content = "\n".join(content_lines).encode("latin-1", errors="replace")
        objects[page_id] = (
            f"<< /Type /Page /Parent 2 0 R /Resources << /Font << /F1 3 0 R >> >> "
            f"/MediaBox [0 0 612 792] /Contents {content_id} 0 R >>"
        ).encode("ascii")
        objects[content_id] = b"<< /Length " + str(len(content)).encode("ascii") + b" >>\nstream\n" + content + b"\nendstream"
    kids = " ".join(f"{page_id} 0 R" for page_id in page_ids)
    objects[2] = f"<< /Type /Pages /Kids [{kids}] /Count {len(page_ids)} >>".encode("ascii")

    payload = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets: list[int] = [0]
    for object_id in range(1, max(objects) + 1):
        offsets.append(len(payload))
        payload.extend(f"{object_id} 0 obj\n".encode("ascii"))
        payload.extend(objects[object_id])
        payload.extend(b"\nendobj\n")
    xref_offset = len(payload)
    payload.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    payload.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        payload.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    payload.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode("ascii")
    )
    path.write_bytes(payload)


def _wrap_pdf_line(value: Any, *, width: int = 92) -> list[str]:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if not text:
        return [""]
    words = text.split(" ")
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) <= width:
            current = candidate
            continue
        if current:
            lines.append(current)
        current = word[:width]
        remainder = word[width:]
        while remainder:
            lines.append(current)
            current = remainder[:width]
            remainder = remainder[width:]
    if current:
        lines.append(current)
    return lines or [""]


def _pdf_literal(value: Any) -> str:
    return str(value or "").replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


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
    strategic = final_artifact.get("strategic_review") if isinstance(final_artifact.get("strategic_review"), dict) else {}
    executive = strategic.get("executive_engagement_summary") if isinstance(strategic.get("executive_engagement_summary"), dict) else {}
    income = strategic.get("income_reconstruction") if isinstance(strategic.get("income_reconstruction"), dict) else {}
    deductions = strategic.get("deductions_credits_optimization") if isinstance(strategic.get("deductions_credits_optimization"), dict) else {}
    financial_leaf = strategic.get("executive_financial_leaf") if isinstance(strategic.get("executive_financial_leaf"), dict) else {}
    forward = strategic.get("forward_planning") if isinstance(strategic.get("forward_planning"), dict) else {}
    compliance = strategic.get("premium_compliance_risk_assessment") if isinstance(strategic.get("premium_compliance_risk_assessment"), dict) else {}
    post_mortem = strategic.get("strategic_post_mortem_advisory") if isinstance(strategic.get("strategic_post_mortem_advisory"), dict) else {}
    risk_register = final_artifact.get("risk_register") if isinstance(final_artifact.get("risk_register"), list) else []
    recommendations = (
        final_artifact.get("advisor_recommendations") if isinstance(final_artifact.get("advisor_recommendations"), list) else []
    )
    readiness = final_artifact.get("filing_readiness") if isinstance(final_artifact.get("filing_readiness"), dict) else {}

    story: list[Any] = []
    story.append(Paragraph(_pdf_text(final_artifact.get("title") or "Personal Income Tax Preparation & Strategic Review"), title_style))
    story.append(Paragraph(_pdf_text(final_artifact.get("draft_warning") or "Draft review packet only."), warning_style))
    story.append(Paragraph(_pdf_text(final_artifact.get("advisor_message") or ""), body_style))
    story.append(Spacer(1, 0.18 * inch))

    story.append(Paragraph("0. Executive Engagement Summary", heading_style))
    story.append(
        _pdf_table(
            [
                ["Taxpayer Name(s)", executive.get("taxpayer_names", "Unconfirmed - populate during intake")],
                ["Filing Status", str(executive.get("filing_status", prepared.get("filing_status", "single"))).replace("_", " ")],
                ["Primary CPA / Advisor", executive.get("primary_cpa_or_advisor", "Unassigned")],
                ["Client Data Input Method", executive.get("client_data_input_method", "Hybrid source documents and extracted summaries")],
            ],
            repeat_rows=0,
        )
    )
    story.append(Paragraph(_pdf_text(executive.get("executive_tax_regime_overview", "Draft strategic review pending complete source documents.")), body_style))
    story.append(Spacer(1, 0.1 * inch))

    story.append(Paragraph("1. Flexible Document & Data Intake Tracker", heading_style))
    tracker_rows = [["Category", "Source Format", "Status", "Action Notes"]]
    for row in _as_list(strategic.get("intake_tracker"), [])[:8]:
        if isinstance(row, dict):
            tracker_rows.append(
                [
                    row.get("category", ""),
                    row.get("data_source_format_provided", ""),
                    row.get("completeness_status", ""),
                    f"Taxpayer: {row.get('taxpayer_action', '')}\nPreparer: {row.get('preparer_action', '')}",
                ]
            )
    story.append(_pdf_table(tracker_rows))
    story.append(Spacer(1, 0.12 * inch))

    story.append(Paragraph("2. Income Reconstruction & Narrative", heading_style))
    for item in _as_list(income.get("cash_flow_architecture"), []):
        if isinstance(item, dict):
            story.append(Paragraph(_pdf_text(f"{item.get('area', 'Review area')}: {item.get('finding', '')}"), body_style))
    roles = income.get("roles_and_responsibilities") if isinstance(income.get("roles_and_responsibilities"), dict) else {}
    story.append(Paragraph("Taxpayer responsibilities", heading_style))
    story.extend(_pdf_bullets(_as_list(roles.get("taxpayer"), []) or ["Confirm all income and source documents."], body_style))
    story.append(Paragraph("Tax professional responsibilities", heading_style))
    story.extend(_pdf_bullets(_as_list(roles.get("tax_professional"), []) or ["Classify income and preserve evidence."], body_style))

    story.append(Paragraph("3. Deductions & Tax Credits Optimization Matrix", heading_style))
    adjustment_rows = [["Optimization Vector", "2025 Limit / Rule", "Client Data", "Advisory"]]
    for row in _as_list(deductions.get("above_the_line_adjustments"), []):
        if isinstance(row, dict):
            adjustment_rows.append(
                [
                    row.get("optimization_vector", ""),
                    row.get("statutory_limit", ""),
                    row.get("client_data_provided", ""),
                    row.get("strategic_advisory", ""),
                ]
            )
    story.append(_pdf_table(adjustment_rows))
    schedule_rows = [["Itemized Deduction", "Amount", "Proof Needed"]]
    for row in _as_list(deductions.get("schedule_a_tracker"), []):
        if isinstance(row, dict):
            schedule_rows.append([row.get("item", ""), row.get("gross_amount", ""), row.get("proof_needed", "")])
    story.append(Paragraph("Schedule A strategy", heading_style))
    story.append(_pdf_table(schedule_rows))

    story.append(Paragraph("4. Executive Financial Output Summary", heading_style))
    financial_rows = [["Code", "Line", "Amount", "Review Note"]]
    for row in _as_list(financial_leaf.get("rows"), []):
        if isinstance(row, dict):
            financial_rows.append([row.get("code", ""), row.get("label", ""), row.get("amount", ""), row.get("note", "")])
    story.append(_pdf_table(financial_rows))

    story.append(Paragraph("5. Mid-Year 2026 Forward-Looking Planning & Safe Harbors", heading_style))
    story.extend(_pdf_bullets(_as_list(forward.get("safe_harbor_targets"), []) or ["Calculate safe harbor after final liability is known."], body_style))
    voucher_rows = [["Voucher", "Due Date", "Amount"]]
    for row in _as_list(forward.get("estimated_tax_schedule"), []):
        if isinstance(row, dict):
            voucher_rows.append([row.get("voucher", ""), row.get("due_date", ""), row.get("amount", "")])
    story.append(_pdf_table(voucher_rows))

    story.append(Paragraph("6. Premium Compliance & Risk Assessment", heading_style))
    story.extend(
        _pdf_bullets(
            [
                f"{item.get('check', '')}: {item.get('status', '')}. {item.get('action', '')}"
                for item in _as_list(compliance.get("red_flag_diagnostics"), [])
                if isinstance(item, dict)
            ]
            or ["No compliance diagnostics were generated."],
            body_style,
        )
    )
    story.append(Paragraph(_pdf_text(compliance.get("state_residency_and_multi_jurisdiction", "")), body_style))
    story.append(Paragraph(_pdf_text(compliance.get("international_disclosures", "")), body_style))

    story.append(Paragraph("7. Execution, Authorization, and E-File Timeline", heading_style))
    story.extend(
        _pdf_bullets(
            [
                f"{step.get('step', '')} ({step.get('owner', '')}): {step.get('action', '')}"
                for step in _as_list(strategic.get("execution_authorization_timeline"), [])
                if isinstance(step, dict)
            ]
            or ["Complete client verification and signed authorization before e-file."],
            body_style,
        )
    )

    story.append(Paragraph("8. Strategic Post-Mortem Advisory", heading_style))
    story.extend(
        _pdf_bullets(
            [
                f"{option.get('option', '')}: {option.get('advisor_note', '')} Trigger: {option.get('trigger', '')}"
                for option in _as_list(post_mortem.get("high_impact_structural_pivots"), [])
                if isinstance(option, dict)
            ]
            or ["Review W-4, entity structure, retirement funding, and document architecture after filing."],
            body_style,
        )
    )

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

    story.append(Paragraph("Risk Register", heading_style))
    story.extend(
        _pdf_bullets(
            [
                f"{risk.get('severity', 'review').upper()} / {risk.get('category', 'risk')}: {risk.get('finding', '')}"
                for risk in risk_register
                if isinstance(risk, dict)
            ]
            or ["No automated risks were produced."],
            body_style,
        )
    )

    story.append(Paragraph("Filing Readiness", heading_style))
    readiness_rows = [
        ["Status", readiness.get("status", "not_ready_for_filing")],
        ["Manager signoff", readiness.get("manager_signoff", "not_approved_for_filing")],
    ]
    story.append(_pdf_table([[_pdf_text(left), _pdf_text(right)] for left, right in readiness_rows]))

    story.append(Paragraph("Advisor Recommendations", heading_style))
    story.extend(
        _pdf_bullets(
            [
                f"P{recommendation.get('priority')}: {recommendation.get('action')}"
                for recommendation in recommendations[:10]
                if isinstance(recommendation, dict)
            ]
            or ["Review the packet with the taxpayer or a qualified preparer."],
            body_style,
        )
    )

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


def _pdf_table(rows: list[list[Any]], *, repeat_rows: int = 1) -> Any:
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import Paragraph
    from reportlab.platypus import Table, TableStyle

    column_count = max((len(row) for row in rows), default=1)
    widths_by_column_count = {
        2: [2.1 * inch, 4.2 * inch],
        3: [1.6 * inch, 1.4 * inch, 3.3 * inch],
        4: [1.35 * inch, 1.55 * inch, 1.25 * inch, 2.2 * inch],
        5: [0.8 * inch, 1.0 * inch, 1.7 * inch, 2.0 * inch, 0.8 * inch],
    }
    col_widths = widths_by_column_count.get(column_count)
    cell_style = ParagraphStyle("TableCell", fontName="Helvetica", fontSize=7.2, leading=8.5)
    header_style = ParagraphStyle("TableHeader", parent=cell_style, fontName="Helvetica-Bold", textColor=colors.HexColor("#10233F"))
    wrapped_rows = []
    for row_index, row in enumerate(rows):
        padded = [*row, *[""] * (column_count - len(row))]
        style = header_style if repeat_rows and row_index < repeat_rows else cell_style
        wrapped_rows.append([Paragraph(_pdf_text(item), style) for item in padded[:column_count]])

    table = Table(wrapped_rows, hAlign="LEFT", repeatRows=repeat_rows, colWidths=col_widths)
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
