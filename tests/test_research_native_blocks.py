"""Research evidence joins, analysis completion and publication contracts."""
import importlib
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


def test_interrupted_research_does_not_repeat_model_procedure(research, monkeypatch):
    block, modules, branches = research
    calls = []
    def interrupted(*args, **kwargs):
        calls.append(True)
        raise TimeoutError('interrupted research')
    monkeypatch.setattr(modules['autonomous'], 'run_autonomous_research', interrupted)
    with pytest.raises(TimeoutError):
        modules['autonomous'].autonomous_research(block, branches)
    with pytest.raises(BlockError) as raised:
        modules['autonomous'].autonomous_research(block, branches)
    assert raised.value.code == 'outcome_unknown' and calls == [True]
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
