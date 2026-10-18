"""Regressions for the EMC-2 planner starting without supplied case terms."""
# ruff: noqa: F811 -- Imported pytest fixtures are requested by name.
import json

import pytest
from jsonschema import ValidationError

from test_litigation_analyst import make_context, modules, graph_engine_stub  # noqa: F401
from test_dynamic_rounds import RoundModel, dynamic_case  # noqa: F401


def test_first_planner_discovers_case_terms_without_matter_or_history(dynamic_case, monkeypatch):
    from domain import round_planning
    context, ref = dynamic_case
    original = round_planning.complete

    def complete(root, frozen, key, stage, instruction, data, schema, client):
        assert schema['properties']['decision']['enum'] == ['execute']
        assert schema['properties']['hypotheses']['minItems'] == 1
        assert 'Empty historical memory is not an empty source corpus' in instruction
        return original(root, frozen, key, stage, instruction, data, schema, client)

    monkeypatch.setattr(round_planning, 'complete', complete)

    class SourceAware(RoundModel):
        def completion_text(self, system, user):
            data = json.loads(user)
            assert not data['counsel_scope']['issues'] and not data['prior_findings']
            overview = data['source_overview']
            assert overview['authorized_readable_sources'] == 1
            assert overview['inventory'][0]['source_id'] == 'case:notice.txt'
            sample = overview['samples'][0]
            assert sample['complete_source']
            assert sample['passages'][0]['text'] == 'Approval notice. Routine duties explain the correspondence.'
            assert not overview['exhaustive']
            return super().completion_text(system, user)

    model = SourceAware()
    result = round_planning.plan_round(context, {'context':ref, '_child':{'revision':0}}, llm_client=model)
    assert result['child_plan']['decision'] == 'execute'
    assert round_planning.plan_round(context, {'context':ref, '_child':{'revision':0}}, llm_client=model) == result
    assert len(model.calls) == 1


def test_first_planner_rejects_a_model_stop(dynamic_case):
    from domain.round_planning import plan_round
    context, ref = dynamic_case

    class EarlyStop(RoundModel):
        def completion_text(self, system, user):
            return json.dumps({'decision':'stop', 'rationale':'Historical memory is empty.', 'hypotheses':[]})

    with pytest.raises(ValidationError):
        plan_round(context, {'context':ref, '_child':{'revision':0}}, llm_client=EarlyStop())
    assert not (context['run_dir'] / 'case/rounds/plan-00.json').exists()


def test_discovery_filters_handling_and_duplicate_content(modules, tmp_path):
    from domain.round_state import initialize, load
    from domain.planning_context import discover
    folder = tmp_path / 'input'
    folder.mkdir()
    (folder/'record.txt').write_text('USD 12,500 for TX-104. Approval remains disputed.')
    (folder/'copy.txt').write_text((folder/'record.txt').read_text())
    (folder/'restricted.txt').write_text('Attorney-client privileged. PRIVATE_PLANNING_SENTINEL')
    context = make_context(tmp_path, folder)
    modules['intake'].prepare_sources(context)
    modules['indexing'].build_indexes(context)
    frozen = load(context['run_dir'], initialize(context)[0]['context'])
    packet = discover(context['run_dir'], frozen, 4096)
    assert packet['authorized_readable_sources'] == 2
    assert packet['distinct_contents'] == 1
    assert len(packet['inventory']) == len(packet['samples']) == 1
    assert 'restricted.txt' not in json.dumps(packet)
    assert 'PRIVATE_PLANNING_SENTINEL' not in json.dumps(packet)
    assert 'USD 12,500 for TX-104.' in packet['samples'][0]['passages'][0]['text']


def test_discovery_bounds_complete_units_and_preserves_dependencies(modules, tmp_path):
    from domain.round_state import initialize, load
    from domain.planning_context import discover
    folder = tmp_path / 'input'
    folder.mkdir()
    text = '1. Approval requires compliance with Section 2.\n\n2. Approval excludes emergency transfers.\n\n3. ' + 'Long appendix. ' * 1200
    (folder/'terms.txt').write_text(text)
    context = make_context(tmp_path, folder)
    modules['intake'].prepare_sources(context)
    modules['indexing'].build_indexes(context)
    frozen = load(context['run_dir'], initialize(context)[0]['context'])
    packet = discover(context['run_dir'], frozen, 2048)
    assert len(json.dumps(packet, ensure_ascii=False).encode()) <= 2048
    sample = packet['samples'][0]
    assert not sample['complete_source']
    spans = sample['passages']
    assert len(spans) == 2
    assert 'Section 2' in spans[0]['text'] and 'excludes emergency' in spans[1]['text']
    for span in spans:
        assert text[span['start_offset']:span['end_offset']] == span['text']
    assert discover(context['run_dir'], frozen, 0) is None


def test_no_authorized_sources_stops_without_inference(modules, tmp_path):
    from domain.round_state import initialize
    from domain.round_planning import plan_round
    folder = tmp_path/'input'
    folder.mkdir()
    (folder/'restricted.txt').write_text('Attorney-client privileged. PRIVATE_PLANNING_SENTINEL')
    context = make_context(tmp_path, folder)
    modules['intake'].prepare_sources(context)
    modules['indexing'].build_indexes(context)
    ref = initialize(context)[0]['context']
    model = RoundModel()
    result = plan_round(context, {'context':ref, '_child':{'revision':0}}, llm_client=model)
    assert result['child_plan']['output']['stop_reason'] == 'no_authorized_readable_sources'
    assert not model.calls


def test_no_planning_capacity_marks_incomplete_without_inference(dynamic_case, modules, monkeypatch):
    from domain import round_planning
    context, ref = dynamic_case
    monkeypatch.setattr(round_planning, 'evidence_room', lambda *args: 0)
    model = RoundModel()
    result = round_planning.plan_round(context, {'context':ref, '_child':{'revision':0}}, llm_client=model)
    assert result['child_plan']['output']['stop_reason'] == 'planning_source_context_unavailable'
    assert not model.calls
    modules['reporting'].write_review(context)
    workspace = json.loads((context['run_dir']/'case/workspace.json').read_text())
    assert workspace['analysis']['status'] == 'Incomplete analysis'


def test_tampered_index_never_reaches_planner(dynamic_case):
    from domain.round_planning import plan_round
    context, ref = dynamic_case
    (context['run_dir']/'case/source-relationships.json').write_text('{}')
    model = RoundModel()
    with pytest.raises(ValueError, match='index hash mismatch'):
        plan_round(context, {'context':ref, '_child':{'revision':0}}, llm_client=model)
    assert not model.calls
