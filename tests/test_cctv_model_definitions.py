"""Real CCTV dependency staging, without Docker, downloads or live inference."""

from pathlib import Path

import pytest

from mn_sdk.blueprints import blueprint_definition, read_blueprint
from mn_sdk.components.installation import SDKInstallation
from mn_sdk.submission_preparation import (
    manifest_nodes,
    prepare_manifest_for_submission,
    stage_skill_dependency_payloads_for_manifest,
    stage_upload_path_payloads_for_manifest,
)
from mn_sdk.model_catalog import load_builtin_model_catalog_document

ROOT = Path(__file__).resolve().parents[1] / "cctv_operator"


@pytest.mark.parametrize("local", [True, False], ids=["source", "package"])
def test_cctv_build_installs_declared_dependencies_before_model_preparation(monkeypatch, local):
    from mn_sdk import submission_preparation
    from mn_sdk.components import installation

    monkeypatch.setenv("MN_USE_LOCAL_SKILLS", "1" if local else "0")
    monkeypatch.setattr(installation, "sdk_installation", lambda: (
        SDKInstallation("local", source_root=Path(submission_preparation.__file__).resolve().parents[1])
        if local else SDKInstallation("wheel")))
    monkeypatch.setattr(submission_preparation, "ensure_runtime_modules_for_manifest", lambda *a, **k: {})
    prepared = prepare_manifest_for_submission(ROOT, blueprint_definition(read_blueprint(ROOT)))
    from mn_sdk import iter_bundle_assets

    payloads = {asset.logical_path: asset.path.read_bytes() for asset in iter_bundle_assets(ROOT)}
    stage_upload_path_payloads_for_manifest(prepared, payloads, bundle_dir=ROOT)
    stage_skill_dependency_payloads_for_manifest(prepared, payloads, bundle_dir=ROOT)
    dockerfile = payloads["docker_worker/Dockerfile"].decode()
    requirements = payloads["requirements.txt"].decode()
    assert "FROM nvcr.io/nvidia/pytorch:25.11-py3@sha256:" in dockerfile
    assert dockerfile.index("pip install") < dockerfile.index("person_detector.py --prepare")
    assert "rfdetr==1.11.2" in requirements
    assert "[mobileclip]" not in requirements
    assert payloads["domain/person_detector.py"] == (ROOT / "payloads/domain/person_detector.py").read_bytes()
    node = next(n for n in manifest_nodes(prepared) if n.get("node_id") == "visual_detector")
    assert node["config"]["build_context"] == "."
    assert node["config"]["dockerfile"] == "docker_worker/Dockerfile"
    assert "COPY domain/person_detector.py" in dockerfile
    if local:
        assert dockerfile.index("COPY __mn_skill_dependencies/local/") < dockerfile.index("pip install")
        assert dockerfile.index("COPY local-requirements.txt") < dockerfile.index("pip install")


def test_cosmos_recipe_belongs_to_the_blueprint_and_is_not_built_in():
    models = blueprint_definition(read_blueprint(ROOT))["runtime"]["models"]
    spec = models["vision"]["model_spec"]
    assert spec["id"] not in load_builtin_model_catalog_document().models
    assert spec["input_modalities"] == ["text", "image", "video"]
    assert models["vision"]["customize_mode"] is True
    assert "NGC_API_KEY" not in spec["docker"]["environment"]


def test_restart_recipe_selects_pinned_edge_without_a_nano_alias():
    from mn_sdk.blueprints import resolve_config

    package = read_blueprint(ROOT)
    definition = blueprint_definition(package)
    vision = definition["runtime"]["models"]["vision"]
    spec = vision["model_spec"]
    docker = spec["docker"]
    config = resolve_config(package).data
    assert vision["model"] == config["llm"]["configs"]["vision"]["model"] == "cosmos3-edge:bf16"
    assert vision["backend"] == config["llm"]["configs"]["vision"]["backend"] == "vllm"
    assert spec["api_model"] == "nvidia/Cosmos3-Edge"
    assert docker["image"] == "vllm/vllm-openai@sha256:db0bb920b0b54e82ea96a98659bbd21921f87d0dcfc86feffdafa2db3f08be55"
    assert docker["arguments"][docker["arguments"].index("--revision") + 1] == "344d602b128d1bbdacb43b08d0a3626f46343e29"
    assert all("nano" not in alias.lower() for alias in spec["aliases"] + spec["route_aliases"])
    assert docker["ready_path"] == "/health"
    assert int(docker["arguments"][docker["arguments"].index("--kv-cache-memory-bytes") + 1]) == 4 * 1024**3
    assert int(docker["arguments"][docker["arguments"].index("--max-model-len") + 1]) == 32768
    assert spec["requirements"]["min_vram_gb"] >= 16


def test_cosmos_budget_leaves_capacity_for_conversation_and_matches_caption_lane():
    from mn_sdk.blueprints import resolve_config

    package = read_blueprint(ROOT)
    arguments = blueprint_definition(package)["runtime"]["models"]["vision"][
        "model_spec"
    ]["docker"]["arguments"]
    config = resolve_config(package).data
    assert float(arguments[arguments.index("--gpu-memory-utilization") + 1]) <= 0.5
    assert int(arguments[arguments.index("--max-num-seqs") + 1]) == config["backpressure"][
        "llm"
    ]["max_concurrent_calls"]


@pytest.mark.parametrize("timeout", [None, 450], ids=["default", "operator-override"])
def test_caption_deadline_reaches_the_compiled_detector(monkeypatch, timeout):
    from mn_sdk import submission_preparation

    monkeypatch.setattr(submission_preparation, "ensure_runtime_modules_for_manifest", lambda *a, **k: {})
    overrides = {"llm": {"configs": {"vision": {"timeout_seconds": timeout}}}} if timeout else None
    prepared = prepare_manifest_for_submission(
        ROOT, blueprint_definition(read_blueprint(ROOT)), config_overrides=overrides,
    )
    detector = next(node for node in manifest_nodes(prepared) if node.get("node_id") == "visual_detector")
    assert detector["config"]["environment"]["MN_VLM_TIMEOUT_SECONDS"] == str(timeout or 300)
