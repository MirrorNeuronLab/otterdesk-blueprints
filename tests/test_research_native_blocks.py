"""Research evidence joins, analysis completion and publication contracts."""
import importlib
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest
from mn_blueprint_blocks.context import BlockContext
from mn_blueprint_blocks.contracts import BlockError
from mn_sdk.blueprints import read_blueprint, resolve_config
from mn_sdk_common.committed_artifacts import CommittedJsonStore, CommittedArtifactIntegrityError

ROOT = Path(__file__).resolve().parents[1] / 'research_assistant'


@pytest.fixture
def research(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / 'payloads'))
    monkeypatch.setenv('MN_JOB_OUTPUT_DIR', str(tmp_path / 'output'))
    config = resolve_config(read_blueprint(ROOT), {'execution': {'quick_test': True},
        'knowledge_rag': {'enabled': False}, 'internet_research': {'enabled': False}}).data
    block = BlockContext(store=CommittedJsonStore(tmp_path / 'run'), invocation_id='research-native', revision='v4',
        config=config, run_id='run-1', job_id='job-1')
    modules = {name: importlib.import_module('domain.' + name) for name in
        ['intake', 'evidence', 'preflight', 'autonomous', 'verification', 'reporting', 'model']}
    goal = modules['intake'].frame_goal(block, {'input_folder': str(ROOT / 'examples/sample_inputs')})
    evidence = modules['evidence'].prepare_evidence(block, {'previous': goal})
    branches = {'evidence_coverage': modules['preflight'].assess_evidence_coverage(block, {'previous': evidence}),
        'experiment_readiness': modules['preflight'].assess_experiment_readiness(block, {'previous': evidence})}
    return block, modules, branches


def test_preflight_join_rejects_different_evidence_before_model_work(research, monkeypatch):
    block, modules, branches = research
    source = branches['experiment_readiness']['evidence']
    other = block.store.commit('research/other-evidence.json', block.store.read(source), kind='research_evidence').to_dict()
    branches['experiment_readiness']['evidence'] = other
    monkeypatch.setattr(modules['autonomous'], 'init_research_llm', lambda *a: pytest.fail('Mixed evidence reached model work'))
    with pytest.raises(ValueError, match='different evidence'):
        modules['autonomous'].autonomous_research(block, branches)


def test_preflight_join_rejects_changed_assessment_before_model_work(research, monkeypatch):
    block, modules, branches = research
    block.store.path(branches['evidence_coverage']['assessment']['path']).write_text('{}')
    monkeypatch.setattr(modules['autonomous'], 'init_research_llm', lambda *a: pytest.fail('Changed assessment reached model work'))
    with pytest.raises(CommittedArtifactIntegrityError):
        modules['autonomous'].autonomous_research(block, branches)


def test_completed_research_replays_without_more_model_calls(research, monkeypatch):
    block, modules, branches = research
    first = modules['autonomous'].autonomous_research(block, branches)
    monkeypatch.setattr(modules['autonomous'], 'init_research_llm', lambda *a: pytest.fail('Completed research repeated model work'))
    assert modules['autonomous'].autonomous_research(block, branches) == first
    audited = modules['verification'].audit_packet(block, {'previous': first})
    assert audited['status'] == 'passed'
    published = modules['reporting'].publish_packet(block, {'result': audited})
    assert block.store.read(published['state'])['packet_audit']['status'] == 'passed'
    assert block.store.read_path('final_artifact.json')['generation_provenance']['llm_calls'] == 18


@pytest.mark.parametrize('increase_allowance', [False, True])
def test_interrupted_read_only_research_can_retry(research, monkeypatch, increase_allowance):
    block, modules, branches = research
    calls = []
    run_research = modules['autonomous'].run_autonomous_research
    def interrupted(*args, **kwargs):
        calls.append(True)
        if len(calls) == 1:
            raise TimeoutError('interrupted research')
        return run_research(*args, **kwargs)
    monkeypatch.setattr(modules['autonomous'], 'run_autonomous_research', interrupted)
    with pytest.raises(TimeoutError):
        modules['autonomous'].autonomous_research(block, branches)
    assert not block.store.path('research/analysis-checkpoint.json').exists()
    assert not block.store.path('final_artifact.json').exists()
    if increase_allowance:
        retry_config = deepcopy(block.config)
        retry_config['budgets']['max_llm_calls'] *= 2
        block = replace(block, config=retry_config)
    retried = modules['autonomous'].autonomous_research(block, branches)
    assert calls == [True, True]
    assert modules['verification'].audit_packet(block, {'previous': retried})['status'] == 'passed'
    assert modules['autonomous'].autonomous_research(block, branches) == retried


def test_completed_analysis_checkpoint_recovers_before_state_publication(research, monkeypatch):
    block, modules, branches = research
    save_state = modules['autonomous'].save_state
    def interrupted(*args, **kwargs):
        raise TimeoutError('interrupted state publication')
    monkeypatch.setattr(modules['autonomous'], 'save_state', interrupted)
    with pytest.raises(TimeoutError, match='state publication'):
        modules['autonomous'].autonomous_research(block, branches)
    assert block.store.path('research/analysis-checkpoint.json').exists()
    assert not block.store.path('research/completed-analysis.json').exists()
    monkeypatch.setattr(modules['autonomous'], 'save_state', save_state)
    monkeypatch.setattr(modules['autonomous'], 'init_research_llm', lambda *a, **kw: pytest.fail('Checkpoint repeated model work'))
    recovered = modules['autonomous'].autonomous_research(block, branches)
    assert modules['verification'].audit_packet(block, {'previous': recovered})['status'] == 'passed'


def test_incomplete_analysis_rejects_changed_configuration(research, monkeypatch):
    from mn_sdk_common.committed_artifacts import CommittedArtifactConflict
    block, modules, branches = research
    def interrupted(*args, **kwargs):
        raise TimeoutError('interrupted research')
    monkeypatch.setattr(modules['autonomous'], 'run_autonomous_research', interrupted)
    with pytest.raises(TimeoutError):
        modules['autonomous'].autonomous_research(block, branches)
    block.config['execution']['quick_test'] = False
    block = replace(block, original_config=None)
    monkeypatch.setattr(modules['autonomous'], 'init_research_llm', lambda *a, **kw: pytest.fail('Changed configuration reached model work'))
    with pytest.raises(CommittedArtifactConflict):
        modules['autonomous'].autonomous_research(block, branches)


def test_live_provider_failure_remains_visible_on_retry(research, monkeypatch):
    from mn_sdk import llm as sdk_llm
    from mn_sdk.blueprint_support import runtime as sdk_runtime
    block, modules, branches = research
    block.config['execution']['quick_test'] = False
    block = replace(block, original_config=None)
    monkeypatch.setenv('MN_LLM_PROVIDER', 'litellm')
    monkeypatch.setenv('MN_LLM_API_BASE', 'http://runtime-selected.example/v1')
    monkeypatch.setenv('MN_LLM_MODEL', 'default')
    monkeypatch.setattr(sdk_runtime, 'select_default_model', lambda *a, **kw: {
        'selected_model': 'external-route', 'model': 'default', 'provider': 'litellm'})
    calls = []
    def unavailable(*args, **kwargs):
        calls.append(True)
        raise sdk_llm.LLMError('Runtime model gateway is unavailable.')
    monkeypatch.setattr(sdk_llm, 'runtime_model_json_request', unavailable)
    for _ in range(2):
        with pytest.raises(RuntimeError, match='research_phase:source_analysis.*Runtime model gateway is unavailable'):
            modules['autonomous'].autonomous_research(block, branches)
    assert calls == [True, True]
    assert not block.store.path('research/completed-analysis.json').exists()
    assert not block.store.path('final_artifact.json').exists()


def test_publication_requires_the_completed_audit(research):
    block, modules, branches = research
    analysis = modules['autonomous'].autonomous_research(block, branches)
    with pytest.raises(ValueError, match='completed packet audit'):
        modules['reporting'].publish_packet(block, {'result': analysis})
    assert not block.store.path('final_artifact.json').exists()


def test_research_publication_replay_rejects_changed_report(research):
    block, modules, branches = research
    analysis = modules['autonomous'].autonomous_research(block, branches)
    audited = modules['verification'].audit_packet(block, {'previous': analysis})
    modules['reporting'].publish_packet(block, {'result': audited})
    block.store.path('research_brief.md').write_text('changed')
    with pytest.raises(CommittedArtifactIntegrityError):
        modules['reporting'].publish_packet(block, {'result': audited})


def test_live_mode_does_not_reuse_a_quick_test_analysis(research):
    block, modules, branches = research
    modules['autonomous'].autonomous_research(block, branches)
    block.config['execution']['quick_test'] = False
    block = replace(block, original_config=None)
    with pytest.raises(ValueError, match='different evidence or configuration'):
        modules['autonomous'].autonomous_research(block, branches)


def test_native_research_cancels_between_model_phases(research):
    from mn_sdk.blueprint_support import DeterministicFallbackLLM
    block, modules, branches = research
    class Cancelling(DeterministicFallbackLLM):
        def generate_json(self, *, system_prompt, user_prompt, fallback):
            result = super().generate_json(system_prompt=system_prompt, user_prompt=user_prompt, fallback=fallback)
            block.cancelled = lambda: True
            return result
    model = Cancelling('cancel-test', default_summary='Synthetic research test', confidence=.5)
    block.resources['llm'] = model
    with pytest.raises(BlockError) as raised:
        modules['autonomous'].autonomous_research(block, branches)
    assert raised.value.code == 'cancelled' and model.calls == 1
    assert not block.store.path('research/completed-analysis.json').exists()
