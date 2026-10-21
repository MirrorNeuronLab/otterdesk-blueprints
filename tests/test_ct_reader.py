"""Deterministic CT blueprint tests; no GPU, network or patient data."""

import base64
import json
import sys
from pathlib import Path

import pytest
from mn_sdk.blueprints import blueprint_definition, compile_blueprint, read_blueprint
from mn_sdk.blueprints.definition import catalog_record
from mn_sdk.model_access.custom import resolve_requirement_entry

ROOT = Path(__file__).resolve().parents[1] / "ct_reader"


def test_blueprint_compiles_with_strict_nvidia_48_gib_and_special_docker_model():
    package = read_blueprint(ROOT)
    source = blueprint_definition(package)
    compiled = compile_blueprint(package).manifest
    gpu = source["requirements"]["gpu"]
    assert gpu == {
        "min_count": 1,
        "vendor": "nvidia",
        "driver": "cuda",
        "min_memory_mb": 49152,
        "memory_operator": ">=",
        "enforcement": "required",
    }
    model = source["runtime"]["models"]["ct"]
    assert model["customize_mode"] is True
    assert model["model_spec"]["requirements"]["min_vram_gb"] == 48
    import re

    assert re.fullmatch(
        r"docker\.io/homerquan/nv-reason-ct@sha256:[a-f0-9]{64}",
        model["model_spec"]["docker"]["image"],
    )
    assert model["model_spec"]["source"] == "docker"
    assert compiled["agents"]["nodes"]
    # Validate with the existing special model resolver, with no SDK catalog entry.
    resolved = resolve_requirement_entry(
        {
            "model": model["model"],
            "manifest_config": model,
            "backend": "docker",
            "customize_mode": True,
        },
        catalog={},
        catalog_resolver=lambda *args, **kwargs: (_ for _ in ()).throw(KeyError()),
    )
    assert resolved["cataloged"] is False
    assert resolved["customize_mode"] is True


def test_chat_requests_upload_and_safety_copy_is_present_in_product_surfaces():
    package = read_blueprint(ROOT)
    entry = catalog_record(package, "ct_reader")
    assert "conversation_file_upload:nifti" in entry["capabilities"]
    assert "conversation_result_text:report.md" in entry["capabilities"]
    assert entry["setup_guide"]["sample"]["available"] is False
    assert "upload" in entry["setup_guide"]["introduction"].lower()
    assert "not for real diagnosis" in entry["description"].lower()
    file_field = entry["setup_guide"]["fields"][0]
    assert file_field["path"] == "inputs.payload.ct_file"
    assert file_field["path_kind"] == "file" and file_field["role"] == "input"
    for name in ["README.md", "SPEC.md", "TERM.md", "knowledge/conversation_guide.md"]:
        assert "not for real diagnosis" in (ROOT / name).read_text().lower()


def test_first_run_uses_managed_model_preparation_without_a_preexisting_service(
    tmp_path,
):
    from mn_sdk.blueprint_runtime import blueprint_runtime_environment
    from mn_sdk.model_runtime import expand_manifest_model_service_requirements

    package = read_blueprint(ROOT)
    manifest = compile_blueprint(package).manifest
    config = json.loads((ROOT / "config/default.json").read_text())
    environment = blueprint_runtime_environment(
        ROOT,
        config=config,
        runtime_env={},
        include_docker_worker_runtime_env=True,
        env={"MN_HOME": str(tmp_path)},
    )
    assert environment["MN_RUNTIME_MODEL_MANAGED"] == "1"
    expand_manifest_model_service_requirements(manifest, config, env=environment)
    for node in manifest["agents"]["nodes"]:
        assert not node.get("requires_services")
        assert not node.get("placement_requirements", {}).get("models")


def test_domain_stays_outside_steps_and_runtime():
    for directory in ("steps", "runtime"):
        for file in (ROOT / "payloads" / directory).glob("*.py"):
            assert "from domain" not in file.read_text()
    assert not (ROOT / "payloads/agents/domain.py").exists()


@pytest.fixture
def model_server(monkeypatch):
    import importlib.util
    import struct

    sys.path.insert(0, str(ROOT / "payloads/model"))
    spec = importlib.util.spec_from_file_location(
        "ct_blueprint_model_server", ROOT / "payloads/model/server.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    data = bytearray(368)
    struct.pack_into("<i", data, 0, 348)
    struct.pack_into("<4h", data, 40, 3, 2, 2, 2)
    struct.pack_into("<2h", data, 70, 4, 16)
    struct.pack_into("<f", data, 108, 352)
    data[344:348] = b"n+1\0"
    return module, bytes(data)


def test_model_api_decodes_gzip_and_rejects_bombs_and_malformed_headers(
    model_server, monkeypatch
):
    import gzip

    server, data = model_server
    assert server.decode_volume(base64.b64encode(gzip.compress(data)).decode()) == data
    for invalid in (b"fake", data[:352], data[:344] + b"ni1\0" + data[348:]):
        with pytest.raises(ValueError):
            server.decode_volume(base64.b64encode(invalid).decode())
    monkeypatch.setattr(server, "MAX_EXPANDED", 512)
    with pytest.raises(ValueError):
        server.decode_volume(base64.b64encode(gzip.compress(b"0" * 513)).decode())


def test_docker_api_accepts_only_volume_bytes_and_bounded_research_inputs(
    model_server, monkeypatch
):
    from fastapi.testclient import TestClient

    server, data = model_server
    calls = []
    monkeypatch.setattr(
        server,
        "infer",
        lambda volume, region, prompt: (
            calls.append((volume, region, prompt))
            or {
                "answer": "Synthetic output",
                "research_only": True,
                "model_revision": "pinned",
            }
        ),
    )
    client = TestClient(server.app)
    response = client.post(
        "/v1/ct",
        json={
            "volume_base64": base64.b64encode(data).decode(),
            "region": "chest",
            "prompt": "Research report",
        },
    )
    assert response.status_code == 200 and response.json()["research_only"] is True
    assert calls == [(data, "chest", "Research report")]
    for body in (
        {"ct_path": "/etc/passwd", "region": "chest", "prompt": "Read"},
        {"messages": []},
        {"messages": [{"role": "user", "content": []}]},
    ):
        assert client.post("/v1/ct", json=body).status_code == 400
    assert client.get("/health").status_code == 503
    assert client.get("/v1/models").json()["data"][0]["id"] == "nvidia/NV-Reason-CT"


def test_native_block_compiles_without_local_wrappers():
    package = read_blueprint(ROOT)
    manifest = compile_blueprint(package).manifest
    assert package.manifest["version"] == "3.0.0"
    assert (
        package.extension("mn.blocks")["steps"]["read_ct_volume"]["uses"]
        == "mn.blocks.native_computation@1"
    )
    assert (
        manifest["metadata"]["mn_blocks_lock"]["steps"]["read_ct_volume"]["limits"][
            "max_calls"
        ]
        == 1
    )
    assert not package.extension("mn.blocks")["steps"]["read_ct_volume"].get("adapters")
    assert not (ROOT / "payloads/agents/ct_research_specialist.py").exists()
    assert not (ROOT / "payloads/steps/read_ct_volume.py").exists()
    assert not (ROOT / "payloads/runtime/runtime.py").exists()
