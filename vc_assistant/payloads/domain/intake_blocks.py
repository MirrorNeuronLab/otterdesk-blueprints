"""Native intake specialists over verified, explicit VC evidence snapshots."""

from mn_sdk.agent_events import activity_operation
from mn_sdk.blueprint_support import slugify, write_json
from mn_sdk.integrations.block_inputs import capture_declared_inputs

from .common import utc_now_iso
from .composition import hydrate_cached_companies
from .evidence import build_company_evidence_layer
from .intake import (
    build_company_work_queue, force_reprocess_enabled, group_document_file_records,
    load_watch_state, processed_and_skipped_company_names, scan_documents,
    OcrRequiredError, MarkdownConversionError,
)
from .intake_state import (
    prepare_snapshot, publish_snapshot, read_snapshot, source_inventory,
    materialize_sources, capture_processed_inputs,
)
from .runtime_tools import append_event


@activity_operation('Checking startup folders for changes', completed='Checking startup folders for changes: completed')
def startup_folder_watcher(block, inputs):
    values = capture_declared_inputs(block, inputs, runtime_file=__file__)
    folder = values.get("document_folder") or values.get("input_folder")
    if not folder:
        raise ValueError("VC intake requires a staged document folder")
    files = source_inventory(block, values["document_folder"])
    state = {"inputs": values, "started_at": utc_now_iso(), "files": files,
             "force_reprocess": force_reprocess_enabled(values, block.config)}
    state = prepare_snapshot(block, state, "startup_folder_watcher")
    append_event(block.store.run_dir, "watch_cycle_started", {"cycle": 1,
        "max_cycles": int((values.get("monitoring") or {}).get("max_cycles") or 1)})
    return publish_snapshot(block, state, "startup_folder_watcher",
        {"document_file_count": len(state["files"]), "document_folder": state["inputs"]["document_folder"]},
        {"document_files.json": state["files"]})


@activity_operation('Grouping company documents', completed='Grouping company documents: completed')
def company_packet_grouper(block, inputs):
    state = read_snapshot(block, inputs, "startup_folder_watcher")
    folder, files = materialize_sources(block, state)
    groups = group_document_file_records(folder, files)
    state["packets"] = [{"company_name": company, "company_slug": slugify(company),
        "document_count": len(items), "source_refs": [item["path"] for item in items]}
        for company, items in groups.items()]
    state = prepare_snapshot(block, state, "company_packet_grouper")
    return publish_snapshot(block, state, "company_packet_grouper",
        {"company_count": len(state["packets"]), "document_file_count": len(state["files"])},
        {"company_packet_groups.json": state["packets"]})


@activity_operation('Extracting document evidence', completed='Extracting document evidence: completed')
def document_evidence_extractor(block, inputs):
    state = read_snapshot(block, inputs, "company_packet_grouper")
    folder, _ = materialize_sources(block, state)
    try:
        state["records"] = scan_documents(folder, block.config,
            source_output_folder=block.output_directory / "context_sources" / "inputs",
            source_scope={"job_id": block.job_id, "run_id": block.run_id})
    except (OcrRequiredError, MarkdownConversionError) as exc:
        ocr = isinstance(exc, OcrRequiredError) or isinstance(exc.__cause__, OcrRequiredError)
        append_event(block.store.run_dir, "tool_call_failed", {
            "tool": "llm_ocr.extract_document_folder" if ocr else "docs_to_markdown.convert_documents",
            "status": "required_ocr_failed" if ocr else "required_document_conversion_failed",
            "error": str(exc),
        })
        raise
    if not state["records"]:
        state["records"] = {"Sample Startup": []}
    if state["files"]:
        state["source_files"] = capture_processed_inputs(block, state["records"])
    else:
        state["source_files"] = []
    materialize_sources(block, state)
    state = prepare_snapshot(block, state, "document_evidence_extractor")
    return publish_snapshot(block, state, "document_evidence_extractor",
        {"company_count": len(state["records"]),
         "document_count": sum(len(records) for records in state["records"].values())},
        {"company_records.json": state["records"]})


@activity_operation('Normalizing company claims', completed='Normalizing company claims: completed')
def claim_normalizer(block, inputs):
    state = read_snapshot(block, inputs, "document_evidence_extractor")
    output = block.output_directory
    queue = build_company_work_queue(state["records"], load_watch_state(output),
        force_reprocess=state["force_reprocess"])
    state["cached"] = hydrate_cached_companies(output, block.config, state["records"], queue)
    state["queue"] = queue
    state["evidence"] = {company: build_company_evidence_layer(company, records, [],
        source_scope={"job_id": block.job_id, "run_id": block.run_id})
        for company, records in sorted(state["records"].items(), key=lambda item: slugify(item[0]))}
    state = prepare_snapshot(block, state, "claim_normalizer")
    queue = state["queue"]
    count = sum(len(layer.get("claim_records") or []) for layer in state["evidence"].values())
    processed, skipped = processed_and_skipped_company_names(queue)
    views = {"company_work_queue.json": queue,
        **{f"company_evidence/{slugify(company)}.json": layer for company, layer in state["evidence"].items()},
        **{f"{collection}/{slugify(company)}.json": value
           for collection, values in state["cached"].items() for company, value in values.items()}}
    write_json(output / "company_work_queue.json", queue)
    write_json(block.store.run_dir / "company_work_queue.json", queue)
    return publish_snapshot(block, state, "claim_normalizer",
        {"processed_company_count": len(processed), "skipped_company_count": len(skipped),
         "normalized_claim_count": count}, views)
