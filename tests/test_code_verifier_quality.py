"""Known failure-mode regressions; synthetic source only, no live model."""
from copy import deepcopy
import importlib
import json
from pathlib import Path

import pytest
from mn_code_search_skill import TextSearchIndex
from mn_static_code_analysis_skill import analyze_sources

from test_code_verifier import modules, context, authority, Model, extracted, judgment, phase_inputs, reading


def finish_for(verification, span, status='pass', kind='behavior'):
    result = judgment(status)
    handle = verification.evidence_handle(span)
    result.update(evidence_ids=[handle], evidence=[{**span, 'quote':span['text']}])
    result['assessment'].update(enforcement_evidence_ids=[handle], requirement_kind=kind)
    return result


def test_generated_configuration_cannot_prove_behavior_or_configuration_of_product(modules):
    index = TextSearchIndex({'benchmark-results/run/analysis.json':'{"limit":4096}\n'})
    span = index.read(index.paths[0], 1, 1)
    for kind in ('behavior', 'configuration'):
        result = finish_for(modules['verification'], span, kind=kind)
        admitted = modules['verification'].admit(result, {'id':'R', 'requirement_kind':kind}, index, [span])
        assert admitted['status'] == 'unknown'
        assert admitted['reason_code'] == 'insufficient_evidence'


def test_configuration_only_proves_an_explicit_setting_and_example_requires_matching_scope(modules):
    index = TextSearchIndex({'profiles/default.json':'{"limit":4096}\n', 'examples/client.py':'import os\n'})
    span = index.read('profiles/default.json', 1, 1)
    result = finish_for(modules['verification'], span)
    assert modules['verification'].admit(result, {'id':'R'}, index, [span])['status'] == 'unknown'
    result['assessment']['requirement_kind'] = 'configuration'
    assert modules['verification'].admit(result, {'id':'R', 'requirement_kind':'configuration'}, index, [span])['status'] == 'pass'
    span = index.read('examples/client.py', 1, 1)
    result = finish_for(modules['verification'], span)
    assert modules['verification'].admit(result, {'id':'R'}, index, [span])['status'] == 'unknown'
    assert modules['verification'].admit(result, {'id':'R', 'scope':'examples/client.py'}, index, [span])['status'] == 'pass'


def test_status_cannot_disagree_with_structured_assessment(modules):
    index = TextSearchIndex({'src/a.py':'return_value = True\n'})
    span = index.read('src/a.py', 1, 1)
    result = finish_for(modules['verification'], span)
    result['status'] = 'fail'
    with pytest.raises(ValueError, match='inconsistent_verdict'):
        modules['verification'].admit(result, {'id':'R'}, index, [span])


def test_independent_critic_receives_no_draft_verdict_and_disagreement_preserves_evidence(modules, context):
    index = TextSearchIndex({'store.py':'def save():\n    return True\n'})
    span = index.read('store.py', 1, 2)
    result = finish_for(modules['verification'], span)
    class Reviewer(Model):
        def generate_json(self, **kwargs):
            if kwargs['system_prompt'].startswith('Independently assess'):
                packet = json.loads(kwargs['user_prompt'])
                assert 'status' not in packet and 'explanation' not in packet
                self.calls.append(packet)
                missing = judgment('unknown', .2)
                missing['evidence_ids'] = []
                return {'decision':missing}
            return super().generate_json(**kwargs)
    model = Reviewer([result])
    output = modules['verification'].verify_rule(context, {'id':'R', 'statement':'save returns True'},
        index, analyze_sources(index.copy_sources()), model)
    assert output['status'] == 'unknown' and output['reason_code'] == 'reviewer_disagreement'
    assert output['evidence'][0]['text'] == span['text']
    assert len(model.calls) == 2


def test_reserved_judgment_and_critique_fit_eight_calls(modules, context):
    index = TextSearchIndex({'store.py':'def save():\n    return True\n'})
    span = index.read('store.py', 1, 2)
    model = Model([{'action':'rank', 'query':f'nonexistent{n}'} for n in range(6)] +
                  [finish_for(modules['verification'], span)])
    output = modules['verification'].verify_rule(context, {'id':'R', 'statement':'save returns True'},
        index, analyze_sources(index.copy_sources()), model)
    assert output['status'] == 'pass' and output['diagnostics']['model_calls'] == 8
    assert output['diagnostics']['empty_searches'] == 6
    assert 'evidence_reads' in model.calls[-1]


def test_repeated_queries_receive_specific_feedback(modules, context):
    index = TextSearchIndex({'store.py':'def save():\n    return True\n'})
    span = index.read('store.py', 1, 2)
    model = Model([{'action':'search', 'query':'missing'}] * 2 + [finish_for(modules['verification'], span)])
    output = modules['verification'].verify_rule(context, {'id':'R', 'statement':'save returns True'},
        index, analyze_sources(index.copy_sources()), model)
    assert output['diagnostics']['repeated_queries'] == 1
    assert any(e.get('error_code') == 'repeated_query' for e in output['investigation'])
    assert output['status'] == 'pass'


def test_section_context_survives_packets_and_bare_tutorial_import_is_excluded(modules):
    text = '# API client\n\nThe client must use a timeout only when retries are enabled.\n```python\n' + 'import os\n' * 70 + '```\n'
    index = TextSearchIndex({'docs/client.md':text})
    packets = list(modules['rules'].document_packets(index, 'docs/client.md', text))
    assert len(packets) == 2 and packets[1]['line_context']['51']['in_code_fence']
    sources = importlib.import_module('domain.rule_sources')
    line = sources.source_lines(packets[1])[0]
    result = sources.bind_sources(index, packets[1], {'complete':True, 'rules':[
        {'statement':'The product must import os.', 'source_ids':[line['id']]}]})
    assert not result['rules'] and result['excluded_candidates'][0]['source']['start_line'] == 51
    assert result['excluded_candidates'][0]['reason'] == 'non_normative_example_or_instruction'
    assert 'only when retries are enabled' in packets[0]['text']


def test_current_scope_excludes_history_and_retains_current_contracts(modules):
    selection = modules['rules'].select_documents({'documents':['CHANGELOG.md', 'docs/evaluations/run.md',
        'docs/live-benchmark-review-20261003.md', 'SPEC.md', 'docs/usage.md', 'docs/benchmarking.md']}, 'current_requirements')
    assert selection['selected_documents'] == ['SPEC.md', 'docs/usage.md', 'docs/benchmarking.md']
    assert {r['reason'] for r in selection['excluded_documents']} == {'historical_changes', 'historical_evaluation'}


def test_dedup_keeps_conditions_and_all_origins_and_flags_conflicts(modules):
    policy = importlib.import_module('domain.document_policy')
    base = {'id':'A', 'origin':'extracted', 'statement':'The client must retry.', 'subject':'client', 'scope':'product',
            'conditions':['when enabled'], 'modality':'must', 'requirement_kind':'behavior', 'source':{'path':'SPEC.md'}}
    rules, flags = policy.consolidate([base, {**deepcopy(base), 'id':'B', 'source':{'path':'docs/a.md'}},
        {**deepcopy(base), 'id':'C', 'conditions':['when offline']},
        {**deepcopy(base), 'id':'D', 'statement':'The client must not retry.'}])
    assert len(rules) == 3 and rules[0]['additional_origins'][0]['id'] == 'B'
    assert flags[0]['rule_ids'] == ['A', 'C', 'D']
    distinct, _ = policy.consolidate([{**deepcopy(base), 'statement':'Call Foo("a  b").'},
        {**deepcopy(base), 'id':'B', 'statement':'Call foo("a b").'}])
    assert len(distinct) == 2  # Identifier case and literal whitespace are significant.


def test_project_map_is_bounded_without_limiting_retrieval(modules):
    from domain.source_policy import project_map
    sources = {f'{n:04}-long-source-name.py':'value = True\n' for n in range(600)}
    mapping = project_map(sources, analyze_sources(sources))
    assert mapping['roots_truncated'] and mapping['total_roots'] == 600
    assert len(mapping['roots']) == 32 and mapping['roles']['production_source'] == 600


def test_ci_capture_is_allowlisted_and_rejects_secrets_and_symlinks(modules, tmp_path):
    workflow = tmp_path / '.github/workflows'
    workflow.mkdir(parents=True)
    (workflow / 'release.yml').write_text('on: push\n')
    (workflow / 'secrets.yaml').write_text('private\n')
    (workflow / 'link.yml').symlink_to(workflow / 'release.yml')
    (tmp_path / '.github/credentials.json').write_text('private\n')
    (tmp_path / '.env').write_text('private\n')
    sources, omitted = modules['intake'].capture_folder(tmp_path)
    assert set(sources) == {'.github/workflows/release.yml'}
    assert {o['path'] for o in omitted} >= {'.env', '.github/credentials.json', '.github/workflows/secrets.yaml', '.github/workflows/link.yml'}


def test_capture_uses_declared_staged_configuration_without_a_shadowing_empty_port(modules, context):
    from mn_sdk.blueprints import compile_blueprint, read_blueprint
    from test_code_verifier import PACKAGE
    context.config['inputs']['payload']['input_folder'] = context.resources['inputs']['input_folder']
    context.original_config = deepcopy(context.config)
    modules['intake'].capture(context, {})
    captured = modules['artifacts'].read(context, 'capture.json')
    assert 'store.py' in captured['sources']
    compiled = compile_blueprint(read_blueprint(PACKAGE)).manifest
    source_block = compiled['metadata']['mn_blocks_lock']['steps']['capture_software_sources']
    assert source_block['inputs'] == {}


def test_policy_change_cannot_reuse_an_old_verified_result(modules, context, authority):
    modules['intake'].capture(context, context.resources['inputs'])
    modules['rules'].extract(context, phase_inputs(context), llm=Model([extracted()]))
    authority.approve(context)
    modules['verification'].verify(context, phase_inputs(context), llm=Model([reading(), judgment()] * 2))
    rule = modules['artifacts'].read(context, 'rules.json')['rules'][0]
    record = modules['artifacts'].read(context, f"verification/{rule['id']}.json")
    record['policy']['implementation'] = 'old-policy'
    modules['artifacts'].save(context, f"verification/{rule['id']}.json", record)
    with pytest.raises(ValueError, match='fresh run'):
        modules['verification'].verify(context, phase_inputs(context), llm=Model([]))


def test_extraction_exclusions_are_approved_and_exported_separately(modules, context, authority):
    (Path(context.resources['inputs']['input_folder']) / 'CHANGELOG.md').write_text('Historical behavior.\n')
    modules['intake'].capture(context, context.resources['inputs'])
    modules['rules'].extract(context, phase_inputs(context), llm=Model([extracted()]))
    authority.approve(context)
    document = modules['artifacts'].read(context, authority.published[-1][2]['markdown_review']['artifact_path'])
    assert 'historical_changes' in document['instructions'] and 'excluded' in document['notice']
    modules['verification'].verify(context, phase_inputs(context), llm=Model([reading(), judgment()] * 2))
    modules['reporting'].publish(context, phase_inputs(context))
    report = modules['artifacts'].read(context, 'result.json')
    assert report['coverage']['documentation_selection']['excluded_documents'][0]['path'] == 'CHANGELOG.md'
    assert report['diagnostics']['model_calls'] == 6
    assert report['summary'] == {'pass':2}
