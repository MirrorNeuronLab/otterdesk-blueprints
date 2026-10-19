import copy
import pytest
def assess(*args, **kwargs):
    from domain.architecture_score import assess as calculate
    return calculate(*args, **kwargs)



def source():
    return {'snapshot_id':'same','schema_version':'mn.static_code.v1',
      'components':[{'id':p,'status':'parsed','physical_lines':2} for p in ['a/one.c','a/two.c','b/three.c']],
      'component_edges':[{'source':'a/one.c','target':'a/two.c'}], 'cycles':[],
      'functions':[{'path':'a/one.c','evidence':{'sha256':'hash'}}]}


def history():
    return {'snapshot_id':'same','status':'ready','timeline':{'frames':[{'baseline':False,'changed_paths':['a/one.c' if i%2 else 'b/three.c']} for i in range(10)]}}


def test_unknown_weights_are_not_zero_full_or_renormalized():
    score=assess(source(),history())
    assert sum(r['weight'] for r in score['dimensions'])==100
    assert score['score'] is None and score['assessed_weight']==70
    assert score['range']['upper']-score['range']['lower']==30
    assert all(r['points'] is None for r in score['dimensions'][-2:])


def test_cycles_reduce_score_and_no_history_is_not_zero():
    f=source();before=assess(f,history());f['cycles']=[['a/one.c','a/two.c']]
    after=assess(f,history())
    assert after['range']['lower'] < before['range']['lower']
    missing=assess(f,{'snapshot_id':'same'})
    assert missing['assessed_weight']==50 and missing['dimensions'][2]['points'] is None


def test_empty_graph_or_unsupported_source_does_not_earn_perfect_health():
    f=source();f['component_edges']=[]
    score=assess(f,{'snapshot_id':'same'})
    assert score['assessed_weight']==0 and score['range']=={'lower':0,'upper':100}
    f=source();f['components'][0]['status']='unsupported'
    assert assess(f,{'snapshot_id':'same'})['assessed_weight']==0


def test_declared_evidence_can_complete_model_but_needs_matching_source_and_rules():
    witness={'path':'a/one.c','sha256':'hash','line_start':1,'line_end':2}
    supplemental={k:{'complete':True,'passed':8,'total':10,'evidence':[witness],'approved_rules':['no-cross-layer']} for k in ['data_ownership','conformance']}
    result=assess(source(),history(),supplemental=supplemental)
    assert result['assessed_weight']==100 and result['score']==result['range']['lower']==result['range']['upper']
    bad=copy.deepcopy(supplemental);bad['conformance']['evidence'][0]['sha256']='wrong'
    with pytest.raises(ValueError,match='match captured'):assess(source(),history(),supplemental=bad)
    bad=copy.deepcopy(supplemental);bad['conformance']['approved_rules']=[]
    with pytest.raises(ValueError,match='approved'):assess(source(),history(),supplemental=bad)


def test_snapshot_mismatch_rejected():
    with pytest.raises(ValueError,match='snapshots'):assess(source(),{'snapshot_id':'different'})


def test_single_giant_directory_does_not_earn_full_modularity_for_internal_edges():
    f=source()
    f['components'] += [{'id':f'a/extra{i}.c','status':'parsed'} for i in range(20)]
    score=assess(f,history())
    assert score['dimensions'][0]['points'] < 25


def test_incomplete_or_forged_supplemental_evidence_cannot_fill_missing_weight():
    f=source()
    with pytest.raises(ValueError):assess(f,history(),supplemental={'data_ownership':{'complete':False,'passed':10,'total':10}})
    w={'path':'a/one.c','sha256':'hash','line_start':1,'line_end':1000}
    with pytest.raises(ValueError):assess(f,history(),supplemental={'data_ownership':{'complete':True,'passed':10,'total':10,'evidence':[w]}})
