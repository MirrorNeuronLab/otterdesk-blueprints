"""Project separately qualified legal units, dependency edges and proposals."""
from .projector import _logical_id
from ..relationship_index import proposal_key


def records(index):
    nodes, edges = [], []
    for unit in index['units']:
        key = unit['key']
        nodes.append({'id':_logical_id('node',key), 'kind':'Clause', 'labels':['Clause'],
            'properties':{k:v for k,v in unit.items() if k not in {'text','dependencies'}}})
    for relation in index['relations']:
        key = 'relation:' + '|'.join(relation[k] for k in ('source','relation','target','kind'))
        props = {**relation, 'key':key, 'source_key':relation['source'], 'target_key':relation['target']}
        # The node view exposes complete support despite the engine's edge-value
        # projection limitations. Observed and proposed interpretations stay apart.
        nodes.append({'id':_logical_id('node',key), 'kind':'LegalRelation', 'labels':['LegalRelation'],
                      'properties':{k:v for k,v in props.items() if k != 'observations'}})
        edges.append({'id':_logical_id('edge',key), 'src':_logical_id('node',relation['source']),
            'dst':_logical_id('node',relation['target']), 'rel_type':relation['relation'],
            'properties':{'kind':relation['kind'], 'support':relation['support']}})
    for proposal in index['proposals']:
        key = proposal_key(proposal)
        nodes.append({'id':_logical_id('node',key), 'kind':'LegalProposal', 'labels':['LegalProposal'],
                      'properties':{**proposal, 'key':key}})
        edges.append({'id':_logical_id('edge',key), 'src':_logical_id('node',proposal['source']),
                      'dst':_logical_id('node',key), 'rel_type':'HAS_PROPOSAL',
                      'properties':{'kind':'model_proposal'}})
    return nodes, edges
