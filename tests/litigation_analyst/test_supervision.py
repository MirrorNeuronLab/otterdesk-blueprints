"""Question timing, evidence boundaries and compact handoff without live models."""
from copy import deepcopy
import json

import pytest
from test_reading_view import workspace  # noqa: F401
from test_litigation_analyst import BLUEPRINT, modules  # noqa: F401


def test_conflicting_claims_are_questioned_before_ordinary_drafts(workspace):
    from domain.workspace_review import attach
    from domain.supervision import chat_summary, markdown
    before = deepcopy(workspace['findings'])
    result = attach(workspace)
    handoff = result['supervision']
    assert handoff['next_review']['kind'] == 'consistency'
    assert handoff['next_review']['evidence_ids']
    assert handoff['retained_finding_ids'] == ['qualified']
    assert workspace['findings'] == before
    summary = chat_summary(result)
    assert [r['title'] for r in summary['highlights']] == ['Bank settlement unresolved']
    assert 'No written approval is visible' not in json.dumps(summary)
    assert summary['review']['question'] == handoff['next_review']['question']
    assert 'does not approve' in markdown(result)
    assert 'transaction_appendix.md#evidence-' in markdown(result)
    assert result['reading_reports'][0]['markdown'].index('## Your next review') < result['reading_reports'][0]['markdown'].index('## What the transaction records show')


@pytest.mark.parametrize('state', ['Needs reassessment', 'Reviewers disagree'])
def test_changed_or_disputed_review_precedes_an_ordinary_draft(workspace, state):
    from domain.supervision import build
    workspace['financial_review'] = {'events': [], 'evidence': []}
    ordinary = deepcopy(workspace['findings'][-1])
    ordinary.update(id='ordinary', review_state='AI draft')
    changed = deepcopy(ordinary)
    changed.update(id='changed', title='Changed source basis', review_state=state)
    workspace['findings'] = [ordinary, changed]
    before = deepcopy(workspace)
    result = build(workspace)
    assert result['next_review']['finding_id'] == 'changed'
    assert set(result['next_review']['evidence_ids']) == set(changed['supporting_evidence'])
    assert workspace == before


def test_handling_question_cannot_clear_restricted_material(workspace):
    from domain.supervision import build
    workspace['gaps'] = [{'id': 'handling', 'work_type': 'handling_review', 'source_evidence_ids': []}]
    result = build(workspace)
    assert result['next_review']['kind'] == 'handling'
    assert 'cannot clear' in result['next_review']['reason']
    workspace['gaps'][0]['source_evidence_ids'] = ['hidden-evidence']
    with pytest.raises(ValueError, match='unavailable evidence'):
        build(workspace)


def test_summary_does_not_publish_a_finding_with_inaccessible_counterevidence(workspace):
    from domain.supervision import chat_summary
    from domain.run_summary import render
    finding = workspace['findings'][-1]
    finding.update(title='PRIVATE_FINDING', counter_evidence=['hidden'])
    workspace['findings'] = [finding]
    assert 'PRIVATE_FINDING' not in json.dumps(chat_summary(workspace))
    assert 'PRIVATE_FINDING' not in render(workspace)


def test_summary_respects_dismissal_and_current_reviewed_wording(workspace):
    from domain.supervision import chat_summary
    current = deepcopy(workspace['findings'][-1])
    current.update(review_state='Revised', reviewed_text='Qualified human wording')
    dismissed = deepcopy(current)
    dismissed.update(id='dismissed', title='DISMISSED_MARKER', review_state='Dismissed')
    workspace['findings'] = [dismissed, current]
    summary = chat_summary(workspace)
    assert 'DISMISSED_MARKER' not in json.dumps(summary)
    assert summary['highlights'][0]['detail'].startswith('Reviewed wording excerpt: Qualified human wording')
    current['review_state'] = 'Needs reassessment'
    assert chat_summary(workspace)['highlights'][0]['detail'].startswith('Draft excerpt:')


def test_reread_before_collection_and_no_invented_findings_in_empty_handoff(workspace):
    from domain.supervision import build, chat_summary
    workspace['findings'] = []
    workspace['gaps'] = [{'id': 'gap', 'question': 'What does the ledger establish?', 'why_it_matters': 'Separate accounting from settlement.',
                          'work_type': 'internal_reread', 'source_evidence_ids': []}]
    result = build(workspace)['next_review']
    assert result['kind'] == 'gap'
    assert 'Re-read them before requesting' in result['reason']
    workspace['gaps'] = []
    workspace['sample'] = True
    summary = chat_summary(workspace)
    assert summary['highlights'] == []
    assert summary['overview'].startswith('Synthetic sample. 0 draft findings')
    assert 'readable does not mean reviewed' in summary['overview']
    assert build(workspace)['next_review']['kind'] == 'scope'


def test_summary_remains_bounded_and_preserves_excerpt_and_limit_labels(workspace):
    from domain.supervision import chat_summary
    from domain.run_summary import render
    workspace['findings'] = [workspace['findings'][-1]]
    workspace['findings'][0].update(title='🌍' * 500, assessment='Long assessment. ' * 500)
    summary = chat_summary(workspace)
    assert len(summary['highlights'][0]['title']) <= 180
    assert len(summary['highlights'][0]['detail']) <= 320
    assert summary['highlights'][0]['detail'].startswith('Read the full finding')
    assert 'Long assessment' not in summary['highlights'][0]['detail']
    assert len(summary['review']['question']) <= 320
    assert len(json.dumps(summary, ensure_ascii=False).encode()) < 16 * 1024
    assert len(render(workspace).encode()) < 16 * 1024
    assert 'Long assessment' not in render(workspace)


@pytest.mark.parametrize('reason, explanation', [
    ('planning_source_context_unavailable', 'no complete source passage fit'),
    ('no_authorized_readable_sources', 'no authorized readable sources'),
])
def test_zero_analysis_is_explicit_in_both_saved_summaries(workspace, reason, explanation):
    from domain.supervision import chat_summary
    from domain.run_summary import render
    workspace['findings'] = []
    workspace['analysis']['stop_reason'] = reason
    workspace['coverage'] = {}
    assert chat_summary(workspace)['status'] == 'Analysis did not start'
    report = render(workspace)
    assert explanation in report
    assert '0 source records sent for assessment; 0 sent for independent review' in report
    assert '[Evidence appendix](evidence_appendix.md)' in report


def test_real_setup_asks_for_goal_while_sample_is_ready(modules):
    ui = json.loads((BLUEPRINT / 'extensions/ui.json').read_text())['setup_guide']
    fields = ui['fields']
    assert [f['path'] for f in fields[:2]] == ['inputs.payload.input_folder', 'inputs.payload.goal']
    assert all(f['requiredModes'] == ['real'] for f in fields[:2])
    assert ui['real']['values']['inputs.payload.goal'] == ''
    assert ui['sample']['values']['inputs.payload.goal']
    optional = [f for f in fields if f['path'] in {'inputs.payload.matter_file', 'inputs.payload.review_file'}]
    assert len(optional) == 2 and all(f['requiredModes'] == [] for f in optional)
