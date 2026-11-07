"""Offline compiled worker checks; the external CUDA request is injected."""

import io
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from mn_nvidia_ocr_skill.backend import NemotronOcrBackend
from mn_sdk.blueprints import compile_blueprint, read_blueprint, resolve_config
from mn_sdk.blueprints.worker_descriptors import resolved_worker_descriptor
from mn_sdk.integrations.block_worker import run
from mn_sdk.step_runtime import StepContext
from mn_sdk_common.committed_artifacts import CommittedJsonStore
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]


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
    descriptor.write_text(json.dumps(resolved_worker_descriptor(package, compiled, config)))
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
    image = io.BytesIO()
    Image.new("RGB", (80, 30), "white").save(image, format="PNG")
    path = tmp_path / "source.png"
    path.write_bytes(image.getvalue())
    inputs = {"document_file": str(path), "merge_level": "paragraph"}
    saved = NemotronOcrBackend(
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
    ).extract(image.getvalue(), suffix=".png")
    calls = []

    def request(*args, **options):
        calls.append((args, options))
        return saved

    monkeypatch.setattr("mn_sdk.integrations.block_native.runtime_model_json_request", request)

    def execute(selected=None):
        return run(
            StepContext(
                step_id="extract_document_text",
                agent_id=node["node_id"],
                run_id="ocr-test",
                idempotency_key="ocr-test/extract",
                config=config.data,
                environment=environment,
                message={"body": {"step_input": inputs if selected is None else selected}},
            ),
            **parameters,
        )

    return SimpleNamespace(
        execute=execute,
        calls=calls,
        store=CommittedJsonStore(tmp_path / "run"),
        saved=saved,
        inputs=inputs,
    )


def test_compiled_ocr_publishes_and_replays(worker):
    output = worker.execute()
    assert worker.execute() == output
    assert len(worker.calls) == 1
    args, options = worker.calls[0]
    assert args[0] == "inference" and args[2] == "/ocr"
    assert options["num_retries"] == 0
    assert options["model_spec"]["protocol"] == "http_json"
    assert worker.store.read_path("ocr_result.json") == worker.saved
    assert worker.store.path("text.txt").read_text() == "Synthetic source text\n"
    assert "## Page 1" in worker.store.path("document.md").read_text()
    assert "Synthetic source text" not in json.dumps(output.outputs)
    assert len(json.dumps(output.outputs)) < 4096


def test_source_mismatch_does_not_publish(worker):
    worker.saved["input_sha256"] = "a" * 64
    with pytest.raises(ValueError, match="source"):
        worker.execute()
    assert not worker.store.path("ocr_result.json").exists()
    assert len(worker.calls) == 1


def test_invalid_document_never_dispatches(worker):
    Path(worker.inputs["document_file"]).write_bytes(b"invalid")
    with pytest.raises(ValueError):
        worker.execute()
    assert not worker.calls


def test_publication_recovers_without_another_model_call(worker, monkeypatch):
    original = CommittedJsonStore.commit_bytes

    def interrupted(store, path, content, **options):
        if str(path) == "document.md":
            raise OSError("publication interruption")
        return original(store, path, content, **options)

    with monkeypatch.context() as patch:
        patch.setattr(CommittedJsonStore, "commit_bytes", interrupted)
        with pytest.raises(OSError):
            worker.execute()
    worker.execute()
    assert len(worker.calls) == 1
    assert worker.store.path("document.md").exists()


def test_requires_nvidia_48_gib_and_real_sample():
    execution = json.loads((ROOT / "execution.json").read_text())
    gpu = execution["requirements"]["gpu"]
    assert gpu["min_memory_mb"] == 49152 and gpu["vendor"] == "nvidia"
    assert gpu["enforcement"] == "hard"
    from pypdf import PdfReader

    assert (
        "Invoice total: 42.00 USD"
        in PdfReader(ROOT / "examples/sample.pdf").pages[0].extract_text()
    )
