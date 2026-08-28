"""Shared runtime context and OCR-service preparation for Legal Assistant."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mn_sdk.blueprint_support import (
    create_blueprint_run_context,
    persist_blueprint_run_context,
    resolve_existing_path,
)

from .common import *

def fake_llm_requested(config: dict[str, Any], payload: dict[str, Any] | None = None) -> bool:
    if not payload or not payload.get("quick_test"):
        return fake_llm_mode_enabled(config)
    merged = copy.deepcopy(config)
    merged.setdefault("execution", {})["quick_test"] = True
    return fake_llm_mode_enabled(merged)

def _ocr_skill_config(config: dict[str, Any]) -> dict[str, Any]:
    input_skills = config.get("input_skills") if isinstance(config.get("input_skills"), dict) else {}
    return {"input_skills": input_skills}

def build_ocr_runtime(ctx: dict[str, Any]) -> tuple[Any | None, dict[str, Any]]:
    section = (ctx["config"].get("input_skills") or {}).get("llm_ocr")
    section = section if isinstance(section, dict) else {}
    install_policy = str(section.get("install_policy") or "on_first_required_document")
    status: dict[str, Any] = {
        "enabled": section.get("enabled", True) is not False,
        "skill_available": extract_document is not None and docker_ocr_client_factory_from_config is not None,
        "configured": False,
        "status": "not_needed",
        "install_policy": install_policy,
        "trigger": f"PDF/image with less than {OCR_MIN_TEXT_CHARS} embedded characters",
        "source_model": "runtime_selected_by_llm_ocr_skill",
        "warnings": [],
    }
    if not status["enabled"]:
        status["status"] = "disabled"
        status["warnings"].append("llm_ocr_disabled_in_config")
        return None, status
    if fake_llm_requested(ctx["config"], ctx.get("payload")):
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
                "status": "ready_for_runtime_managed_first_use" if install_policy == "runtime" else "ready_for_lazy_first_use",
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


def runtime_context_for_step(
    *,
    inputs: dict[str, Any] | None = None,
    config: dict[str, Any] | None = None,
    runs_root: str | Path | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    base = create_blueprint_run_context(
        runtime_file=__file__,
        blueprint_id=BLUEPRINT_ID,
        inputs=inputs,
        config=config,
        runs_root=runs_root,
        run_id=run_id,
    )
    payload = base.payload
    search_roots = [base.layout.payload_root, base.layout.root, base.layout.root.parent]
    document_folder: Path | None = None
    first_candidate: Path | None = None
    for raw_path in (payload.get("document_folder"), payload.get("input_folder")):
        if not str(raw_path or "").strip():
            continue
        candidate = resolve_existing_path(
            raw_path,
            search_roots,
            blueprint_id=BLUEPRINT_ID,
        )
        first_candidate = first_candidate or candidate
        if candidate.exists():
            document_folder = candidate
            break

    document_folder = document_folder or first_candidate
    if document_folder is None or not document_folder.exists():
        document_folder = base.layout.root / "examples" / "sample_inputs"
    payload["document_folder"] = str(document_folder)
    payload["input_folder"] = str(document_folder)

    context = base.to_mapping()
    context.update(
        {
            "_base_context": base,
            "document_folder": document_folder,
        }
    )
    persist_blueprint_run_context(base, document_folder=str(document_folder))
    return context


__all__ = ["append_event", "build_ocr_runtime", "runtime_context_for_step"]
