"""Product input policy and publication for one document OCR run."""
from pathlib import Path
from mn_nvidia_ocr_skill import build_ocr_request, detect_document_suffix, validate_result
from mn_nvidia_ocr_skill.contracts import MAX_INPUT_BYTES
from mn_sdk.blueprint.inputs import capture_declared_inputs
from mn_sdk.blueprint.outputs import publish_artifact_bundle
from mn_sdk_common.publication import ArtifactWrite


def prepare(block, inputs):
    inputs = capture_declared_inputs(block, inputs, runtime_file=__file__)
    path = Path(inputs.get("document_file") or "")
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        raise ValueError("Provide one resolved staged document file")
    with path.open("rb") as stream:
        data = stream.read(MAX_INPUT_BYTES + 1)
    request = build_ocr_request(data, suffix=detect_document_suffix(data), merge_level=inputs.get("merge_level", "paragraph"))
    ref = block.store.commit_bytes(block.root + "/source.bin", data, kind="ocr_source")
    request["payload"]["document_base64"] = {"$artifact": ref.to_dict(), "encoding": "base64"}
    return request


def accepted(block, result):
    validate_result(result)
    return True


def publish(block, data):
    source = data["request"]["payload"]["document_base64"]["$artifact"]
    block.store.validate(source)
    result = validate_result(data["result"], input_sha256=source["sha256"])
    if result["merge_level"] != data["request"]["payload"]["merge_level"]:
        raise ValueError("OCR response does not match requested merge level")
    report = block.store.commit("ocr_result.json", result, kind="ocr_result")
    text = "\n\n".join(page["text"] for page in result["pages"]) + "\n"
    markdown = "# OCR transcript\n\n" + "\n\n".join(
        "## Page " + str(page["page_number"]) + "\n\n" + page["text"] for page in result["pages"]
    ) + "\n"
    plain = block.store.commit_bytes("text.txt", text.encode(), kind="text")
    md = block.store.commit_bytes("document.md", markdown.encode(), kind="markdown")
    publish_artifact_bundle(block, [
        ArtifactWrite("ocr_result", "ocr_result.json", block.store.read_bytes(report), kind="ocr_result", authoritative=True),
        ArtifactWrite("text", "text.txt", block.store.read_bytes(plain), kind="text"),
        ArtifactWrite("markdown", "document.md", block.store.read_bytes(md), kind="markdown"),
    ], receipt_path=block.root + "/publication.json")
    return {"report": report.to_dict(), "page_count": len(result["pages"]), "artifacts": [report.to_dict(), plain.to_dict(), md.to_dict()]}
