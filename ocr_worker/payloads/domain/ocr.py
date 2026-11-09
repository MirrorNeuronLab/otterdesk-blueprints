"""Folder OCR policy; the SDK owns model journals and verified publication."""

from pathlib import Path

from mn_nvidia_ocr_skill import MODEL_REVISION, SOURCE_MODEL, validate_result
from mn_nvidia_ocr_skill.contracts import MERGE_LEVELS
from mn_sdk.blueprint.context import source_manifest
from mn_sdk.blueprint.hooks import ProcessingProgress, fingerprint, report_activity
from mn_sdk.blueprint.inputs import capture_declared_inputs
from mn_sdk.blueprint.models import model_request
from mn_sdk.blueprint.outputs import publish_artifact_bundle
from mn_sdk_common.publication import ArtifactWrite

from .documents import prepare_document, snapshot_folder
from .office import DocumentInputError
from .reporting import publish_comparison


def _publish_document(block, item, prepared, result):
    result = validate_result(result, input_sha256=prepared["input_sha256"])
    prefix = "documents/" + item["source"] + "/"
    report = block.store.commit(prefix + "ocr_result.json", result, kind="ocr_result")
    text = "\n\n".join(page["text"] for page in result["pages"]) + "\n"
    markdown = (
        "# OCR transcript\n\n"
        + "\n\n".join(
            "## Page " + str(page["page_number"]) + "\n\n" + page["text"]
            for page in result["pages"]
        )
        + "\n"
    )
    plain = block.store.commit_bytes(prefix + "text.txt", text.encode(), kind="text")
    md = block.store.commit_bytes(
        prefix + "document.md", markdown.encode(), kind="markdown"
    )
    refs = [report, plain, md]
    publish_artifact_bundle(
        block,
        [
            ArtifactWrite(
                ref.kind,
                ref.path,
                block.store.read_bytes(ref),
                kind=ref.kind,
                authoritative=True,
            )
            for ref in refs
        ],
        receipt_path=block.root + "/published/" + fingerprint(item["source"]) + ".json",
    )
    return {
        "source": item["source"],
        "source_sha256": item["source_sha256"],
        "input_sha256": prepared["input_sha256"],
        "status": "completed",
        "page_count": len(result["pages"]),
        "warnings": result["warnings"],
        "artifacts": [ref.to_dict() for ref in refs],
    }


def run(block, inputs):
    inputs = capture_declared_inputs(block, inputs, runtime_file=__file__)
    folder = Path(inputs.get("input_folder") or "")
    if not folder.is_absolute():
        raise ValueError("Provide one resolved staged source folder")
    merge = inputs.get("merge_level", "paragraph")
    if merge not in MERGE_LEVELS:
        raise ValueError("Text grouping must be paragraph, sentence or word")
    inventory_path = block.root + "/document-inventory.json"
    inventory = block.read_checkpoint(
        block.freeze_checkpoint(inventory_path, lambda: snapshot_folder(block, folder)),
        expected_path=inventory_path,
    )
    declaration = source_manifest(__file__)["runtime"]["models"]["ocr"]
    records = []
    report_inputs = []
    progress = ProcessingProgress("page", context=block).start()
    for index, item in enumerate(inventory["files"], 1):
        block.check()
        report_activity(
            f"Reading document {index} of {len(inventory['files'])}", kind="action"
        )
        prepared_path = (
            block.root + "/prepared/" + fingerprint(item["source"]) + ".json"
        )

        def prepare(item=item):
            try:
                return prepare_document(block, item)
            except DocumentInputError as error:
                return {"error": str(error)}

        prepared = block.read_checkpoint(
            block.freeze_checkpoint(prepared_path, prepare),
            expected_path=prepared_path,
        )
        report_inputs.append((item, prepared))
        if "error" in prepared:
            records.append(
                {
                    "source": item["source"],
                    "source_sha256": item["source_sha256"],
                    "status": "failed",
                    "error": prepared["error"],
                }
            )
            continue
        request = {
            "purpose": "ocr",
            "model": declaration["model"],
            "path": "/ocr",
            "payload": {
                "document_base64": {
                    "$artifact": prepared["document"],
                    "encoding": "base64",
                },
                "suffix": prepared["suffix"],
                "merge_level": merge,
            },
            "options": {
                "provider": declaration["provider"],
                "backend": declaration["backend"],
                "model_spec": declaration["model_spec"],
                "timeout_seconds": 900,
            },
        }
        key = fingerprint(item["source"])
        response = model_request(block, request, key=key)
        if response.get("merge_level") != merge:
            raise ValueError("OCR response does not match requested text grouping")
        records.append(_publish_document(block, item, prepared, response))
        progress.record_model_response(
            block, request, key=key, units=len(response["pages"])
        )
    progress.finish()
    succeeded = sum(item["status"] == "completed" for item in records)
    failed = len(records) - succeeded
    report = {
        "schema": "mn.nvidia_ocr.batch.v1",
        "source_model": SOURCE_MODEL,
        "model_revision": MODEL_REVISION,
        "status": ("partial" if succeeded else "failed") if failed else "completed",
        "file_count": len(records),
        "completed_count": succeeded,
        "failed_count": failed,
        "skipped_count": len(inventory["skipped"]),
        "files": records,
        "skipped": inventory["skipped"],
    }
    ref = block.store.commit("ocr_result.json", report, kind="ocr_batch")
    summary = (
        f"# OCR results\n\n{succeeded} documents completed; {failed} failed; "
        f"{len(inventory['skipped'])} unsupported files skipped.\n\n"
        + "\n".join(f"- {item['source']}: {item['status']}" for item in records)
        + "\n"
    )
    md = block.store.commit_bytes("document.md", summary.encode(), kind="markdown")
    publish_artifact_bundle(
        block,
        [
            ArtifactWrite(
                "ocr_result",
                "ocr_result.json",
                block.store.read_bytes(ref),
                kind="ocr_batch",
                authoritative=True,
            ),
            ArtifactWrite(
                "summary", "document.md", block.store.read_bytes(md), kind="markdown"
            ),
        ],
        receipt_path=block.root + "/publication.json",
    )
    publish_comparison(block, report, report_inputs)
    if not succeeded:
        raise ValueError("No documents could be read. Review the batch summary.")
    return {"report": ref.to_dict(), "file_count": len(records), "failed_count": failed}
