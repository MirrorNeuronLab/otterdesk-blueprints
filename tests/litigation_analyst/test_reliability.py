"""Regressions from the real approval/reversal review; no live inference."""
# ruff: noqa: F811 -- Imported pytest fixtures are requested by name.
import json
import re

from test_litigation_analyst import BLUEPRINT, make_context, modules, graph_engine_stub  # noqa: F401
from test_dynamic_rounds import RoundModel, execute_round


def test_numeric_references_and_currency_never_create_clause_fragments(modules):
    from domain.legal_sources import LegalSourceAdapter
    from domain.ingestion.corpus import CaseCorpus
    docs = CaseCorpus(BLUEPRINT / 'examples/approval_reversal_case/inputs', 'case').scan()
    for d in docs:
        adapter = LegalSourceAdapter()
        sections = adapter.sections(d.text, d.relative_path)
        for section in sections:
            value = d.text.encode()[section.start_byte:section.end_byte].decode()
            assert not re.match(r'(104\.|500\.)\s', value)
            assert value == d.text.encode()[section.start_byte:section.end_byte].decode()
        if '03_limited' in d.relative_path:
            assert any('I approve USD 8,000 only for TX-104.' in d.text.encode()[s.start_byte:s.end_byte].decode() for s in sections)


def test_transaction_context_reaches_both_models_and_blocks_false_absence(modules, tmp_path):
    from domain.round_state import initialize, read
    from domain.round_planning import plan_round
    context = make_context(tmp_path, BLUEPRINT / 'examples/approval_reversal_case/inputs')
    context['config']['context_memory']['policy'].update(window_tokens=32768, output_tokens=8192)
    context['payload']['matter_file'] = str(BLUEPRINT / 'examples/approval_reversal_case/matter.json')
    modules['intake'].prepare_sources(context)
    modules['indexing'].build_indexes(context)
    ref = initialize(context)[0]['context']
    seen = []
    class Model(RoundModel):
        def completion_text(self, system, user):
            data = json.loads(user)
            if data['stage'] == 'plan':
                return super().completion_text(system, user)
            seen.append(data)
            # All six cleared documents fit, including the missed limited approval.
            bodies = '\n'.join(e['text'] for e in data['evidence'])
            assert 'I approve USD 8,000 only for TX-104.' in bodies
            assert '-12500.00' in bodies and 'net_balance,0.00' in bodies
            assert 'PRIVATE_LEGAL_SENTINEL_9147' not in bodies
            facts = data['verified_financial']
            assert facts['omitted_event_count'] == 0
            assert facts['transactions'][0]['request_minus_approval'] == '4500.00'
            assert facts['transactions'][0]['posting_reversal_net'] == '0.00'
            if data['stage'] == 'assess':
                value = json.loads(super().completion_text(system, user))
                eid = next(e['evidence_id'] for e in data['evidence'] if e['text'].startswith('As finance director'))
                value['hypothesis']['supporting_evidence'] = [eid]
                value['report']['findings'][0].update(evidence_ids=[eid], assessment='No ledger is available for this transfer.')
                return json.dumps(value)
            return json.dumps({'accepted_ids':[data['report']['findings'][0]['id']], 'issues':[],
                'financial_checks':[{'finding_id':data['report']['findings'][0]['id'], 'status':'consistent',
                    'record_ids':[e['record_id'] for e in facts['events']], 'reason':'Scripted mistaken acceptance.'}]})
    plan = plan_round(context, {'context':ref, '_child':{'revision':0}}, llm_client=Model())
    execute_round(context, ref, plan, Model())
    result = read(context['run_dir'] / 'case/rounds/r01-H01-review.json')
    assert not result['accepted_ids']
    assert any(c['status']=='needs_review' for c in result['consistency_checks'])
    assert len(result['evidence_review_coverage']['complete_source_ids']) == 6
    assert (context['run_dir'] / result['independent_search']).exists()
    assert seen[1]['search_coverage'][-1]['purpose'] == 'source_context'


def test_inventory_routes_existing_and_restricted_requests_internally(modules):
    from domain.gap_work import classify
    from domain.ingestion.corpus import CaseCorpus
    docs = CaseCorpus(BLUEPRINT / 'examples/approval_reversal_case/inputs', 'case').scan()
    assert classify({'question':'Verify the record', 'requested_record':'Complete TX-104 accounting ledger'}, docs)['work_type']=='internal_reread'
    assert classify({'question':'Verify the record', 'requested_record':'Full authorization policy'}, docs)['work_type']=='internal_reread'
    assert classify({'question':'Verify the record', 'requested_record':'Privileged legal advice'}, docs)['work_type']=='handling_review'
    for name in ('TX-104 bank statement', 'Written approval for USD 12,500', 'Confirm reported telephone discussion'):
        assert classify({'question':'Verify the record', 'requested_record':name}, docs)['work_type']=='customer_follow_up'


def test_emc_repository_docs_excluded_only_for_sample_and_attachments_disclosed(modules, tmp_path):
    from domain.ingestion.corpus import CaseCorpus
    from domain.sample_data import EMC2_DOCUMENTATION
    root = tmp_path / 'corpus'
    root.mkdir()
    for name in EMC2_DOCUMENTATION:
        (root / name).write_text('Repository background, not case evidence')
    (root / 'record.txt').write_text('Recorded source statement')
    (root / 'record-copy.txt').write_text('Recorded source statement')
    (root / 'mail.eml').write_text('MIME-Version: 1.0\nContent-Type: multipart/mixed; boundary=x\n\n--x\nContent-Type: text/plain\n\nbody\n--x\nContent-Type: application/pdf\nContent-Disposition: attachment; filename=unprocessed.pdf\n\nopaque\n--x--\n')
    corpus = CaseCorpus(root, 'case', excluded_paths=EMC2_DOCUMENTATION)
    documents = corpus.scan()
    assert len(documents)==3
    assert corpus.processing_gaps[0]['status']=='attachment_not_extracted'
    assert len(CaseCorpus(root, 'case').scan())==6
    context = make_context(tmp_path, root)
    modules['intake'].prepare_sources(context)
    inventory = json.loads((context['run_dir'] / 'case/source_inventory.json').read_text())
    assert ['case:record-copy.txt', 'case:record.txt'] in inventory['duplicate_source_groups']


def test_limited_approval_does_not_falsely_establish_larger_amount_authority(modules):
    from domain.review_packets import consistency_checks
    financial={'events':[{'record_id':'approval','event_type':'approved','amount':'8000.00','evidence_ids':['a']} ]}
    report={'findings':[{'id':'f','title':'Amount-limited authorization',
        'assessment':'No written approval for USD 12,500 is established by the limited record.',
        'limitations':'Only USD 8,000 is expressly approved.'}]}
    assert consistency_checks(report, financial)==[]
    report['findings'][0]['assessment']='No written approval is available.'
    assert consistency_checks(report, financial)[0]['status']=='needs_review'


def test_performance_counts_readiness_and_deduplicates_provider_ledger(modules, tmp_path):
    from domain.performance import measure
    row={'event_id':'one','type':'llm_usage','timestamp':'2026-10-18T18:00:00Z',
        'payload':{'input_tokens':60,'output_tokens':44,'total_tokens':104,'estimated':False}}
    (tmp_path / 'model_usage.jsonl').write_text('\n'.join(json.dumps(r) for r in [row,row]))
    result=measure(tmp_path)
    assert result['provider_ledger']['usage']['values']['total_tokens']==104
    assert result['provider_ledger']['usage']['records']==1
    assert result['calibration_seconds'] is None and result['repair_seconds'] is None


def test_unknown_token_measurements_are_not_reported_as_zero(modules, tmp_path):
    from domain.performance import measure
    path=tmp_path / 'case/rounds/models/decision.json'
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({'value':{'accepted_ids':[]}, 'usage':{
        'input_tokens':None,'output_tokens':None,'total_tokens':None,'provider_response_count':1,'estimated':False}}))
    result=measure(tmp_path)
    assert result['recorded_decision_usage']['total_tokens'] is None
    assert result['recorded_decision_usage']['provider_response_count']==1
