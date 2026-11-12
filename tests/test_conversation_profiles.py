"""App-owned conversation guidance across the authoritative published catalog."""
import json
import re
from pathlib import Path
import pytest
from mn_sdk.blueprints import read_blueprint, catalog_record
from mn_sdk.blueprints.definition import setup_guide_from_contracts

ROOT = Path(__file__).resolve().parents[1]
FOLDERS = json.loads((ROOT / 'index.json').read_text())
# Local packages have the same Chat contract without being catalog entries.
LOCAL_FOLDERS = ['general_assistant', 'gtm_planner', 'gtm_executor']
PROFILE_FOLDERS = list(dict.fromkeys([*FOLDERS, *LOCAL_FOLDERS]))
STAGES = {'onboarding', 'configuring', 'ready', 'preparing', 'working', 'waiting_for_input', 'paused', 'reviewing', 'failed', 'stopped', 'archived'}
DERIVED_GUIDES = {'drug_discovery_research_assistant', 'vc_assistant', 'mac_security_investigator'}

@pytest.mark.parametrize('folder', PROFILE_FOLDERS)
def test_stage_profile_and_memory_contract_are_consumed_by_desktop(folder):
    root = ROOT / folder
    package = read_blueprint(root)
    profile_file = root / 'payloads/prompts/conversation.json'
    profile = json.loads(profile_file.read_text())
    assert profile['schema'] == 'otterdesk.conversation_profile.v1'
    assert profile['blueprintId'] == package.manifest['id']
    assert set(profile['stages']) == STAGES
    # The desktop normalizer keeps only 1,000 characters per stage. Guidance
    # after that point would validate but silently disappear from the prompt.
    assert all(20 < len(value) <= 1000 for value in profile['stages'].values())
    assert isinstance(profile['responsibility'], str) and 0 < len(profile['responsibility']) <= 1200
    # Match the desktop reader's array contract and normalization bounds. A
    # nonempty string used to pass this gate but was rejected by native Chat.
    for key in ('evidence', 'limitations'):
        assert isinstance(profile[key], list) and 0 < len(profile[key]) <= 8
        assert all(isinstance(text, str) and 0 < len(text) <= 1000 for text in profile[key])
    assert isinstance(profile['instructionKinds'], list)
    assert len(profile['instructionKinds']) == len(set(profile['instructionKinds']))
    assert set(profile['instructionKinds']) <= {'communication', 'work_rule'}
    assert profile_file.stat().st_size <= 12000
    entry = catalog_record(package, folder)
    # First-hire welcomes read setup_guide directly, before any model reply.
    # A stage profile alone would leave the generic welcome visible.
    assert 20 < len(entry['setup_guide']['introduction']) <= 2000
    assert entry['setup_guide']['introduction'] == package.extension('mn.ui')['setup_guide']['introduction']
    prompt_file = entry['setup_guide']['prompt_file']
    assert prompt_file == '@/payloads/prompts/setup.md'
    prompt = root / prompt_file.removeprefix('@/')
    assert prompt.is_file() and 0 < prompt.stat().st_size <= 12000
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
        # Presentation guidance does not opt a co-worker into a new memory
        # feature. Both bounded responders and ordinary read-only roles may
        # intentionally have no app-managed supervisor instructions.
        assert 'supervisor_instructions' not in package.document('contracts')['inputs']
        if folder in {'cctv_operator', 'ros_amr_controller'}:
            assert entry['response_service']['agent']['kind'] == 'bounded_mcp'


@pytest.mark.parametrize('folder', PROFILE_FOLDERS)
def test_conversation_knowledge_is_reachable_and_worker_seeds_match(folder):
    root = ROOT / folder
    guide = root / 'knowledge/conversation_guide.md'
    manual = root / 'knowledge/user_manual.md'
    assert guide.is_file()
    links = re.findall(r'\[[^\]]+\]\(([^)]+)\)', manual.read_text())
    assert 'conversation_guide.md' in links
    # Several workers stage a separate knowledge tree in their isolated image.
    # They must explain the same onboarding and handoff as the Job responder.
    for staged in (root / 'payloads').rglob('conversation_guide.md'):
        assert staged.read_bytes() == guide.read_bytes(), staged


@pytest.mark.parametrize('folder', sorted(DERIVED_GUIDES))
def test_authored_welcomes_preserve_previously_generated_setup_contract(folder):
    package = read_blueprint(ROOT / folder)
    guide = package.extension('mn.ui')['setup_guide']
    generated = setup_guide_from_contracts(package)
    # Declaring welcome copy replaces the SDK's entire generated guide. Keep
    # its fields and sample/real values so presentation cannot hide a setting.
    assert guide['fields'] == generated['fields']
    assert guide['sample']['available'] == generated['sample']['available']
    assert guide['sample']['values'] == generated['sample']['values']
    assert guide['real']['values'] == generated['real']['values']
