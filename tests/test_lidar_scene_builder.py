"""Verify the authored package, staged sample and durable preview boundary."""

import base64
import hashlib
import importlib
import json
from pathlib import Path
import struct
import sys
from types import SimpleNamespace

import pytest
from mn_sdk.blueprints import compile_blueprint, read_blueprint, read_catalog, resolve_config
from mn_sdk.blueprint_support.local_inputs import stage_local_input_payloads

from block_workflow_fixture import run_sample

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "lidar_scene_builder"
SAMPLE = PACKAGE / "examples/sample_inputs/street-corner.ply"


@pytest.fixture
def domain(monkeypatch):
    monkeypatch.syspath_prepend(str(PACKAGE / "payloads"))
    for name in list(sys.modules):
        if name == "domain" or name.startswith("domain."):
            monkeypatch.delitem(sys.modules, name)
    yield importlib.import_module("domain.conversion")
    for name in list(sys.modules):
        if name == "domain" or name.startswith("domain."):
            sys.modules.pop(name)


def test_catalog_admission_and_sample():
    entry = next(item for item in read_catalog(ROOT / "index.json") if item["id"] == PACKAGE.name)
    compiled = compile_blueprint(read_blueprint(PACKAGE)).manifest
    assert entry["setup_guide"]["sample"]["values"]["inputs.payload.scan_file"] == (
        "@/" + SAMPLE.relative_to(PACKAGE).as_posix()
    )
    assert entry["web_ui"]["adapter"] == "static_html"
    assert compiled["requirements"]["gpu"] == {
        "vendor": "nvidia", "driver": "cuda", "enforcement": "hard",
        "min_count": 1, "memory_operator": ">=", "min_memory_mb": 49152,
    }
    assert compiled["policies"]["constraints"] == [
        {"attribute": "cpu.arch", "operator": "in", "value": ["x86_64", "amd64"]},
    ]
    worker = next(node for node in compiled["agents"]["nodes"] if node["agent_type"] == "executor")
    assert worker["config"]["runner_module"] == "MirrorNeuron.Runner.DockerWorker"
    assert worker["config"]["gpus"] == "all"
    config = resolve_config(read_blueprint(PACKAGE)).data
    payloads = {}
    stage_local_input_payloads(config, payloads, bundle_dir=PACKAGE)
    assert payloads == {"mn_local_inputs/scan.ply": SAMPLE.read_bytes()}


@pytest.mark.parametrize("count", [0, 1_000_001, 10**20])
def test_bounded_header(domain, count, tmp_path):
    from domain.scan_io import ScanInputError, read_header

    with SAMPLE.open("rb") as stream:
        assert read_header(stream).count == 4191
    malformed = tmp_path / "malformed.ply"
    malformed.write_bytes(SAMPLE.read_bytes().replace(b"4191", str(count).encode(), 1))
    with malformed.open("rb") as stream, pytest.raises(ScanInputError):
        read_header(stream)


@pytest.mark.parametrize(("encoding", "order"), [
    ("binary_little_endian", "<"), ("binary_big_endian", ">"),
])
def test_binary_scan_preserves_rgb_and_registration(domain, tmp_path, encoding, order):
    from domain.scan_io import ScanInputError, read_scan

    path = tmp_path / "scan.ply"
    header = (
        f"ply\nformat {encoding} 1.0\nelement vertex 2\n"
        "property double x\nproperty double y\nproperty double z\n"
        "property uchar red\nproperty uchar green\nproperty uchar blue\nend_header\n"
    ).encode()
    body = struct.pack(order + "dddBBBdddBBB", 1e6, 0, 0, 255, 128, 0, 1e6 + 0.25, 0.125, 2, 20, 30, 40)
    path.write_bytes(header + body)
    points, colors, digest = read_scan(path)
    assert (points[1] - points[0]).tolist() == [0.25, 0.125, 2]
    assert colors[0].tolist() == pytest.approx([1, 128 / 255, 0])
    assert digest == hashlib.sha256(header + body).hexdigest()
    path.write_bytes(header + body[:-8])
    with pytest.raises(ScanInputError, match="binary PLY size"):
        read_scan(path)


@pytest.mark.parametrize("body", [b"0 1 2\n", b"0 nan 2\n1 2 3\n", b"0 bad 2\n1 2 3\n"])
def test_ascii_scan_rejects_invalid_rows(domain, tmp_path, body):
    from domain.scan_io import ScanInputError, read_scan

    path = tmp_path / "scan.ply"
    header = (
        b"ply\nformat ascii 1.0\nelement vertex 2\n"
        b"property float x\nproperty float y\nproperty float z\nend_header\n"
    )
    path.write_bytes(header + body)
    with pytest.raises(ScanInputError):
        read_scan(path)


def test_cuda_memory_requirement_applies_to_one_device(domain, monkeypatch):
    from domain.nurec_export import select_device
    from domain.scan_io import ScanInputError

    memory_gib = [24, 32]
    selected = []
    torch = SimpleNamespace(
        version=SimpleNamespace(cuda="12.8"),
        cuda=SimpleNamespace(
            is_available=lambda: True,
            device_count=lambda: len(memory_gib),
            get_device_properties=lambda index: SimpleNamespace(total_memory=memory_gib[index] * 1024**3),
            set_device=selected.append,
        ),
        device=lambda name, index: f"{name}:{index}",
    )
    monkeypatch.setitem(sys.modules, "torch", torch)
    with pytest.raises(ScanInputError, match="one NVIDIA GPU"):
        select_device(49152)
    memory_gib.append(48)
    assert select_device(49152) == "cuda:2"
    assert selected == ["cuda:2"]


@pytest.mark.parametrize("preview_fails", [False, True])
def test_compiled_sample_publishes_scene_before_preview(domain, monkeypatch, tmp_path, preview_fails):
    sample = SAMPLE.read_bytes()
    scene = b"test scene bytes"
    calls = []

    def execute(block, command, *paths):
        calls.append(command)
        if command == "export":
            source, destination, summary = paths
            assert source.name == "scan.ply"
            assert source.read_bytes() == sample
            destination.write_bytes(scene)
            summary.write_text(json.dumps({
                "point_count": 4191,
                "bounds_m": [[-6.9, -5.7, 0], [6.9, 6.14, 4.17]],
                "input_sha256": hashlib.sha256(sample).hexdigest(),
            }))
        else:
            saved, projection = paths
            assert saved.read_bytes() == scene
            assert block.store.path("scan_result.json").is_file()
            if preview_fails:
                raise OSError("preview failed")
            projection.write_text(json.dumps({
                "count": 1,
                "positions": base64.b64encode(struct.pack("<fff", 0, 0, 0)).decode(),
                "colors": base64.b64encode(b"\xff\x80\x40").decode(),
            }))

    monkeypatch.setattr(domain, "run_nurec", execute)
    monkeypatch.delenv("MN_JOB_OUTPUT_DIR", raising=False)
    # The offline fixture places staged payloads beside its runtime workdir.
    spec = resolve_config(read_blueprint(PACKAGE)).data["local_inputs"]["files"][0]
    config = {"local_inputs": {"files": [{**spec, "payload_path": "runtime/" + spec["payload_path"]}]}}
    options = dict(config=config, runs_root=tmp_path, run_id="fixture", through_step="convert_scan")
    result = run_sample(PACKAGE.name, **options)
    assert run_sample(PACKAGE.name, **options)["outputs"] == result["outputs"]
    assert calls == ["export", "project"]
    root = tmp_path / "fixture"
    report = json.loads((root / "scan_result.json").read_text())
    assert report["point_count"] == 4191
    assert report["scene"]["sha256"] == hashlib.sha256(scene).hexdigest()
    assert result["scene"]["path"] == "scene.usdc"
    assert (root / "scene.usdc").read_bytes() == scene
    if preview_fails:
        assert not (root / "web_ui.json").exists()
    else:
        page = (root / "web/index.html").read_bytes()
        handle = json.loads((root / "web_ui.json").read_text())
        assert handle["adapter"] == "static_html"
        assert handle["metadata"]["sha256"] == hashlib.sha256(page).hexdigest()
        assert b"1 of 4,191 points" in page
        assert b"Content-Security-Policy" in page
