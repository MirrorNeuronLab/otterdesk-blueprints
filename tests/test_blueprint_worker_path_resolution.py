from __future__ import annotations

from pathlib import Path
import json

from blueprint_modernization_support import expanded_manifest, run_payload_script
from mn_sdk.blueprints import blueprint_definition, read_blueprint, resolve_config

ROOT = Path(__file__).resolve().parents[1]


def test_procurement_runner_uses_embedded_config_when_default_file_is_not_mounted(tmp_path):
    blueprint = ROOT / "procurement_manager"
    manifest = blueprint_definition(read_blueprint(blueprint / "manifest.json"))
    config = resolve_config(read_blueprint(blueprint)).data
    assert manifest["config"]["embed"] is True
    assert "llm" in manifest["config"]["data"]
    assert config["inputs"]["payload"]["input_folder"] == "@/examples/edge_ai_workstation"
    compiled = expanded_manifest("procurement_manager")
    embedded = next(
        node["config"]["environment"]["MN_BLUEPRINT_CONFIG_JSON"]
        for node in compiled["agents"]["nodes"]
        if node.get("config", {}).get("environment", {}).get("MN_BLUEPRINT_CONFIG_JSON")
    )
    result = run_payload_script("procurement_manager", f"""
import json
import os
import shutil
import sys
from pathlib import Path

worker = Path({str(tmp_path)!r})
shutil.copytree(Path({str(blueprint)!r}) / 'payloads', worker / 'payloads')
(worker / 'manifest.json').write_text({json.dumps(manifest)!r})
assert not (worker / 'config' / 'default.json').exists()
os.environ['MN_BLUEPRINT_CONFIG_JSON'] = {embedded!r}
os.environ['MN_BLUEPRINT_MANIFEST_PATH'] = str(worker / 'manifest.json')
os.environ.pop('MN_BLUEPRINT_CONFIG_PATH', None)
os.environ.pop('MN_BLUEPRINT_BUNDLE_DIR', None)
os.environ.pop('MN_BUNDLE_ROOT', None)
sys.path.insert(0, str(worker / 'payloads'))
from domain.runtime_services import runtime_context_for_step
context = runtime_context_for_step(
    inputs={{'output_folder': str(worker / 'output')}},
    runs_root=str(worker / 'runs'), run_id='embedded-config',
)
print(json.dumps({{'config': context['config'],
                  'run_id': context['run_id'],
                  'module_root': str(context['bundle_layout'].payload_root)}}))
""")
    assert result["config"] == json.loads(embedded)
    assert result["run_id"] == "embedded-config"
    assert Path(result["module_root"]) == tmp_path / "payloads"
