"""Exercise the model image's bundled code without CUDA or network access."""

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def bundled_backend(monkeypatch):
    # The worker can use the installed skill, but the image must test its own copy.
    root = ROOT / "payloads/skills/nvidia_ocr_skill/src/mn_nvidia_ocr_skill"
    name = "blueprint_bundled_ocr"
    spec = importlib.util.spec_from_file_location(
        name, root / "__init__.py", submodule_search_locations=[str(root)]
    )
    package = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, package)
    spec.loader.exec_module(package)
    try:
        yield importlib.import_module(name + ".backend")
    finally:
        for key in list(sys.modules):
            if key.startswith(name + "."):
                sys.modules.pop(key)


@pytest.mark.parametrize("machine", ["x86_64", "amd64", "aarch64", "arm64"])
def test_model_loads_pinned_weights_on_supported_cuda_hosts(
    bundled_backend, monkeypatch, tmp_path, machine
):
    monkeypatch.setattr("platform.system", lambda: "Linux")
    monkeypatch.setattr("platform.machine", lambda: machine)
    monkeypatch.setitem(
        sys.modules,
        "torch",
        SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: True)),
    )
    downloads, loaded = [], []

    def download(**options):
        downloads.append(options)
        return str(tmp_path)

    monkeypatch.setitem(
        sys.modules, "huggingface_hub", SimpleNamespace(snapshot_download=download)
    )
    monkeypatch.setitem(sys.modules, "nemotron_ocr", SimpleNamespace())
    monkeypatch.setitem(sys.modules, "nemotron_ocr.inference", SimpleNamespace())
    monkeypatch.setitem(
        sys.modules,
        "nemotron_ocr.inference.pipeline_v2",
        SimpleNamespace(
            NemotronOCRV2=lambda **options: loaded.append(options) or "pipeline"
        ),
    )
    with pytest.raises(RuntimeError, match="incomplete"):
        bundled_backend.load_pipeline()
    assert not loaded
    weights = tmp_path / "v2_multilingual"
    weights.mkdir()
    for name in bundled_backend.CHECKPOINT_FILES:
        (weights / name).touch()
    assert bundled_backend.load_pipeline() == "pipeline"
    assert downloads[-1]["revision"] == bundled_backend.MODEL_REVISION
    assert downloads[-1]["allow_patterns"] == [
        f"v2_multilingual/{name}" for name in bundled_backend.CHECKPOINT_FILES
    ]
    assert loaded == [{"model_dir": str(weights), "detector_max_batch_size": 1}]


@pytest.mark.parametrize(
    "system,machine,cuda,error",
    [
        ("Darwin", "arm64", True, "Linux"),
        ("Linux", "riscv64", True, "Linux"),
        ("Linux", "aarch64", False, "NVIDIA CUDA"),
    ],
)
def test_unsupported_hosts_fail_before_downloading(
    bundled_backend, monkeypatch, system, machine, cuda, error
):
    monkeypatch.setattr("platform.system", lambda: system)
    monkeypatch.setattr("platform.machine", lambda: machine)
    monkeypatch.setitem(
        sys.modules,
        "torch",
        SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: cuda)),
    )
    monkeypatch.setitem(
        sys.modules,
        "huggingface_hub",
        SimpleNamespace(
            snapshot_download=lambda **_: pytest.fail("unexpected download")
        ),
    )
    with pytest.raises(RuntimeError, match=error):
        bundled_backend.load_pipeline()


def test_spark_extension_compiles_natively_and_reuses_arch_specific_cache(
    monkeypatch, tmp_path
):
    spec = importlib.util.spec_from_file_location(
        "ocr_startup", ROOT / "payloads/model/serve.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    root = tmp_path / "upstream"
    target = root / "src/nemotron_ocr_cpp"
    target.mkdir(parents=True)
    cache_root = tmp_path / "cache"
    monkeypatch.setattr(
        module, "Path", lambda path: root if path.startswith("/opt/") else cache_root
    )
    monkeypatch.setattr(module.sys, "path", list(sys.path))
    monkeypatch.setattr(module.platform, "machine", lambda: "aarch64")
    monkeypatch.setitem(
        sys.modules,
        "torch",
        SimpleNamespace(
            __version__="test",
            version=SimpleNamespace(cuda="13.0"),
            cuda=SimpleNamespace(
                is_available=lambda: True, get_device_capability=lambda: (12, 1)
            ),
        ),
    )
    calls = []

    def compile_extension(command, **options):
        calls.append((command, options))
        (target / "_nemotron_ocr_cpp.test.so").write_bytes(b"compiled fixture")

    monkeypatch.setattr(module.subprocess, "run", compile_extension)
    module.prepare_extension()
    assert calls[0][1]["env"]["ARCH"] == "aarch64"
    assert calls[0][1]["env"]["TORCH_CUDA_ARCH_LIST"] == "12.1"
    assert calls[0][1]["timeout"] == 1800
    (target / "_nemotron_ocr_cpp.test.so").unlink()
    module.prepare_extension()
    assert len(calls) == 1
    assert (target / "_nemotron_ocr_cpp.test.so").read_bytes() == b"compiled fixture"
    # An x86 build must never load the ARM64 shared library from the same cache.
    monkeypatch.setattr(module.platform, "machine", lambda: "x86_64")
    module.prepare_extension()
    assert len(calls) == 2
