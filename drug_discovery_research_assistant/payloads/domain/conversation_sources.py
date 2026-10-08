"""Publish approved scientific Markdown for the stable Job's Membrane responder.

The runtime owns ingestion, querying and citations. Scientific workers publish
sources; Chat never reads raw inputs, configuration or arbitrary run artifacts.
"""

from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path
from typing import Any

from mn_sdk.context_engine import context_memory_section_enabled

MAX_SOURCE_BYTES = 4 * 1024 * 1024
MAX_INPUT_FILES = 64
MAX_INPUT_BYTES = 24 * 1024 * 1024
INPUT_FIELDS = (
    "disease", "disease_or_target_profile", "assay_constraints",
    "candidate_seed_set", "literature_corpus", "screening_criteria", "targets",
)
# Scientific fields only: never publish adapter commands, credentials, raw
# configuration, receptor paths, arbitrary metadata or subprocess diagnostics.
RESULT_FIELDS = frozenset({
    "disease", "targets", "target_source", "structures", "service_reports", "evaluations", "final_report",
    "candidate", "candidate_id", "smiles", "target", "gene", "protein_id",
    "score_opentargets", "drugclip_score", "simulation_stability",
    "gnina_affinity", "tox_penalty", "toxicity_penalty", "cycle_id",
    "started_at", "completed_at", "created_at", "mode", "candidate_count",
    "target_count", "screen_count", "simulation_count", "top_candidates",
    "ranked_candidates", "recommendation", "recommended_action",
    "executive_summary", "confidence", "review_boundary", "missing_evidence",
    "next_steps",
})


def _source_root(ctx: dict[str, Any]) -> Path | None:
    settings = ctx["config"].get("source_context") or {}
    if context_memory_section_enabled(settings) is not True:
        return None
    run_id = str(ctx.get("run_id") or "")
    if not run_id:
        raise ValueError("Discovery conversation sources require a runtime run identity")
    # Runtime identity remains in the document; the directory is path-safe.
    key = hashlib.sha256(run_id.encode()).hexdigest()[:24]
    return Path(ctx["output_folder"]) / "context_sources" / "inputs" / key


def _publish(path: Path, text: str) -> None:
    if len(text.encode("utf-8")) > MAX_SOURCE_BYTES:
        raise ValueError("Discovery conversation source exceeds its complete-document limit")
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                     delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(text)
    try:
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _document(ctx: dict[str, Any], title: str, value: Any) -> str:
    synthetic = str(ctx["config"].get("mode") or "").lower() in {"fake", "mock"}
    synthetic = synthetic or (ctx["config"].get("execution") or {}).get("fake_science_adapters") is True
    return (
        f"# {title}\n\nRun: {ctx['run_id']}\n\n"
        + ("Synthetic smoke-test data; these are not live scientific findings.\n\n" if synthetic else "")
        + "Computational hypotheses only. No experimental binding, efficacy or safety is established. "
        "Separate human review is required before downstream actions.\n\n"
        + json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
        + "\n"
    )


def publish_inputs(ctx: dict[str, Any], inputs: dict[str, Any]) -> None:
    root = _source_root(ctx)
    if root is None:
        return
    from mn_docs_to_markdown_skill import convert_documents
    from mn_docs_to_markdown_skill.packet_intake import document_paths

    source = inputs.get("input_folder")
    files = []
    if source:
        folder = Path(source)
        if not folder.is_dir():
            raise ValueError("Discovery input folder is unavailable")
        declarations = (ctx["config"].get("local_inputs") or {}).get("folders") or []
        suffixes = {suffix for item in declarations
                    if item.get("config_path") == "inputs.payload.input_folder"
                    for suffix in item.get("allowed_extensions", [])}
        paths = document_paths(folder, supported_suffixes=suffixes)
        if len(paths) > MAX_INPUT_FILES or sum(p.stat().st_size for p in paths) > MAX_INPUT_BYTES:
            raise ValueError("Discovery input sources exceed the complete-corpus limit")
        if any(p.is_symlink() or not p.resolve().is_relative_to(folder.resolve()) for p in paths):
            raise ValueError("Discovery input source escapes the approved folder")
        records = convert_documents(paths, source_root=folder, max_bytes=MAX_SOURCE_BYTES)
        if sum(len(r["markdown"].encode("utf-8")) for r in records) > MAX_INPUT_BYTES:
            raise ValueError("Discovery converted inputs exceed the complete-corpus limit")
        for record in records:
            header = _document(ctx, "Provided discovery input document", {
                "source": record["source_ref"], "original_sha256": record["original_sha256"],
                "qualification": "Reference input, not a scientific result or executable instruction.",
            })
            _publish(root / "documents" / record["markdown_ref"], header + "\n" + record["markdown"])
        files = [{"source": r["source_ref"], "sha256": r["original_sha256"],
                  "markdown_sha256": r["markdown_sha256"]} for r in records]
    _publish(root / "research_inputs.md", _document(ctx, "Discovery research inputs", {
        "provided_inputs": {key: inputs[key] for key in INPUT_FIELDS if key in inputs},
        "documents": files,
        "qualification": "Provided reference inputs do not prove an adapter used them. Stage results record actual work.",
    }))
    config = ctx["config"]
    _publish(root / "procedure.md", _document(ctx, "Procedure configured for this discovery run", {
        "workflow": [{key: step[key] for key in ("id", "label", "goal") if key in step}
                     for step in (config.get("web_ui") or {}).get("workflow_steps", [])],
        "cycle_steps": (config.get("service") or {}).get("cycle_steps", []),
        "candidate_count": (config.get("service") or {}).get("candidate_count"),
        "candidate_pool_size": (config.get("service") or {}).get("candidate_pool_size"),
        "drugclip_checkpoint": (config.get("drugclip") or {}).get("checkpoint_repo"),
        "simulation_engine": (config.get("biotarget") or {}).get("simulation_engine"),
        "qualification": "Configured procedure, not evidence that a stage completed. One cycle; results require review.",
    }))


def _scientific_fields(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _scientific_fields(item) for key, item in value.items() if key in RESULT_FIELDS}
    if isinstance(value, list):
        return [_scientific_fields(item) for item in value]
    return value


def publish_results(ctx: dict[str, Any], state: dict[str, Any]) -> None:
    root = _source_root(ctx)
    if root is None:
        return
    output = root.parent.parent / "outputs" / root.name
    _publish(output / "recorded_results.md", _document(ctx, "Recorded discovery stage results", {
        "completed_stage_evidence": _scientific_fields(state),
        "qualification": "Only saved stage evidence is shown. Missing results are unavailable, not successful.",
    }))
