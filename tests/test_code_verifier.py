"""Deterministic blueprint contracts and end-to-end evidence admission; no live model."""
import ast
from copy import deepcopy
import importlib
import json
import math
from hashlib import sha256
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / 'code_verifier'
IMPLEMENTATION = 'def save(name, password, store):\n    if not name:\n        raise ValueError("name required")\n    store.write(password)\n'


@pytest.fixture
def modules():
    sys.path.insert(0, str(PACKAGE / 'payloads'))
    return {name: importlib.import_module('domain.' + name) for name in
            ['intake', 'rules', 'verification', 'reporting', 'artifacts', 'configuration', 'rule_review']}


@pytest.fixture
def context(tmp_path):
    source = tmp_path / 'repository'
    source.mkdir()
    (source / 'SPEC.md').write_text('The software must reject an empty name.\nThe software must not save plaintext passwords.\n')
    (source / 'store.py').write_text(IMPLEMENTATION)
    job = tmp_path / 'job'
    (job / 'knowledge/rules').mkdir(parents=True)
    (job / 'knowledge/rules/custom.md').write_text('')
    config = json.loads((PACKAGE / 'config/default.json').read_text())
    return {'blueprint_id': 'code_verifier', 'run_dir': tmp_path / 'run', 'output_folder': tmp_path / 'outputs',
            'job_data_dir': job, 'job_id': 'job-1',
            'run_id': 'run-1', 'payload': {'input_folder': str(source)}, 'config': config}


@pytest.fixture
def authority(modules, monkeypatch):
    class Authority:
        def __init__(self):
            self.events = {}
            self.published = []
            self.decisions = []
            self.before_response = lambda: None

        def read(self, run_id):
            return deepcopy(self.events.get(run_id, []))

        def publish(self, run_id, kind, payload, **kwargs):
            self.published.append((run_id, kind, deepcopy(payload)))
            self.events.setdefault(run_id, []).append({'type': kind, 'payload': deepcopy(payload)})

        def wait(self, run_id, request_id, *, timeout):
            assert 0 < timeout <= 3600
            self.before_response()
            decision = self.decisions.pop(0) if self.decisions else 'approve'
            if isinstance(decision, Exception):
                raise decision
            notes = decision.get('notes', '') if isinstance(decision, dict) else ''
            decision = decision['decision'] if isinstance(decision, dict) else decision
            event = {'type': 'human_input_received', 'payload': {'request_id': request_id,
                'decision': decision, 'approved': decision == 'approve', 'notes': notes}}
            self.events.setdefault(run_id, []).append(event)
            return deepcopy(event)

        def approve(self, context):
            return modules['rule_review'].review(context)

    service = Authority()
    api = modules['rule_review'].human_interactions
    monkeypatch.setattr(api, 'read_interaction_events', service.read)
    monkeypatch.setattr(api, 'publish_human_interaction_event', service.publish)
    monkeypatch.setattr(api, 'await_human_decision', service.wait)
    return service


class Model:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    def completion_json(self, system, user, **kwargs):
        self.calls.append(json.loads(user))
        value = next(self.responses)
        if isinstance(value, Exception):
            raise value
        return value


def extracted():
    statements = ['The software must reject an empty name.', 'The software must not save plaintext passwords.']
    return {'complete': True, 'rules': [{'statement': value,
        'source_ids': [f'L{n}-{sha256((value + chr(10)).encode()).hexdigest()[:12]}']}
        for n, value in enumerate(statements, 1)]}


def reading(path='store.py', start=1, end=4):
    return {'action': 'read', 'path': path, 'start_line': start, 'end_line': end}


def judgment(status='pass', score=.95, path='store.py', quote='if not name:'):
    source_hash = sha256((IMPLEMENTATION if quote in IMPLEMENTATION else quote).encode()).hexdigest()
    handle = 'SRC-' + sha256(json.dumps([path, source_hash, 1, 4]).encode()).hexdigest()[:20]
    return {'action': 'finish', 'status': status, 'confidence': score,
            'explanation': 'The inspected implementation directly establishes this scoped observation.',
            'evidence_ids': [handle],
            'evidence': [{'path': path, 'start_line': 1, 'end_line': 4, 'quote': quote}]}


def test_complete_pipeline_rules_report_and_idempotency(modules, context, authority):
    source = Path(context['payload']['input_folder'])
    before = {p.name: p.read_bytes() for p in source.iterdir()}
    modules['intake'].capture(context)
    modules['rules'].extract(context, Model([extracted()]))
    authority.approve(context)
    reviewer = Model([{'action': 'search', 'query': 'name'}, reading(), judgment(),
                      reading(), judgment('fail', .8, quote='store.write(password)')])
    modules['verification'].verify(context, reviewer)
    modules['reporting'].publish(context)
    final = modules['artifacts'].read(context, 'final_artifact.json')
    assert final['summary'] == {'pass': 1, 'fail': 1}
    assert [r['confidence'] for r in final['results']] == [.85, .8]
    assert all(not r['tests_executed'] for r in final['results'])
    report = (context['run_dir'] / 'report.md').read_text()
    assert '| Rule | Pass or not | Evidence with reference | Confidence (0–1) |' in report
    assert 'store.py:1–4' in report and 'SHA-256' in report
    assert (context['run_dir'] / 'source/store.py').read_bytes() == before['store.py']
    page = (context['run_dir'] / 'web/index.html').read_text()
    assert 'MNWebReport' in page and 'Rule results' in page
    assert 'connect-src &#x27;none&#x27;' in page
    assert json.loads((context['run_dir'] / 'web_ui.json').read_text())['adapter'] == 'static_html'
    output = context['output_folder']
    for name in ['report.md', 'rules.md', 'rules.json', 'result.json', 'verification.json',
                 'source/store.py', 'reviews/original-rules.json', 'web/index.html', 'web_ui.json']:
        assert (output / name).read_bytes() == (context['run_dir'] / name).read_bytes()
    assert {p.name: p.read_bytes() for p in source.iterdir()} == before
    assert len(reviewer.calls) == 5
    first, second = [rule['id'] for rule in final['rules']]
    assert [request['rule']['id'] for request in reviewer.calls] == [first] * 3 + [second] * 2
    modules['intake'].capture(context)
    modules['rules'].extract(context, Model([]))
    modules['verification'].verify(context, Model([]))
    modules['reporting'].publish(context)
    assert modules['artifacts'].read(context, 'final_artifact.json') == final


def test_staged_report_reaches_batch_host_output(modules, context, authority, tmp_path):
    from mn_sdk.blueprint_support.shared_outputs import materialize_shared_storage_outputs_until_stable
    modules['intake'].capture(context)
    modules['rules'].extract(context, Model([extracted()]))
    authority.approve(context)
    modules['verification'].verify(context, Model([reading(), judgment(), reading(), judgment()]))
    modules['artifacts'].save(context, 'private-runtime-config.json', {'secret': 'not-a-report'})
    modules['reporting'].publish(context)
    destination = tmp_path / 'Downloads/code-verifier'
    storage = {'run_id': 'run-1', 'host_root': str(tmp_path), 'runtime_root': '/runtime',
               'host_submission_path': str(tmp_path / 'submission'), 'output_copy': [{
                   'source_path': '/runtime/outputs', 'target_path': str(destination),
                   'layout': 'batch', 'result': {'kind': 'output_folder', 'label': 'Output folder'}}]}
    receipt = materialize_shared_storage_outputs_until_stable(storage, poll_seconds=.01, timeout_seconds=1)
    assert receipt['copied'] and not receipt['errors']
    delivered = Path(receipt['target_paths'][0])
    assert delivered.parent == destination and delivered.name.startswith('run_')
    assert (delivered / 'report.md').read_bytes() == (context['run_dir'] / 'report.md').read_bytes()
    assert (delivered / 'web/index.html').read_bytes() == (context['run_dir'] / 'web/index.html').read_bytes()
    assert not (delivered / 'private-runtime-config.json').exists()
    assert delivered.name + '/web/index.html' in (destination / 'latest.html').read_text()


def test_optional_web_staging_failure_keeps_deliverable_report(modules, context, authority, monkeypatch):
    modules['intake'].capture(context)
    modules['rules'].extract(context, Model([extracted()]))
    authority.approve(context)
    modules['verification'].verify(context, Model([reading(), judgment(), reading(), judgment()]))
    stage = modules['reporting'].stage_outputs
    def fail_web(ctx, names):
        if 'web' in names:
            raise OSError('Optional presentation could not be staged')
        stage(ctx, names)
    monkeypatch.setattr(modules['reporting'], 'stage_outputs', fail_web)
    modules['reporting'].publish(context)
    assert (context['output_folder'] / 'report.md').is_file()
    assert (context['output_folder'] / 'rules.md').is_file()
    assert modules['artifacts'].read(context, 'presentation-status.json')['error_type'] == 'OSError'


@pytest.mark.parametrize('link_at', ['source', 'destination'])
def test_report_staging_rejects_escaping_symlinks(modules, context, tmp_path, link_at):
    from domain.publication import stage_outputs
    run, output = context['run_dir'], context['output_folder']
    run.mkdir()
    output.mkdir()
    outside = tmp_path / 'outside.md'
    outside.write_text('private')
    if link_at == 'source':
        (run / 'report.md').symlink_to(outside)
    else:
        (run / 'report.md').write_text('report')
        (output / 'report.md').symlink_to(outside)
    with pytest.raises(ValueError):
        stage_outputs(context, ['report.md'])
    assert outside.read_text() == 'private'


def test_standalone_output_folder_can_contain_its_run_archive(modules, context):
    from domain.publication import stage_outputs
    context['run_dir'] = context['output_folder'] / 'runs/run-1'
    context['run_dir'].mkdir(parents=True)
    (context['run_dir'] / 'report.md').write_text('report')
    stage_outputs(context, ['report.md'])
    assert (context['output_folder'] / 'report.md').read_text() == 'report'


def test_custom_rules_add_override_and_replace(modules, context):
    modules['intake'].capture(context)
    modules['rules'].extract(context, Model([extracted()]))
    original = modules['artifacts'].read(context, 'rules.json')['rules'][0]
    knowledge = context['job_data_dir'] / 'knowledge/rules/custom.md'
    knowledge.write_text(f"## {original['id']}\n\nChanged expectation.\n\n## CUSTOM-1\n\nSoftware should support cancel.\n")
    context['run_dir'] = context['run_dir'].with_name('second')
    modules['intake'].capture(context)
    modules['rules'].extract(context, Model([extracted()]))
    rules = modules['artifacts'].read(context, 'rules.json')['rules']
    assert len(rules) == 3
    assert next(r for r in rules if r['id'] == original['id'])['statement'] == 'Changed expectation.'
    context['run_dir'] = context['run_dir'].with_name('third')
    context['config']['review']['rules_mode'] = 'replace'
    modules['intake'].capture(context)
    modules['rules'].extract(context, Model([]))
    assert len(modules['artifacts'].read(context, 'rules.json')['rules']) == 2


@pytest.mark.parametrize('body', ['free prose', '## MY-RULE\n', '# Wrong heading\nrule',
                                  'preface\n## MY-RULE\nbody', '## ../bad\nbody'])
def test_custom_markdown_invalid_input(modules, body):
    with pytest.raises(ValueError):
        modules['rules'].custom_rules('knowledge/rules/custom.md', body)


def test_duplicate_custom_ids_fail(modules, context):
    knowledge = context['job_data_dir'] / 'knowledge/rules'
    (knowledge / 'custom.md').write_text('## SAME\n\nrule one\n')
    (knowledge / 'other.md').write_text('## SAME\n\nrule two\n')
    modules['intake'].capture(context)
    with pytest.raises(ValueError, match='unique'):
        modules['rules'].extract(context, Model([]))


@pytest.mark.parametrize('result', [{'complete': False, 'rules': []},
                                   {'complete': True, 'rules': [{'statement': 'Invented', 'quote': 'fake', 'start_line': 1, 'end_line': 1}]}])
def test_incomplete_extraction_and_forged_provenance_become_visible_gaps(modules, context, result):
    from domain.extraction_outcome import RuleExtractionFailed
    modules['intake'].capture(context)
    model = Model([result] * 9)
    with pytest.raises(RuleExtractionFailed):
        modules['rules'].extract(context, model)
    saved = modules['artifacts'].read(context, 'rules.json')
    assert saved['rules'] == [] and saved['extraction_status'] == 'failed'
    assert saved['extraction_gaps'] and len(model.calls) <= 9


def test_long_docs_every_line_extracted_once(modules):
    from mn_code_search_skill import TextSearchIndex
    value = ''.join(f'Line {i} with text.\n' for i in range(450))
    packets = list(modules['rules'].document_packets(TextSearchIndex({'spec.md': value}), 'spec.md', value))
    assert len(packets) == 9
    assert ''.join(p['text'] for p in packets) == value
    assert [(p['start_line'], p['end_line']) for p in packets] == [(n, n + 49) for n in range(1, 451, 50)]


def test_single_long_document_line_is_not_split_or_given_an_empty_packet(modules):
    from mn_code_search_skill import TextSearchIndex
    value = 'x' * 8000 + '\nNext line.\n'
    packets = list(modules['rules'].document_packets(TextSearchIndex({'spec.md':value}), 'spec.md', value))
    assert [(p['start_line'], p['end_line']) for p in packets] == [(1, 1), (2, 2)]
    assert ''.join(p['text'] for p in packets) == value


def test_generated_reports_are_explicitly_excluded_from_rule_sources(modules, context, authority):
    source = Path(context['payload']['input_folder'])
    generated = source / 'benchmark-results'
    generated.mkdir()
    for number in range(172):
        (generated / f'result-{number}.md').write_text('Generated benchmark observations.\n')
    modules['intake'].capture(context)
    capture = modules['artifacts'].read(context, 'capture.json')
    assert len(capture['documents']) == 173
    assert 'benchmark-results/result-0.md' in capture['sources']
    model = Model([extracted()])
    modules['rules'].extract(context, model)
    assert len(model.calls) == 1
    plan = modules['artifacts'].read(context, 'extraction-plan.json')
    assert plan['selected_documents'] == ['SPEC.md']
    assert len(plan['excluded_documents']) == 172
    assert plan['packet_count'] == 1
    authority.approve(context)
    modules['verification'].verify(context, Model([reading(), judgment(), reading(), judgment('fail', .8, quote='store.write(password)')]))
    modules['reporting'].publish(context)
    final = modules['artifacts'].read(context, 'final_artifact.json')
    assert final['coverage']['documentation_selection']['excluded_documents'] == plan['excluded_documents']
    assert 'excluded 172 generated reports' in (context['run_dir'] / 'report.md').read_text()


def test_all_docs_support_more_than_150_packets_without_losing_lines(modules, context):
    source = Path(context['payload']['input_folder'])
    generated = source / 'benchmark-results'
    generated.mkdir()
    value = ''.join(f'Observation {n}.\n' for n in range(151 * 50))
    (generated / 'results.md').write_text(value)
    context['config']['review']['documentation_scope'] = 'all_captured_docs'
    modules['intake'].capture(context)
    model = Model([extracted()] + [{'complete': True, 'rules': []}] * 151)
    modules['rules'].extract(context, model)
    plan = modules['artifacts'].read(context, 'extraction-plan.json')
    assert plan['packet_count'] == 152 and plan['excluded_documents'] == []
    assert len(model.calls) == 152
    assert ''.join(c['document']['text'] for c in model.calls[1:]) == value


def test_packet_budget_is_checked_before_model_creation(modules, context, monkeypatch):
    source = Path(context['payload']['input_folder'])
    (source / 'other.md').write_text('Another requirement.\n')
    modules['intake'].capture(context)
    context['config']['review']['max_extraction_packets'] = 1
    monkeypatch.setattr(modules['rules'], 'client', lambda c: pytest.fail('Model constructed before preflight'))
    with pytest.raises(ValueError, match='review.max_extraction_packets=1'):
        modules['rules'].extract(context)
    assert not (context['run_dir'] / 'rules.json').exists()


def test_blueprint_preserves_the_prepared_model_binding(context, modules, monkeypatch):
    from types import SimpleNamespace
    model = importlib.import_module('domain.model')
    prepared = SimpleNamespace(model='registered-provider/model', provider='litellm',
        api_base='http://prepared-gateway/v1', backend='provider', api_key='private',
        structured_output_options={'response_format': {'type': 'json_object'}})
    def from_env(*, strict):
        assert strict is True
        return prepared
    monkeypatch.setattr(model.LLMClient, 'from_env', from_env)
    result = model.client(context)
    assert result.model == 'registered-provider/model' and result.provider == 'litellm'
    assert result.api_base == 'http://prepared-gateway/v1' and result.backend == 'provider'
    assert result.structured_output_options == {'response_format': {'type': 'json_object'}}
    assert result.max_tokens == 3500 and result.timeout_seconds == 90 and result.num_retries == 0
    assert model.client(context, extraction=True).max_tokens == 8192


@pytest.mark.parametrize('provider', ['openai', 'openrouter', 'openai-compatible'])
def test_registered_remote_default_uses_gateway_without_loading_local_model(modules, context, tmp_path, monkeypatch, provider):
    from contextlib import closing
    from io import BytesIO
    from mn_sdk.model_registry import add_registered_models, load_provider_definition, set_registered_default_model
    import mn_sdk.model_access.runtime as access

    monkeypatch.setenv('MN_HOME', str(tmp_path / 'runtime'))
    definition = tmp_path / 'provider.json'
    definition.write_text(json.dumps({'provider': {provider: {
        'options': {'baseURL': 'https://remote.example/v1'},
        'models': {'remote/custom-model': {}},
    }}}))
    add_registered_models(load_provider_definition(definition))
    set_registered_default_model('remote/custom-model')
    for key, value in {'MN_RUN_ID':'run', 'MN_SELECTED_RUNTIME_NODE':'selected',
                       'MN_LLM_MODEL':'default', 'MN_LLM_PROVIDER':'litellm',
                       'MN_LLM_BACKEND':'provider', 'MN_LLM_API_BASE':'http://127.0.0.1:4000/v1'}.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv('MN_RUNTIME_MODEL_MANAGED', raising=False)
    access.clear_runtime_model_cache()

    def unexpected_prepare(**kwargs):
        pytest.fail('A remote default must not prepare a local LLM')
    monkeypatch.setattr(access, '_prepare_managed_binding', unexpected_prepare)
    sent = []
    def gateway(request, timeout):
        sent.append(json.loads(request.data))
        return closing(BytesIO(json.dumps({'choices': [{
            'message': {'content':json.dumps(extracted())}, 'finish_reason':'stop',
        }]}).encode()))
    monkeypatch.setattr(access.urllib.request, 'urlopen', gateway)
    model = importlib.import_module('domain.model')
    client = model.client(context, extraction=True)
    assert model.ask(client, 'extract.md', {'document':{'text':'Synthetic test input.'}}) == extracted()
    assert len(sent) == 1 and sent[0]['model'] == 'default'
    assert client.provider == 'litellm' and client.backend == 'provider'


@pytest.mark.parametrize('newline', ['\n', '\r\n', '\r'])
def test_rule_source_lines_are_derived_from_exact_quotes(modules, newline):
    from mn_code_search_skill import TextSearchIndex
    value = newline.join(['Before', 'The software must reject an empty name.', 'After']) + newline
    index = TextSearchIndex({'spec.md': value})
    packet = index.read('spec.md', 1, 3)
    span = modules['rules'].exact_rule_source(index, packet,
        {'quote':'The software must reject an empty name.', 'start_line':99, 'end_line':100})
    assert (span['start_line'], span['end_line']) == (2, 2)


def test_ambiguous_or_invented_rule_quotes_fail(modules):
    from mn_code_search_skill import TextSearchIndex
    index = TextSearchIndex({'spec.md':'Same statement.\nSame statement.\n'})
    packet = index.read('spec.md', 1, 2)
    for quote in ['Same statement.', 'Invented statement.']:
        with pytest.raises(ValueError, match='verbatim'):
            modules['rules'].exact_rule_source(index, packet, {'quote':quote})


def test_source_contract_correction_is_bounded_and_does_not_drop_rules(modules, context):
    modules['intake'].capture(context)
    invalid = extracted()
    invalid['rules'][0]['source_ids'] = ['fabricated']
    model = Model([invalid, {'repairs':[{'index':0, 'source_ids':extracted()['rules'][0]['source_ids']}]}])
    modules['rules'].extract(context, model)
    rules = modules['artifacts'].read(context, 'rules.json')
    assert len(rules['rules']) == 2 and len(model.calls) == 2
    assert 'correction' in model.calls[1]
    assert (context['run_dir'] / 'extraction/drafts/packet-0000-attempt-1.json').is_file()
    cached = modules['artifacts'].read(context, 'extraction/packet-0000.json')
    assert cached['rules'][0]['quote'] == 'The software must reject an empty name.\n'
    assert model.calls[1]['rules_to_correct'] == [{'index':0, 'statement':extracted()['rules'][0]['statement']}]


def test_source_contract_correction_obeys_operator_limit(modules, context):
    modules['intake'].capture(context)
    context['config']['review']['max_extraction_attempts'] = 1
    invalid = extracted()
    invalid['rules'][0]['source_ids'] = ['fabricated']
    model = Model([invalid, extracted()])
    from domain.extraction_outcome import RuleExtractionFailed
    with pytest.raises(RuleExtractionFailed):
        modules['rules'].extract(context, model)
    assert len(model.calls) == 1
    assert modules['artifacts'].read(context, 'rules.json')['extraction_gaps'][0]['reason'] == 'invalid_model_response'


def invalid_json():
    from mn_sdk.llm import LLMError
    error = LLMError('private provider content', usage={'output_tokens':3500, 'provider_response_count':1})
    try:
        json.loads('{"rules":[')
    except json.JSONDecodeError as cause:
        error.__cause__ = cause
    return error


@pytest.mark.parametrize('response', [invalid_json(), {'complete':False, 'rules':[{'statement':'partial'}]}])
def test_invalid_or_incomplete_json_is_split_without_losing_source(modules, context, response):
    modules['intake'].capture(context)
    model = Model([response, {'complete':True, 'rules':extracted()['rules'][:1]},
                             {'complete':True, 'rules':extracted()['rules'][1:]}])
    modules['rules'].extract(context, model)
    saved = modules['artifacts'].read(context, 'rules.json')
    assert len(saved['rules']) == 2 and len(model.calls) == 3
    assert [c['document']['start_line'] for c in model.calls] == [1, 1, 2]
    assert ''.join(c['document']['text'] for c in model.calls[1:]) == model.calls[0]['document']['text']
    assert (context['run_dir'] / 'extraction/splits/packet-0000.json').is_file()
    assert 'private provider content' not in '\n'.join(p.read_text() for p in context['run_dir'].rglob('*.json'))


def test_adaptive_packet_limit_is_enforced_before_child_model_calls(modules, context):
    modules['intake'].capture(context)
    context['config']['review']['max_extraction_packets'] = 2
    model = Model([invalid_json()])
    from domain.extraction_outcome import RuleExtractionFailed
    with pytest.raises(RuleExtractionFailed):
        modules['rules'].extract(context, model)
    assert len(model.calls) == 1
    assert modules['artifacts'].read(context, 'rules.json')['extraction_gaps']


def test_transient_model_failure_retries_without_splitting_source(modules, context, monkeypatch):
    from mn_sdk.llm import LLMError
    modules['intake'].capture(context)
    error = LLMError('Provider unavailable')
    model = Model([error, extracted()])
    waits = []
    monkeypatch.setattr(modules['rules'].time, 'sleep', waits.append)
    modules['rules'].extract(context, model)
    assert len(model.calls) == 2 and waits == [1]
    assert modules['artifacts'].read(context, 'rules.json')['extraction_status'] == 'complete'
    assert not list((context['run_dir'] / 'extraction/splits').glob('*.json'))


def test_split_keeps_successful_child_and_new_run_reuses_checkpoint(modules, context, monkeypatch):
    from mn_sdk.llm import LLMError
    modules['intake'].capture(context)
    monkeypatch.setattr(modules['rules'].time, 'sleep', lambda seconds: None)
    first = Model([invalid_json(), {'complete':True, 'rules':extracted()['rules'][:1]}]
                  + [LLMError('Provider unavailable')] * 3)
    modules['rules'].extract(context, first)
    assert (context['run_dir'] / 'extraction/parts/packet-0000-left.json').is_file()
    saved = modules['artifacts'].read(context, 'rules.json')
    assert len(saved['rules']) == 1 and saved['extraction_gaps'][0]['start_line'] == 2
    context['run_dir'] = context['run_dir'].with_name('new-run')
    context['run_id'] = 'run-2'
    context['job_id'] = 'execution-2'
    modules['intake'].capture(context)
    second = Model([invalid_json(), {'complete':True, 'rules':extracted()['rules'][1:]}])
    modules['rules'].extract(context, second)
    assert len(second.calls) == 2 and len(modules['artifacts'].read(context, 'rules.json')['rules']) == 2


def test_single_line_invalid_json_corrections_are_bounded(modules, context):
    (Path(context['payload']['input_folder']) / 'SPEC.md').write_text('One requirement.\n')
    modules['intake'].capture(context)
    model = Model([invalid_json()] * 3)
    from domain.extraction_outcome import RuleExtractionFailed
    with pytest.raises(RuleExtractionFailed):
        modules['rules'].extract(context, model)
    assert len(model.calls) == 3
    assert modules['artifacts'].read(context, 'rules.json')['extraction_gaps'][0]['start_line'] == 1


def test_failed_document_does_not_block_others_and_gap_requires_approval(modules, context, authority):
    statement = 'The software should expose health status.'
    (Path(context['payload']['input_folder']) / 'other.md').write_text(statement + '\n')
    modules['intake'].capture(context)
    context['config']['review']['max_extraction_attempts'] = 1
    response = {'complete':True, 'rules':[{'statement':statement,
        'source_ids':['L1-' + sha256((statement + '\n').encode()).hexdigest()[:12]]}]}
    bad = {'complete':True, 'rules':[{'statement':'Unadmitted rule', 'source_ids':['invalid']}]}
    modules['rules'].extract(context, Model([bad, response]))
    rules = modules['artifacts'].read(context, 'rules.json')
    assert [r['statement'] for r in rules['rules']] == [statement]
    assert rules['extraction_gaps'][0]['path'] == 'SPEC.md'
    with pytest.raises(modules['rule_review'].RulesReviewRequired):
        modules['verification'].verify(context, Model([]))
    authority.approve(context)
    assert 'Unresolved document section' in modules['artifacts'].read(context, authority.published[0][2]['markdown_review']['artifact_path'])['instructions']
    modules['verification'].verify(context, Model([{**judgment('unknown', .2), 'evidence_ids':[]}]))
    modules['reporting'].publish(context)
    report = (context['run_dir'] / 'report.md').read_text()
    assert 'Partial extraction: 1' in report and 'SPEC.md:1–2 | Unknown' in report
    assert modules['artifacts'].read(context, 'final_artifact.json')['coverage']['extraction_gaps'] == rules['extraction_gaps']


def test_repeated_provider_outage_cannot_be_approved_as_an_empty_ruleset(modules, context, authority, monkeypatch):
    from mn_sdk.llm import LLMError
    from domain.extraction_outcome import RuleExtractionFailed
    for number in range(4):
        (Path(context['payload']['input_folder']) / f'other-{number}.md').write_text('A requirement.\n')
    modules['intake'].capture(context)
    monkeypatch.setattr(modules['rules'].time, 'sleep', lambda seconds: None)
    model = Model([LLMError('private unavailable reason')] * 9)
    with pytest.raises(RuleExtractionFailed, match='Verification did not start'):
        modules['rules'].extract(context, model)
    rules = modules['artifacts'].read(context, 'rules.json')
    assert len(model.calls) == 9 and len(rules['extraction_gaps']) == 5 and not rules['rules']
    assert rules['extraction_status'] == 'failed'
    assert [gap['reason'] for gap in rules['extraction_gaps']].count('not_attempted_after_model_failure') == 2
    with pytest.raises(RuleExtractionFailed):
        authority.approve(context)
    monkeypatch.setattr(modules['verification'], 'client', lambda c: pytest.fail('No rules to investigate'))
    with pytest.raises(RuleExtractionFailed):
        modules['verification'].verify(context)
    assert not authority.published
    assert not (context['run_dir'] / 'verification.json').exists()
    assert not (context['run_dir'] / 'report.md').exists()
    assert (context['output_folder'] / 'extraction-status.json').is_file()
    status = modules['artifacts'].read(context, 'extraction-status.json')
    assert status['verification_started'] is False and status['model_failed_sections'] == 3
    replay = Model([])
    with pytest.raises(RuleExtractionFailed):
        modules['rules'].extract(context, replay)
    assert replay.calls == []
    assert 'private unavailable reason' not in (context['run_dir'] / 'rules.json').read_text()


def test_model_failure_diagnostics_preserve_codes_without_provider_content(modules):
    from domain.model import failure_details
    from mn_sdk.llm import LLMError
    from mn_sdk.model_access.errors import ModelPrepareRemoteError
    cause = ModelPrepareRemoteError('model.prepare_failed', 'private provider content', stage='install',
        safe_message='private safe message', details={'remote_message':'private body', 'api_key':'private key'})
    error = LLMError('private wrapped message')
    error.__cause__ = cause
    assert failure_details(error) == {'error_type':'LLMError', 'provider_response_count':0,
                                     'code':'model.prepare_failed', 'stage':'install', 'retryable':False}


def test_failure_diagnostics_handle_cycles_and_invalid_usage(modules):
    from domain.model import failure_details
    from mn_sdk.llm import LLMError
    error = LLMError('private', usage={'provider_response_count':'private'})
    error.__cause__ = error
    assert failure_details(error) == {'error_type':'LLMError', 'provider_response_count':0}


def test_old_empty_rules_approval_cannot_start_verification(modules, context, monkeypatch):
    from domain.extraction_outcome import RuleExtractionFailed
    modules['intake'].capture(context)
    capture = modules['artifacts'].read(context, 'capture.json')
    rules = {'snapshot_id':capture['snapshot_id'], 'rules':[],
             'extraction_gaps':[{'reason':'model_unavailable'}]}
    modules['artifacts'].save(context, 'rules.json', rules)
    monkeypatch.setattr(modules['rule_review'].human_interactions, 'read_interaction_events',
                        lambda run: pytest.fail('Empty failed extraction cannot consume approval authority'))
    monkeypatch.setattr(modules['verification'], 'client', lambda ctx: pytest.fail('No candidates to verify'))
    with pytest.raises(RuleExtractionFailed):
        modules['verification'].verify(context)


def test_failed_extraction_stages_typed_diagnostics(modules, context, monkeypatch):
    from domain.extraction_outcome import RuleExtractionFailed
    from mn_sdk.llm import LLMError
    from mn_sdk.model_access.errors import ModelPrepareRemoteError
    modules['intake'].capture(context)
    monkeypatch.setattr(modules['rules'].time, 'sleep', lambda seconds: None)
    error = LLMError('private provider failure')
    error.__cause__ = ModelPrepareRemoteError('model.prepare_failed', 'private', stage='install')
    with pytest.raises(RuleExtractionFailed):
        modules['rules'].extract(context, Model([error] * 3))
    status = json.loads((context['output_folder'] / 'extraction-status.json').read_text())
    assert status['diagnostic_codes'] == ['model.prepare_failed']
    assert status['unresolved_sections'] == 1 and status['rules'] == 0
    draft = json.loads((context['output_folder'] / 'extraction/drafts/packet-0000-attempt-1.json').read_text())
    assert draft['diagnostic']['stage'] == 'install'
    assert 'private' not in json.dumps(status) + json.dumps(draft)


def test_job_checkpoints_reuse_candidates_but_never_human_approval(modules, context, authority):
    modules['intake'].capture(context)
    modules['rules'].extract(context, Model([extracted()]))
    authority.approve(context)
    context.update(run_id='next-run', job_id='next-execution', run_dir=context['run_dir'].with_name('next-run'))
    modules['intake'].capture(context)
    model = Model([])
    modules['rules'].extract(context, model)
    assert not model.calls and len(modules['artifacts'].read(context, 'rules.json')['rules']) == 2
    assert (context['run_dir'] / 'extraction/reused/packet-0000.json').is_file()
    with pytest.raises(modules['rule_review'].RulesReviewRequired):
        modules['verification'].verify(context, Model([]))


def test_tampered_checkpoint_is_recomputed_and_cache_write_failure_is_optional(modules, context, monkeypatch):
    modules['intake'].capture(context)
    modules['rules'].extract(context, Model([extracted()]))
    checkpoint = next(context['job_data_dir'].glob('cache/code-verifier/extraction/*.json'))
    value = json.loads(checkpoint.read_text())
    value['response']['rules'][0]['quote'] = 'Invented text.'
    checkpoint.write_text(json.dumps(value))
    context.update(run_id='next-run', run_dir=context['run_dir'].with_name('next-run'))
    modules['intake'].capture(context)
    def fail(*args):
        raise OSError('Cache unavailable')
    monkeypatch.setattr(modules['rules'].rule_cache, 'store', fail)
    model = Model([extracted()])
    modules['rules'].extract(context, model)
    assert len(model.calls) == 1
    assert (context['run_dir'] / 'extraction/cache-rejected/packet-0000.json').is_file()
    assert len(modules['artifacts'].read(context, 'rules.json')['rules']) == 2


def test_source_handles_copy_trusted_text_and_repairs_cannot_rewrite_rules(modules, context):
    modules['intake'].capture(context)
    initial = extracted()
    initial['rules'][0]['source_ids'] = ['invalid']
    initial['rules'][1]['quote'] = 'Invented quote supplied by model.'
    repairs = {'repairs':[{'index':0, 'source_ids':extracted()['rules'][0]['source_ids'], 'statement':'Rewritten'}]}
    model = Model([initial, repairs])
    modules['rules'].extract(context, model)
    saved = modules['artifacts'].read(context, 'rules.json')
    assert [r['statement'] for r in saved['rules']] == [r['statement'] for r in extracted()['rules']]
    assert saved['rules'][1]['quote'] == 'The software must not save plaintext passwords.\n'
    assert model.calls[1]['rules_to_correct'] == [{'index':0, 'statement':extracted()['rules'][0]['statement']}]


def test_failed_rule_investigation_does_not_block_next_rule(modules, context, authority):
    from mn_sdk.llm import LLMError
    modules['intake'].capture(context)
    modules['rules'].extract(context, Model([extracted()]))
    authority.approve(context)
    model = Model([LLMError('private outage')] * 3 + [reading(), judgment('fail', .8, quote='store.write(password)')])
    modules['verification'].verify(context, model)
    results = modules['artifacts'].read(context, 'verification.json')['results']
    assert [r['status'] for r in results] == ['unknown', 'fail']
    assert len(model.calls) == 5 and 'private outage' not in json.dumps(results)


@pytest.mark.parametrize('recovers', [False, True])
def test_each_approved_rule_is_investigated_after_prior_model_failures(modules, context, authority, recovers):
    from mn_sdk.llm import LLMError
    (context['job_data_dir'] / 'knowledge/rules/custom.md').write_text(
        '\n\n'.join(f'## R-{n}\n\nA scoped expectation {n}.' for n in range(4)))
    context['config']['review']['rules_mode'] = 'replace'
    modules['intake'].capture(context)
    modules['rules'].extract(context, Model([]))
    authority.approve(context)
    final = [reading(), judgment()] if recovers else [LLMError('Provider unavailable')] * 3
    model = Model([LLMError('Provider unavailable')] * 9 + final)
    modules['verification'].verify(context, model)
    results = modules['artifacts'].read(context, 'verification.json')['results']
    assert len(model.calls) == 9 + len(final) and len(results) == 4
    assert [request['rule']['id'] for request in model.calls] == [
        f'R-{number}' for number in range(4) for _ in range(len(final) if number == 3 else 3)]
    assert all(result['status'] == 'unknown' and result['confidence'] == 0 for result in results[:3])
    assert results[-1]['status'] == ('pass' if recovers else 'unknown')
    for result in results:
        assert result['investigation']
        receipt = modules['artifacts'].read(context, f"verification/{result['rule_id']}.json")
        assert receipt['result'] == result
    modules['verification'].verify(context, Model([]))
    assert modules['artifacts'].read(context, 'verification.json')['results'] == results


def test_saved_unattempted_outage_rows_are_investigated_on_resume(modules, context, authority):
    modules['intake'].capture(context)
    modules['rules'].extract(context, Model([extracted()]))
    authority.approve(context)
    rules = modules['artifacts'].read(context, 'rules.json')
    for rule in rules['rules']:
        result = {**modules['verification'].unknown(rule, 'Model unavailable; rule was not assessed.'),
                  'reason_code': 'model_unavailable'}
        modules['artifacts'].save(context, f"verification/{rule['id']}.json",
                                 {'snapshot_id':rules['snapshot_id'], 'rule':rule, 'result':result})
    model = Model([reading(), judgment(), reading(), judgment()])
    modules['verification'].verify(context, model)
    results = modules['artifacts'].read(context, 'verification.json')['results']
    assert len(model.calls) == 4 and all(result['status'] == 'pass' for result in results)
    modules['verification'].verify(context, Model([]))


def test_investigation_corrects_invalid_evidence_selection(modules, context, authority):
    modules['intake'].capture(context)
    modules['rules'].extract(context, Model([extracted()]))
    authority.approve(context)
    model = Model([{**judgment(), 'evidence_ids':['invented']}, reading(), judgment(),
                   reading(), judgment('fail', .8, quote='store.write(password)')])
    modules['verification'].verify(context, model)
    results = modules['artifacts'].read(context, 'verification.json')['results']
    assert [r['status'] for r in results] == ['pass', 'fail']
    assert 'recovery' in model.calls[1]['observations'][0]
    assert results[0]['evidence'][0]['quote'] == IMPLEMENTATION


def test_context_compaction_keeps_full_audit_and_trusted_evidence(modules, context):
    from mn_code_search_skill import TextSearchIndex
    source = '\n'.join('x' * 7000 for _ in range(6)) + '\n'
    index = TextSearchIndex({'store.py':source})
    span = index.read('store.py', 5, 6)
    handle = 'SRC-' + sha256(json.dumps(['store.py', sha256(source.encode()).hexdigest(), 5, 6]).encode()).hexdigest()[:20]
    model = Model([reading(start=1, end=2), reading(start=3, end=4), reading(start=5, end=6),
                   {**judgment(), 'evidence_ids':[handle]}])
    result = modules['verification'].verify_rule(context, {'id':'R', 'statement':'A scoped rule'}, index,
        {'coverage':{}, 'limitations':[]}, model, files=[{'path':'store.py', 'kind':'implementation'}])
    assert result['status'] == 'pass' and result['evidence'][0]['quote'] == span['text']
    assert len(result['investigation']) == 3
    assert len(model.calls[-1]['observations']) == 1


def test_large_inventory_is_previewed_without_narrowing_search_scope(modules, context):
    from mn_code_search_skill import TextSearchIndex
    inventory = [{'path':f'packages/{n}/' + 'x' * 200 + '.py', 'kind':'implementation'} for n in range(2000)]
    model = Model([{**judgment('unknown', 0), 'evidence_ids':[]}])
    modules['verification'].verify_rule(context, {'id':'R'}, TextSearchIndex({'store.py':IMPLEMENTATION}),
        {'coverage':{}, 'limitations':[]}, model, files=inventory)
    request = model.calls[0]
    assert request['file_inventory']['truncated'] and request['file_inventory']['total'] == 2000
    assert request['file_inventory']['search_covers_all_captured_files'] is True
    assert len(json.dumps(request).encode()) < 30_000


def test_changing_source_prevents_candidate_cache_reuse(modules, context):
    modules['intake'].capture(context)
    modules['rules'].extract(context, Model([extracted()]))
    (Path(context['payload']['input_folder']) / 'store.py').write_text(IMPLEMENTATION + '# changed\n')
    context.update(run_id='new-source', run_dir=context['run_dir'].with_name('new-source'))
    modules['intake'].capture(context)
    model = Model([extracted()])
    modules['rules'].extract(context, model)
    assert len(model.calls) == 1 and not list((context['run_dir'] / 'extraction/reused').glob('*.json'))


def test_no_rules_requires_review_and_publishes_no_conformance_result(modules, context, authority, monkeypatch):
    modules['intake'].capture(context)
    modules['rules'].extract(context, Model([{'complete':True, 'rules':[]}]))
    authority.approve(context)
    assert 'No rules identified' in modules['artifacts'].read(context, authority.published[0][2]['markdown_review']['artifact_path'])['instructions']
    monkeypatch.setattr(modules['verification'], 'client', lambda c: pytest.fail('No candidate rules'))
    modules['verification'].verify(context)
    modules['reporting'].publish(context)
    final = modules['artifacts'].read(context, 'final_artifact.json')
    assert final['assessment_status'] == 'needs_review' and final['results'] == []
    assert 'no conformance result' in (context['run_dir'] / 'report.md').read_text()


def test_optional_web_view_failure_preserves_authoritative_report(modules, context, authority, monkeypatch):
    modules['intake'].capture(context)
    modules['rules'].extract(context, Model([extracted()]))
    authority.approve(context)
    modules['verification'].verify(context, Model([reading(), judgment(), reading(), judgment()]))
    web = importlib.import_module('domain.workspace_web')
    def fail(*args):
        raise RuntimeError('private renderer context')
    monkeypatch.setattr(web, 'render', fail)
    result, refs = modules['reporting'].publish(context)
    assert result['rules'] == 2 and refs
    assert (context['run_dir'] / 'report.md').is_file()
    assert (context['output_folder'] / 'report.md').is_file()
    assert not (context['output_folder'] / 'web_ui.json').exists()
    assert len(modules['artifacts'].read(context, 'final_artifact.json')['results']) == 2
    assert modules['artifacts'].read(context, 'presentation-status.json') == {
        'status':'unavailable', 'error_type':'RuntimeError'}


def test_repeated_quote_can_use_an_exact_numbered_span(modules):
    from mn_code_search_skill import TextSearchIndex
    index = TextSearchIndex({'spec.md':'Same statement.\nSame statement.\n'})
    packet = index.read('spec.md', 1, 2)
    span = modules['rules'].exact_rule_source(index, packet,
        {'quote':'Same statement.', 'start_line':2, 'end_line':2})
    assert span['start_line'] == span['end_line'] == 2


def test_larger_custom_ruleset_can_reach_human_review(modules, context, authority):
    (context['job_data_dir'] / 'knowledge/rules/custom.md').write_text(
        '\n\n'.join(f'## R-{n}\n\nThe software must satisfy custom expectation {n}.' for n in range(201)))
    context['config']['review']['rules_mode'] = 'replace'
    modules['intake'].capture(context)
    modules['rules'].extract(context, Model([]))
    assert len(modules['artifacts'].read(context, 'rules.json')['rules']) == 201
    receipt, _ = authority.approve(context)
    assert receipt['status'] == 'approved'


@pytest.mark.parametrize('scope', ['project_docs', 'all_captured_docs'])
def test_doc_selection_preserves_legitimate_specs_and_docs(modules, scope):
    paths = ['spec.md', 'docs/design.rst', 'packages/lib/SPEC.md', 'plain.txt',
             'docs/test-results-policy.md', 'nested/Benchmark-Results/REPORT.md']
    selection = modules['rules'].select_documents({'documents': paths}, scope)
    assert selection['selected_documents'] == (paths[:-1] if scope == 'project_docs' else paths)
    assert len(selection['excluded_documents']) == (1 if scope == 'project_docs' else 0)


@pytest.mark.parametrize('key,value', [('max_extraction_packets', 0), ('max_extraction_packets', 2049),
                                      ('max_extraction_packets', True), ('documentation_scope', 'unknown'),
                                      ('max_extraction_attempts', 0), ('max_extraction_attempts', 4),
                                      ('max_extraction_attempts', True)])
def test_document_policy_validation(modules, context, key, value):
    context['config']['review'][key] = value
    with pytest.raises(ValueError, match=key):
        modules['configuration'].settings(context)


@pytest.mark.parametrize('responses', [
    [judgment()],  # unread citation
    [reading(), judgment(quote='fabricated')],
    [reading(), judgment(score=math.nan)],
    [reading(), judgment(score=True)],
    [reading(), judgment(score=1.1)],
    [reading(), {**judgment(), 'evidence_ids': [None]}],
    [{'action': 'run', 'command': 'touch forbidden'}],
    [TimeoutError('private-provider-message')],
    [{'action': 'read', 'path': '../private', 'start_line': 1, 'end_line': 1}],
])
def test_unsafe_or_invalid_verification_is_unknown(modules, context, responses, authority):
    modules['intake'].capture(context)
    modules['rules'].extract(context, Model([extracted()]))
    authority.approve(context)
    context['config']['review']['max_turns_per_rule'] = len(responses)
    # Both rules get independent responses; no exception leaks private diagnostics.
    modules['verification'].verify(context, Model(responses + responses))
    results = modules['artifacts'].read(context, 'verification.json')['results']
    assert all(r['status'] == 'unknown' and r['confidence'] == 0 for r in results)
    assert 'private-provider-message' not in json.dumps(results)


def test_documentation_and_tests_alone_cannot_pass(modules):
    from mn_code_search_skill import TextSearchIndex
    index = TextSearchIndex({'docs/a.md': 'good\n', 'tests/a.py': 'assert True\n'})
    for path, quote in [('docs/a.md', 'good'), ('tests/a.py', 'assert True')]:
        span = index.read(path, 1, 1)
        result = judgment(path=path, quote=quote)
        result['evidence'][0].update(start_line=1, end_line=1)
        admitted = modules['verification'].admit(result, {'id': 'R'}, index, [span])
        assert admitted['status'] == 'unknown' and admitted['confidence'] == .49


def test_budget_exhaustion_and_no_evidence_are_unknown(modules, context, authority):
    modules['intake'].capture(context)
    modules['rules'].extract(context, Model([extracted()]))
    authority.approve(context)
    context['config']['review']['max_turns_per_rule'] = 1
    modules['verification'].verify(context, Model([{'action': 'search', 'query': 'missing'}] * 2))
    results = modules['artifacts'].read(context, 'verification.json')['results']
    assert len(results) == 2 and all(r['status'] == 'unknown' for r in results)
    assert all('limit' in r['explanation'] for r in results)


def test_capture_exclusions_and_source_budgets(modules, tmp_path):
    (tmp_path / 'ok.py').write_text('pass\n')
    (tmp_path / '.env').write_text('PRIVATE=value')
    (tmp_path / 'secrets.json').write_text('private')
    (tmp_path / 'link.py').symlink_to(tmp_path / 'ok.py')
    (tmp_path / 'node_modules').mkdir()
    (tmp_path / 'node_modules/vendor.py').write_text('vendor')
    (tmp_path / 'huge.md').write_text('x' * 500_001)
    sources, skipped = modules['intake'].capture_folder(tmp_path)
    assert set(sources) == {'ok.py'}
    assert {s['path'] for s in skipped} == {'.env', 'secrets.json', 'link.py', 'node_modules', 'huge.md'}
    with pytest.raises(ValueError, match='budget'):
        modules['intake'].capture_folder(tmp_path, max_bytes=1)


def test_job_knowledge_and_output_boundaries(modules, context):
    context['job_id'] = ''
    with pytest.raises(ValueError, match='Job'):
        modules['intake'].capture(context)
    context['job_id'] = 'job'
    context['run_dir'] = Path(context['payload']['input_folder']) / 'outputs'
    with pytest.raises(ValueError, match='outside'):
        modules['intake'].capture(context)


def test_partial_capture_recovers_static_artifact(modules, context):
    modules['intake'].capture(context)
    (context['run_dir'] / 'static-analysis.json').unlink()
    modules['intake'].capture(context)
    assert modules['artifacts'].read(context, 'static-analysis.json')['coverage']['files'] == 1


def test_rule_limit_preserves_every_row_and_marks_unassessed_rules_unknown(modules, context, authority):
    modules['intake'].capture(context)
    context['config']['review']['max_rules'] = 1
    modules['rules'].extract(context, Model([extracted()]))
    authority.approve(context)
    assert 'Verification budget' in modules['artifacts'].read(context, authority.published[0][2]['markdown_review']['artifact_path'])['instructions']
    model = Model([reading(), judgment()])
    modules['verification'].verify(context, model)
    results = modules['artifacts'].read(context, 'verification.json')['results']
    assert len(results) == 2 and [r['status'] for r in results] == ['pass', 'unknown']
    assert len(model.calls) == 2 and results[1]['confidence'] == 0


def test_catalog_compiles_and_boundary_contracts():
    from mn_sdk.blueprints import blueprint_definition, compile_blueprint, read_blueprint
    package = read_blueprint(PACKAGE)
    definition = blueprint_definition(package)
    assert definition['response_service'] == {'enabled': True}
    assert definition['mcp']['profile'] == 'mn.mcp.supervision.v1'
    assert definition['metadata']['web_ui']['adapter'] == 'static_html'
    compiled = compile_blueprint(package).manifest
    assert len(compiled['workflow']['steps']) == 5
    steps = {s['id']: s for s in definition['workflow']['steps']}
    assert steps['review_software_rules']['needs'] == ['extract_software_rules']
    assert steps['verify_software_rules']['needs'] == ['review_software_rules']
    registry = definition['agents']['registry']
    assert set(registry).isdisjoint(s['id'] for s in definition['workflow']['steps'])
    for ident in registry:
        assert (PACKAGE / f'payloads/agents/{ident}.py').is_file()
    for path in (PACKAGE / 'payloads').rglob('*.py'):
        tree = ast.parse(path.read_text())
        if path.parent.name == 'steps':
            assert not any(isinstance(n, ast.ImportFrom) and (n.module or '').startswith('domain') for n in ast.walk(tree))
        if path.parent.name == 'runtime':
            assert 'domain.' not in path.read_text() and 'agents.' not in path.read_text()
    assert not (PACKAGE / 'payloads/agents/domain.py').exists()


def test_platform_stages_source_and_markdown_before_capture(context, modules):
    from types import SimpleNamespace
    from mn_sdk.blueprint_support.local_inputs import stage_local_input_payloads
    config = context['config']
    config['inputs']['payload']['input_folder'] = context['payload']['input_folder']
    declared = set(config['local_inputs']['folders'][0]['allowed_extensions'])
    assert modules['intake'].TEXT_EXTENSIONS <= declared
    payloads = {}
    summary = stage_local_input_payloads(config, payloads, bundle_dir=PACKAGE)
    assert summary['folders'][0]['file_count'] == 2
    assert set(payloads) == {'runtime/mn_local_inputs/software_sources/SPEC.md',
                             'runtime/mn_local_inputs/software_sources/store.py'}
    assert config['inputs']['payload']['input_folder'] == 'mn_local_inputs/software_sources'
    worker = context['run_dir'].parent / 'worker'
    for path, data in payloads.items():
        target = worker / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    context['bundle_layout'] = SimpleNamespace(runtime_dir=worker / 'runtime')
    context['payload']['input_folder'] = config['inputs']['payload']['input_folder']
    modules['intake'].capture(context)
    captured = modules['artifacts'].read(context, 'capture.json')
    assert captured['documents'] == ['SPEC.md']
    assert captured['sources']['store.py'].startswith('def save(')


def test_deadline_keeps_every_rule_without_extra_model_calls(modules, context, monkeypatch, authority):
    modules['intake'].capture(context)
    modules['rules'].extract(context, Model([extracted()]))
    authority.approve(context)
    ticks = iter([0, 4000, 4001])
    monkeypatch.setattr(modules['verification'].time, 'monotonic', lambda: next(ticks))
    model = Model([])
    modules['verification'].verify(context, model)
    results = modules['artifacts'].read(context, 'verification.json')['results']
    assert len(results) == 2
    assert all(r['status'] == 'unknown' and 'time limit' in r['explanation'] for r in results)
    assert not model.calls


def test_report_rejects_missing_rule_and_changed_capture(modules, context):
    modules['intake'].capture(context)
    modules['rules'].extract(context, Model([extracted()]))
    snapshot = modules['artifacts'].read(context, 'capture.json')['snapshot_id']
    modules['artifacts'].save(context, 'verification.json', {'snapshot_id': snapshot, 'results': []})
    with pytest.raises(ValueError, match='exactly one'):
        modules['reporting'].publish(context)
    rules = modules['artifacts'].read(context, 'rules.json')
    rules['snapshot_id'] = 'different'
    modules['artifacts'].save(context, 'rules.json', rules)
    with pytest.raises(ValueError, match='do not match'):
        modules['verification'].verify(context, Model([]))


def test_registry_handlers_resolve_to_callables(modules):
    execution = json.loads((PACKAGE / 'execution.json').read_text())
    for spec in execution['agents']['registry'].values():
        assert callable(importlib.import_module(spec['handler']).run)


def prepare_rules(modules, context):
    modules['intake'].capture(context)
    modules['rules'].extract(context, Model([extracted()]))


def test_no_verification_before_human_decision(modules, context, authority):
    prepare_rules(modules, context)
    model = Model([])
    with pytest.raises(modules['rule_review'].RulesReviewRequired, match='approve the saved rules'):
        modules['verification'].verify(context, model)
    assert not model.calls
    assert not (context['run_dir'] / 'verification.json').exists()
    authority.before_response = lambda: (
        pytest.fail('Verification started before the human replied')
        if (context['run_dir'] / 'verification.json').exists() else None)
    receipt, refs = authority.approve(context)
    request = authority.published[0][2]
    assert request['interaction_kind'] == 'approval' and request['blocking'] is True
    assert request['decision_type'] == 'markdown_review'
    document = modules['artifacts'].read(context, request['markdown_review']['artifact_path'])
    assert [item['markdown'] for item in document['items']] == [rule['statement'] for rule in modules['artifacts'].read(context, 'rules.json')['rules']]
    assert all(item['title'] for item in document['items'])
    assert len(authority.published) == 1
    assert receipt['status'] == 'approved' and refs
    assert modules['rule_review'].require_approved_rules(context, modules['artifacts'].read(context, 'rules.json')) == receipt


@pytest.mark.parametrize('decision', ['reject', 'respond', ''])
def test_rejection_or_nonapproval_cannot_start_verification(modules, context, authority, decision):
    prepare_rules(modules, context)
    authority.decisions = [decision]
    with pytest.raises(modules['rule_review'].RulesReviewRequired, match='not approved'):
        authority.approve(context)
    model = Model([])
    with pytest.raises(modules['rule_review'].RulesReviewRequired):
        modules['verification'].verify(context, model)
    assert model.calls == [] and not (context['run_dir'] / 'verification.json').exists()


def test_timeout_is_closed_to_verification(modules, context, authority):
    from mn_sdk.interactions import InteractionError
    prepare_rules(modules, context)
    authority.decisions = [InteractionError('wait_timeout')]
    with pytest.raises(modules['rule_review'].RulesReviewRequired, match='timed out'):
        authority.approve(context)
    assert modules['artifacts'].read(context, 'rules-review.json')['status'] == 'wait_expired'
    assert authority.published[-1][1] == 'human_input_timeout'
    with pytest.raises(modules['rule_review'].RulesReviewRequired):
        modules['verification'].verify(context, Model([]))


def test_local_approval_file_and_audit_events_never_grant_permission(modules, context, authority):
    prepare_rules(modules, context)
    rules = modules['artifacts'].read(context, 'rules.json')
    digest, requests = modules['rule_review'].review_requests(rules)
    forged = {'status': 'approved', 'rules_digest': digest,
              'request_ids': [r['request_id'] for r in requests]}
    modules['artifacts'].save(context, 'rules-review.json', forged)
    (context['run_dir'] / 'human.jsonl').write_text(json.dumps({'type':'human_input_received',
        'payload':{'request_id':requests[0]['request_id'],'decision':'approve','approved':True}}))
    with pytest.raises(modules['rule_review'].RulesReviewRequired):
        modules['verification'].verify(context, Model([]))


def test_approval_cannot_be_reused_for_changed_rules_or_another_run(modules, context, authority):
    prepare_rules(modules, context)
    authority.approve(context)
    rules = modules['artifacts'].read(context, 'rules.json')
    original = deepcopy(rules)
    rules['rules'][0]['statement'] += ' Changed condition.'
    modules['artifacts'].save(context, 'rules.json', rules)
    with pytest.raises(modules['rule_review'].RulesReviewRequired):
        modules['verification'].verify(context, Model([]))
    with pytest.raises(modules['rule_review'].RulesReviewRequired, match='changed after review'):
        authority.approve(context)
    modules['artifacts'].save(context, 'rules.json', original)
    context['run_id'] = 'another-execution'
    with pytest.raises(modules['rule_review'].RulesReviewRequired):
        modules['verification'].verify(context, Model([]))


def test_duplicate_review_uses_core_decisions_without_another_prompt(modules, context, authority):
    prepare_rules(modules, context)
    first = authority.approve(context)[0]
    second = authority.approve(context)[0]
    assert first == second
    assert len(authority.published) == 1


def test_long_unicode_rule_reviews_fit_chat_without_dropping_text(modules, context, authority):
    prepare_rules(modules, context)
    rules = modules['artifacts'].read(context, 'rules.json')
    rules['rules'][0]['statement'] = '界' * 1333
    rules['rules'][1]['statement'] = 'x' * 4000
    modules['artifacts'].save(context, 'rules.json', rules)
    _, requests = modules['rule_review'].review_requests(rules)
    assert len(requests) == 1
    request = requests[0]
    assert len(json.dumps(request).encode()) < 8000
    authority.decisions = ['reject']
    with pytest.raises(modules['rule_review'].RulesReviewRequired):
        authority.approve(context)
    reference = request['markdown_review']
    raw = (context['run_dir'] / reference['artifact_path']).read_bytes()
    assert sha256(raw).hexdigest() == reference['sha256']
    document = json.loads(raw)
    assert [item['markdown'] for item in document['items']] == [rule['statement'] for rule in rules['rules']]
    assert all(len(item['title']) <= 120 for item in document['items'])
    with pytest.raises(modules['rule_review'].RulesReviewRequired):
        modules['verification'].verify(context, Model([]))


def test_authority_failure_does_not_substitute_approval(modules, context, authority, monkeypatch):
    from mn_sdk.interactions import InteractionError
    prepare_rules(modules, context)
    def disconnected(*args, **kwargs):
        raise InteractionError('store_unavailable')
    monkeypatch.setattr(modules['rule_review'].human_interactions, 'read_interaction_events', disconnected)
    with pytest.raises(InteractionError, match='store_unavailable'):
        modules['verification'].verify(context, Model([]))


def test_real_sdk_adapter_publishes_a_bound_conversation_request(modules, context, monkeypatch):
    from contextlib import contextmanager
    from types import SimpleNamespace
    import time
    prepare_rules(modules, context)
    records = {}

    class Interactions:
        def snapshot(self):
            return {'items': list(records.values())}

        def publish(self, **values):
            record = {**values, 'id': values['interaction_id'], 'created_at': int(time.time() * 1000),
                      'updated_at': int(time.time() * 1000), 'state': 'pending', 'effect': 'none'}
            records[record['id']] = record
            return record

        def await_decision(self, ident, *, timeout):
            record = records[ident]
            record['state'] = 'responded'
            record['receipt'] = {'answer': {'option_id': 'approve'}, 'received_at': int(time.time() * 1000)}
            return record

    @contextmanager
    def connected():
        record = {'job_id': 'stable-job', 'run_id': 'execution-1', 'run_data_ref': {'run_id': 'run-1'}}
        yield SimpleNamespace(get_run=lambda execution_id: json.dumps(record),
                              list_runs=lambda *args, **kwargs: json.dumps({'job_id': 'stable-job', 'items': [record], 'next_page_token': None})), Interactions()

    monkeypatch.setenv('MN_JOB_ID', 'stable-job')
    monkeypatch.setattr(modules['rule_review'].human_interactions, 'runtime_interactions', connected)
    receipt = modules['rule_review'].review(context)[0]
    assert receipt['status'] == 'approved'
    record, = records.values()
    assert record['scope'] == {'job_id':'stable-job','execution_id':'execution-1','runtime_run_id':'run-1'}
    assert record['kind'] == 'approval' and record['presentation']['widget'] == 'confirmation'
    assert record['metadata']['blocking'] is True
    assert record['metadata']['request_id'] in receipt['request_ids']
    assert not (context['run_dir'] / 'human.jsonl').exists()
    events = modules['rule_review'].human_interactions.read_interaction_events(context['run_id'])
    assert events[-1]['type'] == 'human_input_received'
    assert events[-1]['payload']['decision'] == 'approve'


def test_editing_a_rule_requires_a_fresh_review_and_changes_the_verification_input(modules, context, authority):
    prepare_rules(modules, context)
    original = modules['artifacts'].read(context, 'rules.json')
    edit = {'id': original['rules'][0]['id'], 'title': 'Reject blank names',
            'markdown': 'The software **must reject** a blank name.\n\n- Preserve completed work.'}
    authority.decisions = [{'decision': 'revise', 'notes': json.dumps(edit)}, 'approve']
    seen = []
    def before():
        current = modules['artifacts'].read(context, 'rules.json')
        seen.append(current)
        with pytest.raises(modules['rule_review'].RulesReviewRequired):
            modules['rule_review'].require_approved_rules(context, current)
    authority.before_response = before
    receipt = authority.approve(context)[0]
    assert len(seen) == 2 and len(authority.published) == 2
    first, second = [row[2] for row in authority.published]
    assert first['rules_digest'] != second['rules_digest']
    assert second['review_revision'] == 2
    current = modules['artifacts'].read(context, 'rules.json')
    changed = current['rules'][0]
    assert changed['statement'] == edit['markdown'] and changed['title'] == edit['title']
    assert changed['origin'] == 'supervisor' and changed['source'] == original['rules'][0]['source']
    assert edit['markdown'] in (context['run_dir'] / 'rules.md').read_text()
    assert receipt['request_ids'] == [second['request_id']]
    reviewer = Model([{'action': 'finish', 'status': 'unknown', 'explanation': 'Insufficient source coverage.', 'evidence_ids': [], 'confidence': 0}] * 2)
    modules['verification'].verify(context, reviewer)
    assert reviewer.calls[0]['rule']['statement'] == edit['markdown']
    assert modules['artifacts'].read(context, 'reviews/original-rules.json') == original


@pytest.mark.parametrize('notes', ['not json', '{}', json.dumps({'id':'MISSING', 'title':'Title', 'markdown':'A rule.'})])
def test_invalid_edit_keeps_rules_and_requests_review_again(modules, context, authority, notes):
    prepare_rules(modules, context)
    original = modules['artifacts'].read(context, 'rules.json')
    authority.decisions = [{'decision':'revise', 'notes':notes}, 'approve']
    authority.approve(context)
    assert modules['artifacts'].read(context, 'rules.json') == original
    assert len(authority.published) == 2
    assert authority.published[1][2]['review_revision'] == 2


def test_review_resume_recovers_an_edit_committed_before_plan_write(modules, context, authority, monkeypatch):
    prepare_rules(modules, context)
    original = modules['artifacts'].read(context, 'rules.json')
    edit = {'id':original['rules'][0]['id'], 'title':'Updated rule', 'markdown':'The supervisor expects a safe default.'}
    authority.decisions = [{'decision':'revise', 'notes':json.dumps(edit)}]
    save = modules['rule_review'].save
    def interrupted(ctx, name, value):
        if name == 'rules-review-request.json' and value.get('next_revision') == 2:
            raise OSError('simulated interruption after rules commit')
        return save(ctx, name, value)
    monkeypatch.setattr(modules['rule_review'], 'save', interrupted)
    with pytest.raises(OSError):
        authority.approve(context)
    current = modules['artifacts'].read(context, 'rules.json')
    assert current['rules'][0]['statement'] == edit['markdown']
    with pytest.raises(modules['rule_review'].RulesReviewRequired):
        modules['rule_review'].require_approved_rules(context, current)
    monkeypatch.setattr(modules['rule_review'], 'save', save)
    receipt = authority.approve(context)[0]
    assert receipt['status'] == 'approved'
    assert len(authority.published) == 2


def test_large_review_contains_every_rule_in_one_hashed_manifest(modules, context, authority):
    prepare_rules(modules, context)
    rules = modules['artifacts'].read(context, 'rules.json')
    base = rules['rules'][0]
    rules['rules'] = [{**deepcopy(base), 'id':f'RULE-{i}', 'statement':f'The software must preserve requirement {i}.'} for i in range(1783)]
    modules['artifacts'].save(context, 'rules.json', rules)
    authority.approve(context)
    assert len(authority.published) == 1
    request = authority.published[0][2]
    assert request['markdown_review']['item_count'] == 1783
    document = modules['artifacts'].read(context, request['markdown_review']['artifact_path'])
    assert len(document['items']) == 1783
    assert document['items'][-1]['markdown'] == rules['rules'][-1]['statement']


def test_titled_markdown_round_trips_into_custom_knowledge(modules):
    rules = [{'id':'CUSTOM-1', 'title':'Protect stored secrets', 'statement':'The software **must not** store plaintext passwords.\n\n- Use encrypted storage.'},
             {'id':'CUSTOM-2', 'statement':'The software should support cancellation.'}]
    output = modules['rules'].markdown(rules)
    parsed = modules['rules'].custom_rules('knowledge/rules/custom.md', output)
    assert [r['id'] for r in parsed] == [r['id'] for r in rules]
    assert [r['statement'] for r in parsed] == [r['statement'] for r in rules]
    assert parsed[0]['title'] == rules[0]['title']
    assert parsed[1]['title'] == 'Support cancellation'
    assert modules['rules'].markdown(parsed) == output


def test_a_new_pending_review_invalidates_even_a_matching_older_approval(modules, context, authority):
    prepare_rules(modules, context)
    authority.approve(context)
    rules = modules['artifacts'].read(context, 'rules.json')
    _, requests = modules['rule_review'].review_requests(rules, revision=2)
    authority.publish(context['run_id'], 'human_input_requested', requests[0])
    with pytest.raises(modules['rule_review'].RulesReviewRequired):
        modules['rule_review'].require_approved_rules(context, rules)
