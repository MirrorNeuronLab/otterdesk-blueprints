"""Catalog and non-catalog packages share the SDK input/configuration contract."""
import ast
import json
from pathlib import Path

import pytest
from mn_blueprint_blocks.context import BlockContext
from mn_sdk.blueprints import read_blueprint, resolve_config
from mn_sdk.integrations.block_inputs import capture_declared_inputs
from mn_sdk.local_input_paths import config_path_get
from mn_sdk_common.committed_artifacts import CommittedJsonStore

ROOT = Path(__file__).resolve().parents[1]
CATALOG = json.loads((ROOT / "index.json").read_text())
NON_CATALOG = ["gtm_planner", "gtm_executor"]


@pytest.mark.parametrize("blueprint_id", [*CATALOG, *NON_CATALOG])
def test_blueprint_defaults_use_common_input_resolution_and_storage(blueprint_id, tmp_path):
    root = ROOT / blueprint_id
    package = read_blueprint(root)
    config = resolve_config(package).data
    block = BlockContext(store=CommittedJsonStore(tmp_path / "run"), config=config,
        invocation_id="catalog-intake", revision="test", environment={
            "MN_BLUEPRINT_BUNDLE_DIR": str(root), "MN_WORKDIR": str(tmp_path / "worker")})
    selected = capture_declared_inputs(block, {}, runtime_file=root / "payloads/domain/intake.py")
    artifact = package.document("contracts").get("input_adapters", {}).get("resolved_artifact", "inputs.json")
    assert block.store.read_path(artifact) == selected
    assert capture_declared_inputs(block, {}, runtime_file=root / "payloads/domain/intake.py") == selected
    assert block.original_config == config
    for kind in ("folders", "files"):
        for spec in config.get("local_inputs", {}).get(kind, []):
            if spec.get("enabled") is False or any(config_path_get(config, key) != value for key, value in spec.get("when", {}).items()):
                continue
            for key in [spec["config_path"], *spec.get("linked_config_paths", [])]:
                key = key.removeprefix("inputs.payload.") if key.startswith("inputs.payload.") else None
                if key and selected.get(key):
                    assert Path(selected[key]).is_absolute(), (blueprint_id, key)
                    assert "@/" not in selected[key], (blueprint_id, key)


def test_blueprints_leave_generic_input_artifact_saving_to_sdk():
    for source in ROOT.glob("*/payloads/domain/*.py"):
        tree = ast.parse(source.read_text())
        for call in ast.walk(tree):
            if (isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)
                    and call.func.attr == "commit" and call.args
                    and isinstance(call.args[0], ast.Constant)):
                assert call.args[0].value != "inputs.json", source.relative_to(ROOT)


def test_blueprints_do_not_reimplement_common_runtime_paths():
    for source in ROOT.glob("*/payloads/domain/*.py"):
        tree = ast.parse(source.read_text())
        names = {node.name for node in tree.body if isinstance(node, ast.FunctionDef)}
        assert not names.intersection({"output_directory", "job_directory", "resolve_input_folder"}), source.relative_to(ROOT)


def test_blueprints_leave_generic_atomic_writes_to_sdk():
    for source in ROOT.glob("*/payloads/**/*.py"):
        tree = ast.parse(source.read_text())
        names = {node.name for node in tree.body if isinstance(node, ast.FunctionDef)}
        assert not names.intersection({"atomic_json", "_write_json", "json_dump", "text_dump"}), source.relative_to(ROOT)
