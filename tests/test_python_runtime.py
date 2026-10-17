"""Published and unpublished co-workers compile for the runtime Python minor."""
import json
from pathlib import Path

from mn_sdk.blueprints import compile_blueprint, read_blueprint, resolve_config
import pytest

ROOT = Path(__file__).resolve().parents[1]
BLUEPRINTS = [*json.loads((ROOT / "index.json").read_text()), "gtm_planner", "gtm_executor"]


@pytest.mark.parametrize("blueprint", BLUEPRINTS)
def test_compiled_python_commands_match_runtime(blueprint):
    package = read_blueprint(ROOT / blueprint)
    manifest = compile_blueprint(package, resolve_config(package)).manifest
    nodes = [*manifest.get("agents", {}).get("nodes", []),
             *manifest.get("flow", {}).get("nodes", [])]
    for node in nodes:
        command = node.get("config", {}).get("command", [])
        assert "python3.11" not in json.dumps(command), (blueprint, node.get("node_id"))


def test_blueprint_contributor_python_matches_runtime():
    assert (ROOT / ".python-version").read_text().strip() == "3.12"
