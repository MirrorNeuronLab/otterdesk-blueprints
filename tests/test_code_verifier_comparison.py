"""Exercise two Git snapshots, exact approvals and imported JUnit observations."""
from hashlib import sha256
import importlib
import json
from pathlib import Path
import subprocess
import sys

from mn_code_search_skill import TextSearchIndex
from mn_sdk.blueprint_support.local_inputs import stage_local_input_payloads
import pytest

from test_code_verifier import PACKAGE, Model, authority, context, judgment, modules, phase_inputs
from test_code_verifier_quality import finish_for

BASE_SOURCE = 'def save(name, store):\n    if not name:\n        raise ValueError("name required")\n    store.write(name)\n'
HEAD_SOURCE = 'def save(name, store):\n    store.write(name)\n'
REQUIREMENT = 'The software must reject an empty name.'
TEST_NAME = 'suite.TestNames::rejects_empty'
CHECK = 'Call save with an empty name. Expect ValueError and verify the store receives zero writes.'


def git(repo, *args):
    return subprocess.check_output(['git', '-C', str(repo), '-c', 'user.name=Code verifier test',
        '-c', 'user.email=example@example.invalid', '-c', 'commit.gpgsign=false',
        '-c', f'core.hooksPath={repo / "hooks-disabled"}', '-c', 'core.autocrlf=false', *args]).decode().strip()


@pytest.fixture
def repository(tmp_path):
    repo = tmp_path / 'git-input'
    repo.mkdir()
    git(repo, 'init', '-q')
    (repo / 'src').mkdir()
    (repo / 'src/save.py').write_text(BASE_SOURCE)
    (repo / 'src/common.py').write_text('def complete():\n    return True\n')
    (repo / 'manuals').mkdir()
    (repo / 'manuals/SPEC.md').write_text(REQUIREMENT + '\n')
    (repo / 'README.md').write_text('Irrelevant documentation.\n')
    (repo / 'secrets-example.json').write_text('{}')
    git(repo, 'add', '--force', '.')
    git(repo, 'commit', '-qm', 'Base')
    base = git(repo, 'rev-parse', 'HEAD')
    (repo / 'src/save.py').write_text(HEAD_SOURCE)
    git(repo, 'commit', '-qam', 'Proposed change')
    head = git(repo, 'rev-parse', 'HEAD')
    (repo / 'src/save.py').write_text('uncommitted changes')
    return repo, base, head


def prepare(tmp_path, repository, *extra):
    repo, base, head = repository
    folder = tmp_path / 'prepared-comparison'
    subprocess.run([sys.executable, '-B', str(PACKAGE / 'scripts/prepare_comparison.py'),
        '--repo', str(repo), '--base', base, '--head', head, '--output', str(folder), *extra],
        check=True, capture_output=True)
    return folder


def stage(folder, context, monkeypatch):
    config = context.config
    config['inputs']['payload']['input_folder'] = str(folder)
    payloads = {}
    stage_local_input_payloads(config, payloads, bundle_dir=PACKAGE)
    worker = context.store.run_dir.parent / 'worker'
    for path, data in payloads.items():
        target = worker / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    monkeypatch.setenv('MN_WORKDIR', str(worker / 'runtime'))
    return config['inputs']['payload']['input_folder']


def test_git_review_reports_source_regression_and_commit_bound_ci(modules, context, authority, repository, tmp_path, monkeypatch):
    rule_id = modules['rules'].generated_id('manuals/SPEC.md', REQUIREMENT,
        ('software', 'product', 'must', (), 'behavior'))
    junit = tmp_path / 'ci-results.xml'
    junit.write_text('<testsuite><testcase classname="suite.TestNames" name="rejects_empty"><failure>'
                     'private logs</failure></testcase></testsuite>')
    rule_map = tmp_path / 'ci-map.json'
    rule_map.write_text(json.dumps({rule_id: [TEST_NAME], 'OTHER-RULE': ['missing']}))
    _, base, head = repository
    folder = prepare(tmp_path, repository, '--include', 'src', '--include', 'manuals',
                     '--junit', str(junit), '--rule-map', str(rule_map), '--ci-commit', head)
    assert (folder / 'base/src/save.py').read_text() == BASE_SOURCE
    assert (folder / 'head/src/save.py').read_text() == HEAD_SOURCE
    assert not (folder / 'head/README.md').exists()
    assert 'private logs' not in (folder / 'code-verifier-comparison.json').read_text()
    context.config['review']['spec_paths'] = 'manuals/*.md'
    staged = stage(folder, context, monkeypatch)
    modules['intake'].capture(context, {'input_folder': staged})
    capture = modules['artifacts'].read(context, 'capture.json')
    assert capture['comparison']['base']['commit'] == base
    assert capture['comparison']['head']['commit'] == head
    assert capture['comparison']['changes'] == [{'path': 'src/save.py', 'kind': 'modified'}]
    assert context.store.read(capture['baseline_capture'])['src/common.py'] == capture['sources']['src/common.py']
    rule = {'statement': REQUIREMENT, 'source_ids': [f'L1-{sha256((REQUIREMENT + chr(10)).encode()).hexdigest()[:12]}'],
            'subject': 'software', 'scope': 'product', 'modality': 'must', 'conditions': [], 'requirement_kind': 'behavior'}
    modules['rules'].extract(context, phase_inputs(context), llm=Model([{'complete': True, 'rules': [rule]}]))
    with pytest.raises(modules['rule_review'].RulesReviewRequired):
        modules['verification'].verify(context, phase_inputs(context), llm=Model([]))
    approval = authority.approve(context)
    review = authority.published[0][2]['markdown_review']['artifact_path']
    assert head[:12] in context.store.read_path(review)['instructions']
    assert 'CI test mappings' in context.store.read_path(review)['instructions']

    verify = modules['verification']
    head_ref = TextSearchIndex({'src/save.py': HEAD_SOURCE}).read('src/save.py', 1, 2)
    base_ref = TextSearchIndex({'src/save.py': BASE_SOURCE}).read('src/save.py', 1, 4)
    fail = finish_for(verify, head_ref, status='fail')
    fail.update(explanation='An empty name reaches the store.', recommended_check=CHECK)
    model = Model([fail, finish_for(verify, base_ref)])
    result = verify.verify(context, {'previous': approval}, llm=model)
    assert [call['revision_under_review'] for call in model.calls if 'revision_under_review' in call] == [head, base]
    assert len(model.calls) == 4
    assert verify.verify(context, {'previous': approval}, llm=Model([])) == result
    modules['reporting'].publish(context, {'previous': result})

    final = context.store.read_path('final_artifact.json')
    assert final['comparison']['summary'] == {'regression': 1}
    assert final['attention_rule_ids'] == [rule_id]
    assert final['results'][0]['baseline']['evidence'][0]['text'] == BASE_SOURCE
    assert final['results'][0]['recommended_check'] == CHECK
    assert final['ci_evidence']['checks'] == [
        {'rule_id': rule_id, 'test': TEST_NAME, 'status': 'failed', 'mapping': 'linked'},
        {'rule_id': 'OTHER-RULE', 'test': 'missing', 'status': 'missing', 'mapping': 'rule_missing'},
    ]
    assert final['results'][0]['tests_executed'] is False
    report = context.resources['output_folder'] / 'report.md'
    assert '## What needs attention' in report.read_text()
    assert 'baseline/source/src/save.py#L1' in report.read_text()
    assert (context.resources['output_folder'] / 'baseline/source/src/save.py').read_text() == BASE_SOURCE
    assert (context.resources['output_folder'] / 'web/index.html').is_file()


def test_bad_comparison_and_unknown_spec_fail_before_model_work(modules, context, repository, tmp_path):
    folder = prepare(tmp_path, repository)
    assert not (folder / 'head/secrets-example.json').exists()
    (folder / 'head/src/save.py').write_text('changed after preparation')
    with pytest.raises(ValueError, match='differs from the prepared comparison'):
        modules['intake'].capture(context, {'input_folder': str(folder)})
    (folder / 'head/src/save.py').write_text(HEAD_SOURCE)
    modules['intake'].capture(context, {'input_folder': str(folder)})
    context.config['review']['spec_paths'] = 'does-not-exist.md'
    model = Model([])
    with pytest.raises(ValueError, match='does-not-exist.md'):
        modules['rules'].extract(context, phase_inputs(context), llm=model)
    assert not model.calls


def test_junit_receipts_keep_missing_skipped_and_mixed_explicit(modules, tmp_path):
    ci = importlib.import_module('domain.ci_evidence')
    report = tmp_path / 'reports.xml'
    mapping = tmp_path / 'mapping.json'
    report.write_text('<testsuites><testsuite><testcase name="repeat"><failure>log</failure></testcase>'
                      '<testcase name="repeat"/><testcase name="skip"><skipped/></testcase>'
                      '</testsuite></testsuites>')
    mapping.write_text(json.dumps({'RULE-1': ['repeat', 'skip', 'absent']}))
    data = ci.junit_receipt(report, mapping, 'a' * 40)
    assert [check['status'] for check in data['checks']] == ['mixed', 'skipped', 'missing']
    with pytest.raises(ValueError, match='exact proposed Git commit'):
        ci.validate_ci(data, 'b' * 40)
    report.write_text('<!DOCTYPE suite [<!ENTITY local "ignore">]><testsuite/>')
    with pytest.raises(ValueError, match='without DTDs'):
        ci.junit_receipt(report, mapping, 'a' * 40)


@pytest.mark.parametrize('base,head,changed,expected', [
    ('pass', 'fail', True, 'regression'),
    ('fail', 'fail', False, 'existing_failure'),
    ('unknown', 'fail', True, 'needs_baseline'),
    ('pass', 'fail', False, 'needs_change_evidence'),
    ('pass', 'unknown', True, 'inconclusive'),
    ('fail', 'pass', True, 'resolved'),
    ('pass', 'pass', True, 'unchanged'),
])
def test_comparison_does_not_claim_unproven_regressions(modules, base, head, changed, expected):
    change_status = importlib.import_module('domain.git_comparison').change_status
    assert change_status(base, head, cites_change=changed) == expected


def test_ci_mapping_needs_review_after_a_statement_edit(modules):
    ci_view = importlib.import_module('domain.report_findings').ci_view
    rule = {'id': 'R', 'statement': 'Original', 'source': {'path': 'SPEC.md', 'start_line': 1, 'end_line': 1}}
    comparison = {'ci': {'checks': [{'rule_id': 'R', 'test': TEST_NAME, 'status': 'passed'}]}}
    review = importlib.import_module('domain.rule_document')
    edit = {'id': 'R', 'title': 'Retitled', 'markdown': 'Original'}
    renamed = review.apply_edit({'rules': [rule]}, json.dumps(edit), {'request_id': 'R1', 'rules_digest': 'abc'})
    assert ci_view(comparison, renamed['rules'])['checks'][0]['mapping'] == 'linked'
    edit['markdown'] = 'Changed behavior'
    revised = review.apply_edit(renamed, json.dumps(edit), {'request_id': 'R2', 'rules_digest': 'def'})
    assert ci_view(comparison, revised['rules'])['checks'][0]['mapping'] == 'rule_edited'
