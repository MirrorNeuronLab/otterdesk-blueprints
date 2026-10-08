def test_all_source_bound_modules_are_candidates_without_two_module_shortlist(architecture_paths):
    from domain.context_query_plan import plan
    modules={f'm{i}':{'path':f'src/m{i}.py'} for i in range(5)}
    evidence=[{'path':f'src/m{i}.py'} for i in range(5)]
    result=plan({},'Trace function calls',modules,evidence,{'graph':{'seed_limit':12}})
    assert result['modules']==list(modules)
    assert result['relations']==['CALLS'] and not result['unresolved']


def test_unbound_entity_and_seed_limit_are_explicit(architecture_paths):
    from domain.context_query_plan import plan
    modules={'a':{'path':'a.py'},'b':{'path':'b.py'}}
    assert plan({},'unknown concern',modules,[],{})['unresolved']==['entity_unresolved']
    result=plan({},'callers',modules,[{'path':'a.py'},{'path':'b.py'}],{'graph':{'seed_limit':1}})
    assert result['direction']=='incoming' and result['unresolved']==['seed_limit']


def test_call_paths_include_complete_leaf_declaration_witness(architecture_paths):
    from domain.context_traversal import query_paths
    class Session:
        layers = None
        config = {'investigation':{'max_queries':8}}
        receipts = []
        nodes = [{'kind':'Symbol','properties':{'key':key, 'name':key, 'module':key,
                  'qualified_name':key+'.'+key, 'evidence_id':'declaration-'+key}}
                 for key in ('a','b','c')]
        node_ids = {'a':1,'b':2,'c':3}
        edge_evidence = {(1,2,'CALLS'):['call-ab'],(2,3,'CALLS'):['call-bc']}
        evidence = {key:{} for key in ('call-ab','call-bc','declaration-a','declaration-b','declaration-c')}
        def _prepare(self, tool):
            assert tool == 'calls'
        def _execute(self, tool, query, params):
            return {'rows':[{'edge_source':a,'edge_target':b,'relation':'CALLS'}
                for a,b in [('a','b'),('b','c')] if a in params['frontier']]}
    result=query_paths(Session(), {'relations':['CALLS'],'modules':['a'],'unresolved':[],
        'direction':'outgoing','target':None,'max_hops':4,'max_nodes':128,'max_edges':128}, 'a')
    path=next(row for row in result['rows'] if row['target']=='c')
    assert [edge['source'] for edge in path['edges']] == ['a','b']
    assert set(path['evidence_ids']) == set(Session.evidence)
