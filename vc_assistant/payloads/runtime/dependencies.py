"""Prepare installed/local dependencies before loading VC handlers."""

from __future__ import annotations

import importlib.util
from pathlib import Path


RUNTIME_SKILL_PACKAGES = (
    "mirrorneuron-blueprint-support-skill",
    "mirrorneuron-llm-ocr-skill",
    "mirrorneuron-rag-skill",
    "mirrorneuron-w3m-browser-skill",
    "mirrorneuron-web-browser-skill",
    "mirrorneuron-evidence-engine-skill",
    "mirrorneuron-actor-review-skill",
    "mirrorneuron-client-report-skill",
    "mirrorneuron-document-reading-skill",
    "mirrorneuron-public-research-orchestrator-skill",
    "mirrorneuron-scoring-framework-skill",
)


def prepare_dependencies(runtime_file: str | Path) -> None:
    for parent in Path(runtime_file).resolve().parents:
        helper = parent / "otterdesk_blueprint_env.py"
        if not helper.exists():
            continue
        spec = importlib.util.spec_from_file_location("otterdesk_blueprint_env", helper)
        if spec is None or spec.loader is None:
            return
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.bootstrap_blueprint_runtime(
            runtime_file, packages=RUNTIME_SKILL_PACKAGES
        )
        return


__all__ = ["RUNTIME_SKILL_PACKAGES", "prepare_dependencies"]
