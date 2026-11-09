"""The blueprint-owned image enables real timestamp capture without a GPU test."""

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace


def test_serving_entrypoint_enables_the_pinned_models_timestamp_middleware(monkeypatch):
    path = Path(__file__).parents[1] / "payloads/model/serve.py"
    spec = importlib.util.spec_from_file_location("transcribe_serving_test", path)
    serving = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(serving)
    downloads, commands = [], []
    monkeypatch.setitem(
        sys.modules,
        "torch",
        SimpleNamespace(
            cuda=SimpleNamespace(
                is_available=lambda: True, get_device_capability=lambda: (10, 0)
            )
        ),
    )

    def download(**kwargs):
        downloads.append(kwargs)
        return "/cache/pinned-model"

    monkeypatch.setitem(
        sys.modules, "huggingface_hub", SimpleNamespace(snapshot_download=download)
    )
    monkeypatch.setattr(
        serving.os,
        "execv",
        lambda executable, command: commands.append((executable, command)),
    )
    serving.main()
    assert downloads[0]["revision"] == "66c6adc4020179567074d0399cda2a4eeb2bb347"
    assert downloads[0]["repo_id"].endswith("-NVFP4")
    command = commands[0][1]
    assert "--trust-request-mm-kwargs" in command
    assert (
        command[command.index("--middleware") + 1]
        == "nemo.collections.speechlm2.vllm.salm.ctc_serving.ctc_timestamp_middleware"
    )
    assert command[command.index("--served-model-name") + 1] == downloads[0]["repo_id"]
