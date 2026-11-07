"""Compiled worker, complete chunk coverage, replay and failure tests."""

import io
import json
import shutil
import subprocess
import sys
import wave
from pathlib import Path
from types import SimpleNamespace

import pytest
from mn_sdk.blueprints import compile_blueprint, read_blueprint, resolve_config
from mn_sdk.blueprints.worker_descriptors import resolved_worker_descriptor
from mn_sdk.integrations.block_worker import run
from mn_sdk.step_runtime import StepContext
from mn_sdk_common.committed_artifacts import CommittedJsonStore

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
    folder = tmp_path / "audio"
    folder.mkdir()
    output = io.BytesIO()
    with wave.open(output, "wb") as handle:
        handle.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
        handle.writeframes(b"\0\0" * 36000)
    (folder / "sample.wav").write_bytes(output.getvalue())
    calls = []

    def request(*args, **options):
        calls.append((args, options))
        return {
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {
                        "role": "assistant",
                        "content": "Synthetic transcript " + str(len(calls)),
                    },
                }
            ]
        }

    monkeypatch.setattr(
        "mn_sdk.integrations.block_model_request.runtime_model_json_request", request
    )
    inputs = {"input_folder": str(folder), "chunk_seconds": 1}

    def execute():
        return run(
            StepContext(
                step_id="transcribe_audio_folder",
                agent_id=node["node_id"],
                run_id="audio-test",
                idempotency_key="audio-test/transcribe",
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
        folder=folder,
        inputs=inputs,
    )


def test_complete_markdown_transcripts_and_replay(worker):
    first = worker.execute()
    assert worker.execute() == first
    assert len(worker.calls) == 3
    saved = worker.store.read_path("transcription_result.json")
    record = saved["files"][0]
    assert record["duration_seconds"] == 2.25
    assert [(p["start_seconds"], p["end_seconds"]) for p in record["chunks"]] == [
        (0, 1),
        (1, 2),
        (2, 2.25),
    ]
    text = worker.store.path("transcripts/sample.wav.md").read_text()
    assert all("Synthetic transcript " + str(n) in text for n in (1, 2, 3))
    assert "00:00:02.250" in text
    args, options = worker.calls[0]
    assert args[2] == "/chat/completions"
    assert args[3]["messages"][0]["content"][1]["audio_url"]["url"].startswith(
        "data:audio/wav;base64,"
    )
    assert options["num_retries"] == 0
    assert options["model_spec"]["docker"]["cache_path"] == "/cache"
    assert "Synthetic transcript" not in json.dumps(first.outputs)


def test_publication_failure_recovers_without_repeating_audio_inference(worker, monkeypatch):
    import domain.transcription as domain

    with monkeypatch.context() as patch:
        patch.setattr(
            domain,
            "publish_artifact_bundle",
            lambda *a, **k: (_ for _ in ()).throw(OSError("interrupted delivery")),
        )
        with pytest.raises(OSError):
            worker.execute()
    (worker.folder / "sample.wav").write_bytes(b"changed source after durable capture")
    worker.execute()
    assert len(worker.calls) == 3
    assert worker.store.path("transcription_result.json").exists()


def test_truncated_completion_never_publishes_complete_batch(worker, monkeypatch):
    def request(*args, **options):
        worker.calls.append(args)
        return {"choices": [{"finish_reason": "length", "message": {"content": "Partial words"}}]}

    monkeypatch.setattr(
        "mn_sdk.integrations.block_model_request.runtime_model_json_request", request
    )
    for _ in range(2):
        with pytest.raises(ValueError, match="truncated"):
            worker.execute()
    assert len(worker.calls) == 1
    assert not worker.store.path("transcription_result.json").exists()


def test_empty_folder_never_prepares_model(worker):
    (worker.folder / "sample.wav").unlink()
    with pytest.raises(ValueError, match="no supported"):
        worker.execute()
    assert not worker.calls


def test_sample_is_complete_original_recording():
    metadata = json.loads((ROOT / "examples/sample_source.json").read_text())
    path = ROOT / "examples/sample_inputs/Bdb001.interaction.wav"
    if not path.exists():
        pytest.skip("Binary sample is staged immediately after Synapsy creation")
    import hashlib

    assert hashlib.sha256(path.read_bytes()).hexdigest() == metadata["sha256"]
    with wave.open(str(path)) as audio:
        assert audio.getnframes() / audio.getframerate() == metadata["duration_seconds"]


def test_declared_local_staging_preserves_audio_files(tmp_path):
    from mn_sdk.blueprint_support.local_inputs import stage_local_input_payloads

    folder = tmp_path / "staged-audio"
    folder.mkdir()
    (folder / "recording.wav").write_bytes(b"fake-wav-for-staging")
    (folder / "recording.mp3").write_bytes(b"fake-mp3-for-staging")
    nested = folder / "interviews" / "day-1"
    nested.mkdir(parents=True)
    (nested / "recording.WAV").write_bytes(b"fake-nested-wav-for-staging")
    (nested / "recording.MP3").write_bytes(b"fake-nested-mp3-for-staging")
    (folder / "notes.md").write_text("not an audio input")
    config = json.loads((ROOT / "config/default.json").read_text())
    config["inputs"]["payload"]["input_folder"] = str(folder)
    payloads = {}
    report = stage_local_input_payloads(config, payloads, bundle_dir=ROOT)
    assert report["folders"][0]["file_count"] == 4
    assert {Path(name).suffix.lower() for name in payloads} == {".wav", ".mp3"}
    assert any(name.endswith("interviews/day-1/recording.WAV") for name in payloads)
    assert any(name.endswith("interviews/day-1/recording.MP3") for name in payloads)


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="FFmpeg is required for MP3 decoding")
def test_nested_wav_and_mp3_finish_one_recording_before_the_next(worker, monkeypatch):
    nested = worker.folder / "interviews" / "day-1"
    nested.mkdir(parents=True)
    source = worker.folder / "sample.wav"
    (nested / "recording.WAV").write_bytes(source.read_bytes())
    mp3 = worker.folder / "interviews" / "recording.mp3"
    subprocess.run(
        [shutil.which("ffmpeg"), "-nostdin", "-loglevel", "error", "-i", str(source), str(mp3)],
        check=True,
        timeout=30,
    )
    expected = ["interviews/day-1/recording.WAV", "interviews/recording.mp3", "sample.wav"]

    def request(*args, **options):
        file_index = len(worker.calls) // 3
        # All chunks and the transcript for the preceding file must be saved
        # before inference starts on another file, even across subfolders.
        for previous in expected[:file_index]:
            assert worker.store.path("transcripts/" + previous + ".md").is_file()
        assert not worker.store.path("transcripts/" + expected[file_index] + ".md").exists()
        worker.calls.append((args, options))
        return {"choices": [{"finish_reason": "stop", "message": {"content": f"Chunk {len(worker.calls)}"}}]}

    monkeypatch.setattr("mn_sdk.integrations.block_model_request.runtime_model_json_request", request)
    result = worker.execute()
    report = worker.store.read_path("transcription_result.json")
    assert report["file_count"] == 3
    assert [record["source"] for record in report["files"]] == expected
    assert len(worker.calls) == 9
    for index, record in enumerate(report["files"]):
        assert record["duration_seconds"] == pytest.approx(2.25)
        assert record["chunks"][-1]["end_seconds"] == pytest.approx(2.25)
        text = worker.store.path("transcripts/" + record["source"] + ".md").read_text()
        assert all(f"Chunk {n}" in text for n in range(index * 3 + 1, index * 3 + 4))
    assert worker.execute() == result
    assert len(worker.calls) == 9
