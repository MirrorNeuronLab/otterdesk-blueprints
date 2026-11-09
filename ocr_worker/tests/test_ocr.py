"""Offline compiled folder worker checks; only CUDA inference is injected."""

import base64
import hashlib
import io
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import jsonschema
import pytest
from mn_nvidia_ocr_skill.backend import NemotronOcrBackend
from mn_sdk.blueprints import compile_blueprint, read_blueprint, resolve_config
from mn_sdk.blueprints.worker_descriptors import resolved_worker_descriptor
from mn_sdk.integrations.block_worker import run
from mn_sdk.step_runtime import StepContext
from mn_sdk_common.committed_artifacts import CommittedJsonStore
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SAMPLE_HASH = "82ae016f652e36a8b0721dca2e38f999c245c524dd1f2631968be8901123841d"


def pdf_bytes(pages=1):
    import pypdfium2 as pdfium

    data = io.BytesIO()
    with pdfium.PdfDocument.new() as pdf:
        for _ in range(pages):
            pdf.new_page(80, 30).close()
        pdf.save(data)
    return data.getvalue()


@pytest.fixture
def worker(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "payloads"))
    for name in list(sys.modules):
        if name == "domain" or name.startswith("domain."):
            monkeypatch.delitem(sys.modules, name)
    package = read_blueprint(ROOT)
    config = resolve_config(package)
    compiled = compile_blueprint(package, config).manifest
    descriptor = tmp_path / "manifest.json"
    descriptor.write_text(
        json.dumps(resolved_worker_descriptor(package, compiled, config))
    )
    node = next(
        n
        for n in compiled["agents"]["nodes"]
        if n.get("config", {}).get("environment", {}).get("MN_WORKFLOW_STEP_HANDLER")
        == "mn_sdk.integrations.block_worker"
    )
    parameters = json.loads(node["config"]["environment"]["MN_WORKFLOW_STEP_WITH_JSON"])
    environment = {
        "MN_RUN_DIR": str(tmp_path / "run"),
        "MN_BLUEPRINT_MANIFEST_PATH": str(descriptor),
        "MN_SDK_COMPONENTS_JSON": '["blueprint-blocks"]',
    }
    for key, value in environment.items():
        monkeypatch.setenv(key, value)
    folder = tmp_path / "documents"
    folder.mkdir()
    image = io.BytesIO()
    Image.new("RGB", (80, 30), "white").save(image, format="PNG")
    (folder / "source.png").write_bytes(image.getvalue())
    inputs = {"input_folder": str(folder), "merge_level": "paragraph"}
    backend = NemotronOcrBackend(
        pipeline_factory=lambda: (
            lambda *a, **k: [
                {
                    "text": "Synthetic source text",
                    "confidence": 0.9,
                    "left": 0.1,
                    "lower": 0.2,
                    "right": 0.9,
                    "upper": 0.8,
                }
            ]
        )
    )
    calls, responses, changes = [], [], {}

    def request(*args, **options):
        calls.append((args, options))
        payload = args[3]
        result = backend.extract(
            base64.b64decode(payload["document_base64"]),
            suffix=payload["suffix"],
            merge_level=payload["merge_level"],
        )
        result.update(changes)
        responses.append(result)
        return result

    monkeypatch.setattr(
        "mn_sdk.integrations.block_model_request.runtime_model_json_request", request
    )

    def execute():
        return run(
            StepContext(
                step_id="extract_folder_text",
                agent_id=node["node_id"],
                run_id="ocr-test",
                idempotency_key="ocr-test/extract",
                config=config.data,
                environment=environment,
                message={"body": {"step_input": inputs}},
            ),
            **parameters,
        )

    return SimpleNamespace(
        execute=execute,
        calls=calls,
        store=CommittedJsonStore(tmp_path / "run"),
        inputs=inputs,
        folder=folder,
        responses=responses,
        changes=changes,
    )


def batch(worker):
    result = worker.store.read_path("ocr_result.json")
    schema = json.loads((ROOT / "contracts.json").read_text())["outputs"]["primary"][
        "schema"
    ]
    jsonschema.validate(result, schema)
    return result


def test_compiled_folder_publishes_and_replays(worker):
    output = worker.execute()
    assert worker.execute() == output
    assert len(worker.calls) == 1
    args, options = worker.calls[0]
    assert args[0] == "ocr" and args[2] == "/ocr"
    assert options["num_retries"] == 0
    assert options["model_spec"]["protocol"] == "http_json"
    report = batch(worker)
    assert report["status"] == "completed" and report["completed_count"] == 1
    record = report["files"][0]
    assert record["source"] == "source.png" and record["page_count"] == 1
    assert (
        worker.store.read_path("documents/source.png/ocr_result.json")
        == worker.responses[0]
    )
    assert (
        worker.store.path("documents/source.png/text.txt").read_text()
        == "Synthetic source text\n"
    )
    assert (
        "## Page 1"
        in worker.store.path("documents/source.png/document.md").read_text()
    )
    assert "Synthetic source text" not in json.dumps(output.outputs)
    assert len(json.dumps(output.outputs)) < 4096


def test_recursive_images_pdf_office_and_explicit_exclusions(worker, monkeypatch):
    nested = worker.folder / "reports" / "quarter 1"
    nested.mkdir(parents=True)
    (nested / "source.PNG").write_bytes((worker.folder / "source.png").read_bytes())
    (nested / "pages.PDF").write_bytes(pdf_bytes(2))
    (nested / "notes.md").write_text("Unsupported file is accounted for")
    rendered = pdf_bytes()
    converted = []

    def render(source, **options):
        converted.append(source.suffix)
        assert source.read_bytes() == b"synthetic Office source"
        return rendered

    monkeypatch.setattr("domain.documents.render_office", render)
    for suffix in (".docx", ".pptx", ".xlsx"):
        (nested / ("office" + suffix)).write_bytes(b"synthetic Office source")
    worker.execute()
    report = batch(worker)
    assert report["file_count"] == report["completed_count"] == 6
    assert len(worker.calls) == 6
    assert sorted(converted) == [".docx", ".pptx", ".xlsx"]
    assert report["skipped"] == [
        {"source": "reports/quarter 1/notes.md", "reason": "unsupported_format"}
    ]
    assert [item["source"] for item in report["files"]] == sorted(
        item["source"] for item in report["files"]
    )
    for item in report["files"]:
        if Path(item["source"]).suffix in {".docx", ".pptx", ".xlsx"}:
            assert item["input_sha256"] == hashlib.sha256(rendered).hexdigest()
            assert (
                item["source_sha256"]
                == hashlib.sha256(b"synthetic Office source").hexdigest()
            )
        assert worker.store.path(
            "documents/" + item["source"] + "/text.txt"
        ).is_file()
    assert (
        next(item for item in report["files"] if item["source"].endswith("pages.PDF"))[
            "page_count"
        ]
        == 2
    )


@pytest.mark.parametrize(
    "changes", [{"input_sha256": "a" * 64}, {"merge_level": "word"}]
)
def test_invalid_model_response_never_publishes_or_repeats_inference(worker, changes):
    worker.changes.update(changes)
    for _ in range(2):
        with pytest.raises(ValueError):
            worker.execute()
    assert not worker.store.path("ocr_result.json").exists()
    assert len(worker.calls) == 1


def test_corrupt_supported_file_is_reported_and_valid_files_continue(worker):
    (worker.folder / "broken.pdf").write_bytes(b"%PDF-corrupt")
    worker.execute()
    report = batch(worker)
    assert report["status"] == "partial"
    assert report["failed_count"] == report["completed_count"] == 1
    assert report["files"][0]["status"] == "failed"
    assert len(worker.calls) == 1


def test_output_directories_do_not_collide_with_source_subfolders(worker):
    nested = worker.folder / "source.png.ocr" / "text.txt"
    nested.mkdir(parents=True)
    (nested / "source.png").write_bytes((worker.folder / "source.png").read_bytes())
    worker.execute()
    assert batch(worker)["completed_count"] == 2
    assert worker.store.path("documents/source.png/text.txt").is_file()
    assert worker.store.path("documents/source.png.ocr/text.txt/source.png/text.txt").is_file()


def test_no_valid_documents_reports_failure_without_model_use(worker):
    (worker.folder / "source.png").write_bytes(b"invalid")
    with pytest.raises(ValueError, match="No documents could be read"):
        worker.execute()
    assert batch(worker)["status"] == "failed"
    assert not worker.calls


def test_empty_or_unsupported_folder_never_dispatches(worker):
    (worker.folder / "source.png").unlink()
    (worker.folder / "notes.txt").write_text("No supported source")
    with pytest.raises(ValueError, match="no supported documents"):
        worker.execute()
    assert not worker.calls


def test_conversion_failure_is_reported_per_file(worker, monkeypatch):
    from domain.office import DocumentInputError

    (worker.folder / "damaged.docx").write_bytes(b"bad Office source")

    def invalid(*args, **kwargs):
        raise DocumentInputError("Office document could not be rendered to PDF")

    monkeypatch.setattr("domain.documents.render_office", invalid)
    worker.execute()
    assert batch(worker)["failed_count"] == 1
    assert len(worker.calls) == 1


def test_publication_recovers_from_captured_sources_without_another_model_call(
    worker, monkeypatch
):
    original = CommittedJsonStore.commit_bytes

    def interrupted(store, path, content, **options):
        if str(path).endswith("source.png/document.md"):
            raise OSError("publication interruption")
        return original(store, path, content, **options)

    with monkeypatch.context() as patch:
        patch.setattr(CommittedJsonStore, "commit_bytes", interrupted)
        with pytest.raises(OSError):
            worker.execute()
    (worker.folder / "source.png").write_bytes(b"changed after capture")
    (worker.folder / "added.png").write_bytes(b"not in captured inventory")
    worker.execute()
    assert len(worker.calls) == 1
    assert batch(worker)["file_count"] == 1


def test_page_and_multiframe_limits_are_input_failures(worker):
    (worker.folder / "too-long.pdf").write_bytes(pdf_bytes(51))
    frames = [Image.new("RGB", (5, 5), color) for color in ("white", "black")]
    frames[0].save(
        worker.folder / "animation.tiff", save_all=True, append_images=frames[1:]
    )
    worker.execute()
    assert batch(worker)["failed_count"] == 2
    assert len(worker.calls) == 1


def test_source_byte_limit_never_dispatches(worker, monkeypatch):
    import domain.documents as documents

    monkeypatch.setattr(documents, "MAX_INPUT_BYTES", 16)
    with pytest.raises(ValueError, match="byte limit"):
        worker.execute()
    assert not worker.calls


def test_requires_nvidia_48_gib_and_original_newspaper_sample():
    execution = json.loads((ROOT / "execution.json").read_text())
    gpu = execution["requirements"]["gpu"]
    assert gpu["min_memory_mb"] == 49152 and gpu["vendor"] == "nvidia"
    assert gpu["enforcement"] == "hard"
    config = json.loads((ROOT / "config/default.json").read_text())
    guide = json.loads((ROOT / "extensions/ui.json").read_text())["setup_guide"]
    sample = config["inputs"]["payload"]["input_folder"]
    assert sample == guide["sample"]["values"]["inputs.payload.input_folder"]
    data = (ROOT / sample.removeprefix("@/") / "stock_gs200.jpg").read_bytes()
    assert hashlib.sha256(data).hexdigest() == SAMPLE_HASH
    with Image.open(io.BytesIO(data)) as image:
        assert image.format == "JPEG" and image.size == (626, 580)


def test_newspaper_jpeg_dispatch(worker):
    (worker.folder / "source.png").unlink()
    data = (ROOT / "examples/sample_inputs/stock_gs200.jpg").read_bytes()
    (worker.folder / "stock_gs200.jpg").write_bytes(data)
    worker.execute()
    assert worker.calls[0][0][3]["suffix"] == ".jpg"
    assert batch(worker)["files"][0]["source_sha256"] == SAMPLE_HASH


def test_local_staging_preserves_all_formats_and_subfolders(tmp_path):
    from mn_sdk.blueprint_support.local_inputs import stage_local_input_payloads

    nested = tmp_path / "sources/nested/deep"
    nested.mkdir(parents=True)
    suffixes = [".JPG", ".pdf", ".doc", ".docx", ".pptx", ".xlsx", ".unknown"]
    for suffix in suffixes:
        (nested / ("same" + suffix)).write_bytes(b"fixture for staging")
    config = json.loads((ROOT / "config/default.json").read_text())
    config["inputs"]["payload"]["input_folder"] = str(tmp_path / "sources")
    payloads = {}
    report = stage_local_input_payloads(config, payloads, bundle_dir=ROOT)
    assert report["folders"][0]["file_count"] == len(suffixes)
    assert all(
        any(name.endswith("nested/deep/same" + suffix) for name in payloads)
        for suffix in suffixes
    )


def test_live_speed_counts_completed_pages_without_source_content(worker, monkeypatch):
    events = []
    monkeypatch.setattr("mn_sdk.processing_progress.emit_agent_event", lambda kind, payload: events.append(payload))
    (worker.folder / "two-pages.pdf").write_bytes(pdf_bytes(2))
    (worker.folder / "invalid.pdf").write_bytes(b"%PDF-corrupt")
    worker.execute()
    readings = [event["processing"] for event in events]
    assert [item["completed"] for item in readings] == [0, 1, 3, 3]
    assert [item["status"] for item in readings] == ["running"] * 3 + ["completed"]
    assert all(item["unit"] == "page" and item["total"] is None for item in readings)
    assert readings[-1]["elapsed_seconds"] > 0
    assert all(event["step_id"] == "extract_folder_text" for event in events)
    assert all(event["agent_id"] for event in events)
    assert not any(secret in json.dumps(events) for secret in ("Synthetic source text", "source.png", "two-pages.pdf"))
