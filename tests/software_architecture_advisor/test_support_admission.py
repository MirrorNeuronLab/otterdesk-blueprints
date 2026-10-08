import copy
import hashlib
import json

import pytest


def span(path, text):
    from domain.review_prompts import evidence_record
    return evidence_record({'path':path,'sha256':hashlib.sha256(text.encode()).hexdigest(),
        'start_offset':0,'end_offset':len(text),'start_line':1,'end_line':1,'text':text})


def prompt(evidence, *, budget=8192, rows=(), results=None):
    from domain.review_prompts import build_prompt
    graph = {'queries':[{'tool':'call_state','rows':list(rows),'rows_omitted':0}]}
    inputs = copy.deepcopy((evidence, graph, results))
    arguments = ({'kind':'executive_synthesis','task_id':'synthesis'},
        {'specs':{},'conventions':''}, {'sources':{},'snapshot_id':'s'}, {}, results or {}, budget, {})
    result = build_prompt(*arguments, retrieval={'architecture_graph':graph},graph_evidence=evidence)
    assert result == build_prompt(*arguments, retrieval={'architecture_graph':graph},graph_evidence=evidence)
    assert (evidence, graph, results) == inputs
    assert len(result['prompt'].encode()) <= budget
    return result, json.loads(result['prompt'])


def test_two_witness_relationship_is_admitted_or_omitted_whole(architecture_paths):
    a, b = span('caller.py','def charge():\n    debit()\n'), span('writer.py', 'x'*12000)
    row = {'caller':'charge','writer':'persist','source_evidence_ids':[a['id'], b['id']]}
    result, value = prompt([a,b], rows=[row])
    assert not value['evidence'] and not value['architecture_graph']['queries'][0]['rows']
    assert value['architecture_graph']['queries'][0]['rows_omitted'] == 1
    assert result['support_admission']['omissions'] == {'graph:0:0':'optional_support_over_capacity'}
    assert value['support_admission']['capacity_limited']
    _, value = prompt([a,b], rows=[row], budget=32768)
    assert value['evidence'] == [a,b]
    assert value['architecture_graph']['queries'][0]['rows'] == [row]


def test_transitive_relationships_keep_no_orphan_witnesses_and_allow_other_units(architecture_paths):
    a, b, c = span('a.py','a'), span('b.py','b'), span('c.py','c'*12000)
    other = span('relevant.py','def relevant():\n    return True\n')
    rows = [{'source_evidence_ids':[a['id'],b['id']]}, {'source_evidence_ids':[b['id'],c['id']]}]
    _, value = prompt([a,b,c,other], rows=rows)
    assert value['evidence'] == [other]
    assert not value['architecture_graph']['queries'][0]['rows']
    assert value['architecture_graph']['queries'][0]['rows_omitted'] == 2


def test_prior_claim_and_counterevidence_share_one_support_group(architecture_paths):
    a, b = span('claim.py','supported claim'), span('exception.py','exception '*2000)
    claim = {'claim_id':'C1','statement':'Qualified claim','evidence':[{k:v for k,v in a.items() if k!='id'}],
             'counterevidence_citations':[{k:v for k,v in b.items() if k!='id'}],
             'counterevidence_status':'supplied'}
    results = {'prior':{'task_id':'prior','kind':'section_synthesis','status':'completed','claims':[claim]}}
    _, value = prompt([a,b],results=results)
    assert not value['evidence'] and not value['prior_results']
    _, value = prompt([a,b],results=results,budget=32768)
    assert value['evidence'] == [a,b]
    assert value['prior_results'][0]['claims'][0]['counterevidence_citations'] == [b['id']]


def test_missing_support_is_explicit_and_conflicting_identity_fails(architecture_paths):
    a = span('a.py','original')
    result, value = prompt([a], rows=[{'source_evidence_ids':[a['id'],'S-missing']}])
    assert not value['evidence']
    assert result['support_admission']['omissions'] == {'graph:0:0':'unresolved_source_support'}
    with pytest.raises(ValueError, match='Conflicting source evidence'):
        prompt([a,{**a,'excerpt':'changed'}])
