"""Seed-bound legal graph navigation and byte-verified original hydration."""
import hashlib
import json

from mn_graph_analysis_skill import GraphClient, TraversalPlan, traverse

VIEWS = {
    'clause_dependencies': {'relations':['SOURCE_DEPENDENCY', 'REFERS_TO', 'DEFINES'], 'direction':'outgoing'},
    'qualification_paths': {'relations':['SOURCE_DEPENDENCY', 'QUALIFIES', 'REFERS_TO'], 'direction':'both'},
    'amendment_paths': {'relations':['AMENDS', 'REFERS_TO'], 'direction':'both'},
    'clause_statements': {'relations':['HAS_PROPOSAL'], 'direction':'outgoing'},
}


def normalize(value):
    if isinstance(value, list):
        return [normalize(v) for v in value]
    if isinstance(value, dict):
        if len(value) == 1 and next(iter(value)) in {'String','UInt64','Int64','Bool','Boolean','List','Null'}:
            return normalize(next(iter(value.values())))
        return {k:normalize(v) for k,v in value.items()}
    return value


def walk(case, corpus, passages, view, config):
    if view not in VIEWS:
        raise ValueError('Unknown legal relationship view')
    index = json.loads((case/'source-relationships.json').read_text())
    documents = {d.source_id:d for d in corpus.scan()}
    units = {u['key']:u for u in index['units'] if u['source_id'] in documents
             and u['access_scope'] == corpus.access_scope}
    seeds = list(dict.fromkeys(u['key'] for p in passages for u in units.values()
        if u['source_id'] == p['source_id'] and u['content_sha256'] == p['content_sha256']
        and p['start_offset'] <= u['start_offset'] < u['end_offset'] <= p['end_offset']))
    settings = config.get('source_relationships', {})
    limit = settings.get('graph_max_edges', 49)
    hops = settings.get('graph_max_hops', 4)
    if type(limit) is not int or not 1 <= limit <= 49:
        raise ValueError('source_relationships.graph_max_edges must be in 1..49')
    if not seeds:
        return {'status':'entity_unresolved', 'paths':[], 'passages':[], 'support_groups':[],
                'unresolved':['No clause units bound to the selected original passages.']}
    truncated = len(seeds) > 128
    seeds = seeds[:128]
    relations = {(r['source'],r['relation'],r['target']):r for r in index['relations']}
    graph = GraphClient(case/'evidence.rgx', timeout_seconds=30, max_output_bytes=1024*1024)

    def fetch(frontier, kinds, direction, capacity):
        predicate = {'outgoing':'r.source_key IN $frontier', 'incoming':'r.target_key IN $frontier',
            'both':'(r.source_key IN $frontier OR r.target_key IN $frontier)'}[direction]
        query = (f'MATCH (r:LegalRelation) WHERE r.relation IN $relations AND {predicate} '
            'RETURN DISTINCT r.source_key AS source, r.target_key AS target, r.relation AS relation '
            f'ORDER BY source, relation, target LIMIT {capacity}')
        raw = graph.query(query, {'frontier':list(frontier), 'relations':list(kinds)})
        rows = [normalize(r.get('fields',r)) for r in raw.get('rows', [])]
        edges = []
        for row in rows[:capacity-1]:
            relation = relations.get((row['source'],row['relation'],row['target']))
            if relation is None or any(key not in units for key in relation['support']):
                raise ValueError('Legal graph path lacks authorized frozen source support')
            edges.append({k:relation[k] for k in ('source','target','relation','kind','support','qualification')})
        return {'edges':edges, 'complete':len(rows)<capacity, 'unresolved':[]}

    plan = TraversalPlan(tuple(seeds), tuple(VIEWS[view]['relations']), VIEWS[view]['direction'],
                         max_hops=hops, max_nodes=128, max_edges=limit)
    if view == 'clause_statements':
        from .relationship_index import proposal_key
        proposals = {proposal_key(p):p for p in index['proposals']}
        raw = graph.query('MATCH (p:LegalProposal) WHERE p.source IN $seeds '
            f'RETURN p.key AS key ORDER BY key LIMIT {limit+1}', {'seeds':seeds})
        rows = [normalize(r.get('fields',r)) for r in raw.get('rows', [])]
        paths, edges = [], []
        for row in rows[:limit]:
            proposal = proposals.get(row['key'])
            if proposal is None or proposal['source'] not in seeds:
                raise ValueError('Legal statement escaped its authorized seed scope')
            edge = {'source':proposal['source'], 'target':row['key'], 'relation':'HAS_PROPOSAL',
                    'kind':'model_proposal', 'support':[proposal['source']], 'proposal':proposal,
                    'qualification':'Cited source statement extraction; not an established fact.'}
            edges.append(edge)
            paths.append({'seed':proposal['source'], 'target':row['key'], 'edges':[edge]})
        result = {'status':'complete' if rows else 'not_found_in_searched_scope', 'paths':paths,
                  'edges':edges, 'unresolved':['edge_limit'] if len(rows)>limit else [],
                  'exhaustive':len(rows)<=limit, 'frontier':[]}
    else:
        result = traverse(plan, fetch)
    if truncated:
        result['unresolved'].append('seed_limit')
    searched_documents = {units[k]['source_id'] for k in seeds}
    searched_documents.update(units[k]['source_id'] for e in result['edges'] for k in e['support'])
    result['coverage'] = [c for c in index['coverage'] if c['source_id'] in searched_documents]
    if any(c['unresolved'] or c['model_status'] == 'not_requested' for c in result['coverage']):
        result['unresolved'].append('relationship_index_incomplete')
    evidence = {}
    def hydrate(key):
        unit = units[key]; document = documents[unit['source_id']]
        a,b = unit['start_offset'],unit['end_offset']
        if (hashlib.sha256(document.text.encode()).hexdigest() != unit['revision']
                or document.content_sha256 != unit['content_sha256']
                or not 0 <= a < b <= len(document.text) or document.text[a:b] != unit['text']):
            raise ValueError('Legal relationship support differs from frozen original')
        ident = hashlib.sha256(f'{document.source_id}|{document.content_sha256}|{a}|{b}'.encode()).hexdigest()[:32]
        evidence[ident] = {'evidence_id':ident, 'source_id':document.source_id,
            'content_sha256':document.content_sha256, 'start_offset':a, 'end_offset':b, 'text':unit['text']}
        return ident
    groups = []
    for n, path in enumerate(result['paths']):
        support = list(dict.fromkeys(k for edge in path['edges'] for k in edge['support']))
        # Preserve transitive structural dependencies of every path endpoint.
        pending = list(support)
        while pending:
            key = pending.pop()
            for relation in index['relations']:
                if relation['source'] == key and relation['relation'] == 'SOURCE_DEPENDENCY':
                    target = relation['target']
                    if target not in support:
                        support.append(target); pending.append(target)
        if any(k not in units for k in support):
            raise ValueError('Legal dependency escaped authorized scope')
        aliases = [hydrate(k) for k in support]
        path['source_evidence_ids'] = aliases
        groups.append({'id':view+':'+str(n), 'source_evidence_ids':aliases, 'complete':True, 'required':False})
    result.update(view=view, passages=list(evidence.values()), support_groups=groups,
                  plan={'seeds':seeds, **VIEWS[view], 'max_hops':hops})
    if result['unresolved']:
        result['status'] = 'incomplete'; result['exhaustive'] = False
    return result
