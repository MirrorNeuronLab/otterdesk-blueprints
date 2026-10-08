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
from cctv_operator.payloads.domain.model_definitions import cosmos_model_spec

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
    spec = cosmos_model_spec()
    assert spec == models["vision"]["model_spec"]
    assert spec["id"] not in load_builtin_model_catalog_document().models
    assert spec["input_modalities"] == ["text", "image", "video"]
    assert models["vision"]["customize_mode"] is True
    assert "NGC_API_KEY" not in spec["docker"]["environment"]
