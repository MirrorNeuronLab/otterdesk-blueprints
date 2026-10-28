"""App-owned conversation guidance across the authoritative published catalog."""
import json
from pathlib import Path
import pytest
from mn_sdk.blueprints import read_blueprint, catalog_record

ROOT = Path(__file__).resolve().parents[1]
FOLDERS = json.loads((ROOT / 'index.json').read_text())
STAGES = {'onboarding', 'configuring', 'ready', 'preparing', 'working', 'waiting_for_input', 'paused', 'reviewing', 'failed', 'stopped', 'archived'}

@pytest.mark.parametrize('folder', FOLDERS)
def test_stage_profile_and_memory_contract_are_consumed_by_desktop(folder):
    root = ROOT / folder
    package = read_blueprint(root)
    profile_file = root / 'payloads/prompts/conversation.json'
    profile = json.loads(profile_file.read_text())
    assert profile['schema'] == 'otterdesk.conversation_profile.v1'
    assert profile['blueprintId'] == package.manifest['id']
    assert set(profile['stages']) == STAGES
    assert all(20 < len(value) <= 1200 for value in profile['stages'].values())
    assert profile['responsibility'] and profile['evidence'] and profile['limitations']
    assert profile_file.stat().st_size <= 12000
    entry = catalog_record(package, folder)
    if profile['instructionKinds']:
        declaration = package.document('contracts')['inputs']['supervisor_instructions']
        assert declaration['required'] is False and declaration['maxItems'] == 50
        assert declaration['items']['properties']['kind']['enum'] == profile['instructionKinds']
        config = json.loads((root / 'config/default.json').read_text())
        assert config['inputs']['payload']['supervisor_instructions'] == []
        guides = [entry.get('setup_guide', {}), entry.get('init_config_review', {})]
        assert any(field.get('path') == 'inputs.payload.supervisor_instructions' and field.get('required') is False
                   for guide in guides for field in guide.get('fields', []))
    else:
        assert folder in {'cctv_operator', 'microduck_controller', 'ros_amr_controller'}
        assert 'supervisor_instructions' not in package.document('contracts')['inputs']
        assert entry['response_service']['agent']['kind'] == 'bounded_mcp'
