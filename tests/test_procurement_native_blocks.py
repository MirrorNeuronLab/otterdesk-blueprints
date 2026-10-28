"""Native branch isolation, publication replay and narrative authority contracts."""
import importlib
import json
from pathlib import Path

import pytest
from mn_blueprint_blocks.context import BlockContext
from mn_blueprint_blocks.contracts import fingerprint
from mn_sdk.blueprints import read_blueprint, resolve_config
from mn_sdk_common.committed_artifacts import CommittedJsonStore, CommittedArtifactIntegrityError

ROOT = Path(__file__).resolve().parents[1] / 'procurement_manager'


class Narrative:
    provider = 'fake'
    model = 'procurement-native-test'
    fallback_calls = input_tokens = output_tokens = total_tokens = estimated_tokens = 0

    def __init__(self):
        self.calls = 0
        self.prompts = []

    def generate_json(self, *, system_prompt, user_prompt, fallback):
        self.calls += 1
        self.prompts.append(user_prompt)
        return fallback


@pytest.fixture
def purchase(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / 'payloads'))
    monkeypatch.setenv('MN_JOB_OUTPUT_DIR', str(tmp_path / 'output'))
    config = resolve_config(read_blueprint(ROOT), {'execution': {'quick_test': False},
        'knowledge_rag': {'enabled': False}, 'internet_research': {'enabled': False}}).data
    model = Narrative()
    block = BlockContext(store=CommittedJsonStore(tmp_path / 'run'), invocation_id='purchase-test', revision='v5',
        config=config, run_id='run-1', job_id='job-1', resources={'llm': model})
    modules = {name: importlib.import_module('domain.' + name) for name in
        ['intake', 'comparison', 'case_packet', 'reporting']}
    framed = modules['intake'].collect_context(block, {'request': {'input_folder': str(ROOT / 'examples/procurement_case')}})
    evidence = modules['intake'].retrieve_knowledge(block, {'previous': framed})
    case = modules['case_packet'].assess_procurement_case(block, {'previous': evidence})
    market = modules['comparison'].research_market(block, {'previous': evidence})
    cost = modules['comparison'].analyze_total_cost(block, {'result': market})
    risk = modules['comparison'].review_purchase_risks(block, {'result': cost})
    audited = modules['comparison'].audit_recommendation(block, {'previous': risk})
    assert model.calls == 4
    return block, modules, model, {'previous': audited, 'case_assessment': case}


def test_delivery_retry_preserves_five_call_budget(purchase, monkeypatch):
    block, modules, model, joined = purchase
    publish = modules['reporting']
    from mn_sdk.blueprint_support import shared_outputs
    copy = shared_outputs.copy_path_to_host
    def interrupted(*args):
        raise OSError('output copy interrupted')
    monkeypatch.setattr(shared_outputs, 'copy_path_to_host', interrupted)
    with pytest.raises(OSError):
        publish.publish_report(block, joined)
    assert model.calls == 5 and block.store.path('procurement/report-analysis.json').exists()
    monkeypatch.setattr(shared_outputs, 'copy_path_to_host', copy)
    result = publish.publish_report(block, joined)
    assert model.calls == 5
    final = block.store.read_path('final_artifact.json')
    assert final['llm_generation']['calls_made'] == 5 and result['recommended_action'] == 'consider'
    assert block.store.read(result['state'])['llm_generation']['calls_made'] == 5


def test_checkpoint_cannot_replace_audited_economics(purchase, monkeypatch):
    block, modules, model, joined = purchase
    publish = modules['reporting']
    monkeypatch.setattr(publish, 'publish_documents', lambda *args: (_ for _ in ()).throw(OSError('interrupted')))
    with pytest.raises(OSError):
        publish.publish_report(block, joined)
    path = block.store.path('procurement/report-analysis.json')
    saved = json.loads(path.read_text())
    saved['analysis']['recommendation'] = {'label': 'buy', 'confidence': 'high'}
    saved['digest'] = fingerprint({'audit': saved['audit'], 'analysis': saved['analysis']})
    path.write_text(json.dumps(saved))
    with pytest.raises(ValueError, match='checkpoint'):
        publish.publish_report(block, joined)
    assert model.calls == 5 and not block.store.path('final_artifact.json').exists()


def test_changed_case_is_rejected_before_report_model_call(purchase):
    block, modules, model, joined = purchase
    joined['case_assessment']['decision_digest'] = 'changed'
    with pytest.raises(ValueError, match='differs'):
        modules['reporting'].publish_report(block, joined)
    assert model.calls == 4 and not block.store.path('final_artifact.json').exists()


def test_changed_audit_is_rejected_before_publication(purchase):
    block, modules, model, joined = purchase
    block.store.path(joined['previous']['state']['path']).write_text('{}')
    with pytest.raises(CommittedArtifactIntegrityError):
        modules['reporting'].publish_report(block, joined)
    assert model.calls == 4 and not block.store.path('final_artifact.json').exists()


def test_published_report_replay_verifies_required_bytes(purchase):
    block, modules, model, joined = purchase
    modules['reporting'].publish_report(block, joined)
    block.store.path('procurement_manager_report.md').write_text('changed')
    with pytest.raises(CommittedArtifactIntegrityError):
        modules['reporting'].publish_report(block, joined)
    assert model.calls == 5


def test_report_checkpoint_revalidates_cached_narrative(purchase, monkeypatch):
    block, modules, model, joined = purchase
    publish = modules['reporting']
    monkeypatch.setattr(publish, 'publish_documents', lambda *args: (_ for _ in ()).throw(OSError('interrupted')))
    with pytest.raises(OSError):
        publish.publish_report(block, joined)
    path = block.store.path('procurement/report-analysis.json')
    saved = json.loads(path.read_text())
    saved['analysis']['_llm_analysis_results']['purchase_report_writer']['executive_summary'] = 'The price is $999999999.'
    saved['digest'] = fingerprint({'audit': saved['audit'], 'analysis': saved['analysis']})
    path.write_text(json.dumps(saved))
    with pytest.raises(ValueError, match='narrative'):
        publish.publish_report(block, joined)
    assert model.calls == 5


def test_compiled_input_boundary_retains_contract_fields_and_excludes_unknown_data(tmp_path, monkeypatch):
    from block_workflow_fixture import run_sample
    monkeypatch.syspath_prepend(str(ROOT / 'payloads'))
    folder = tmp_path / 'inputs'
    folder.mkdir()
    (folder / 'missing-evidence.txt').write_text('Supplier quotations and purchase requirements have not been provided.')
    model = Narrative()
    result = run_sample('procurement_manager', inputs={'input_folder': str(folder),
        'output_folder': str(tmp_path / 'output'), 'budget': 2500, 'currency': 'USD',
        'analysis': {'horizon_years': 7}, 'private_prompt': 'SECRET-UNDECLARED-INPUT'},
        config={'execution': {'quick_test': True}, 'knowledge_rag': {'enabled': False},
                'internet_research': {'enabled': False}},
        runs_root=tmp_path / 'runs', run_id='contract-inputs', llm_client=model)
    store = CommittedJsonStore(tmp_path / 'runs/contract-inputs')
    captured = store.read_path('procurement/intake.json')['inputs']
    assert captured['analysis']['horizon_years'] == 7 and captured['budget'] == 2500
    assert captured['currency'] == 'USD' and 'private_prompt' not in captured
    assert store.read_path('inputs.json') == captured
    assert all('SECRET-UNDECLARED-INPUT' not in prompt for prompt in model.prompts)
    assert result['final_artifact']['recommended_action'] == 'wait'


def test_saved_rules_are_captured_and_reach_bounded_review_but_not_public_query_planning(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / 'payloads'))
    intake = importlib.import_module('domain.intake')
    analysis = importlib.import_module('domain.llm_analysis')
    rule = {'id': 'cash-due', 'kind': 'work_rule', 'text': 'PRIVATE-REVIEW-EMPHASIS: explain cash due before scenario sensitivity.'}
    config = resolve_config(read_blueprint(ROOT), {'execution': {'quick_test': False},
        'knowledge_rag': {'enabled': False}, 'internet_research': {'enabled': False},
        'inputs': {'payload': {'supervisor_instructions': [rule]}}}).data
    model = Narrative()
    block = BlockContext(store=CommittedJsonStore(tmp_path), invocation_id='rules', revision='procurement_manager@5.1.0',
        config=config, run_id='rules-run', job_id='rules-job', resources={'llm': model})
    framed = intake.collect_context(block, {'request': {'input_folder': str(ROOT / 'examples/procurement_case')}})
    state = block.store.read(framed['state'])
    assert state['inputs']['supervisor_instructions'] == [rule]
    assert state['supervisor_instruction_revision']
    assert all('PRIVATE-REVIEW-EMPHASIS' not in prompt for prompt in model.prompts)
    analysis.generate_structured_analysis(state=state, config={**config, 'llm_analysis': {'max_context_chars': 6000}},
        agent_id='purchase_total_cost_analyst', prompt_name='purchase-tco-analysis-task.md',
        payload={'evidence': 'Large quote context. ' * 4000, 'financial_npv_tco': 100},
        fallback={'summary': 'Review required'}, validator=lambda value, fallback, _settings: (fallback, []), llm_client=model)
    prompt = model.prompts[-1]
    packet = json.loads(prompt)
    assert len(prompt) <= 6000
    assert packet['supervisor_preferences']['instructions'] == [rule]
    assert 'cannot change deterministic costs' in packet['supervisor_preferences']['boundary']
    assert packet['analysis_context']['context_truncated'] is True
