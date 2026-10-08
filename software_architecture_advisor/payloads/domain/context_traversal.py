"""Source-backed architecture path queries over materialized native graph views."""
import re

from mn_graph_analysis_skill import TraversalPlan, traverse


def query_paths(session, plan, focus):
    relation = plan['relations'][0]
    session._prepare('calls' if relation == 'CALLS' else 'dependencies')
    nodes = session.nodes
    by_key = {n['properties']['key']:n['properties'] for n in nodes}
    if relation == 'DEPENDS_ON':
        seeds = ['module:' + name for name in plan['modules']]
    else:
        candidates = [n['properties'] for n in nodes if n['kind'] == 'Symbol'
                      and n['properties'].get('module') in plan['modules']]
        named = [n for n in candidates if any(re.search(r'(?<![\w.])' + re.escape(value) + r'(?!\w)', focus)
                 for value in (n.get('qualified_name', ''), n.get('name', '')) if value)]
        seeds = sorted(n['key'] for n in (named or candidates))
    known = set(session.node_ids)
    seeds = [seed for seed in seeds if seed in known]
    unresolved = list(plan['unresolved'])
    if len(seeds) > plan['max_nodes']:
        seeds = seeds[:plan['max_nodes']]
        unresolved.append('seed_limit')
    if not seeds:
        return {'tool': 'context_paths', 'rows': [], 'status': 'entity_unresolved',
                'params': plan, 'unresolved': [*unresolved, 'entity_unresolved']}

    def fetch(frontier, relations, direction, limit):
        if len(session.receipts) >= session.config['investigation']['max_queries']:
            return {'edges': [], 'complete': False, 'unresolved': ['query_budget_exhausted']}
        predicate = {'outgoing': 'r.source_key IN $frontier', 'incoming': 'r.target_key IN $frontier',
                     'both': '(r.source_key IN $frontier OR r.target_key IN $frontier)'}[direction]
        query = (f'MATCH (r:EvidenceRelation) WHERE r.relation IN $relations AND {predicate} '
                 'RETURN DISTINCT r.source_key AS edge_source, r.target_key AS edge_target, r.relation AS relation '
                 f'ORDER BY edge_source, relation, edge_target LIMIT {limit}')
        receipt = session._execute('context_paths', query, {'frontier': list(frontier), 'relations': list(relations)})
        edges = {}
        for row in receipt['rows'][:limit-1]:
            source, target, kind = row['edge_source'], row['edge_target'], row['relation']
            key = (session.node_ids[source], session.node_ids[target], kind)
            support = session.edge_evidence.get(key)
            if not support or any(e not in session.evidence for e in support):
                raise ValueError('Graph path edge has no immutable source support')
            support = list(support)
            for endpoint in (source, target):
                declaration = by_key[endpoint].get('evidence_id')
                if declaration:
                    if declaration not in session.evidence:
                        raise ValueError('Graph endpoint declaration has no source witness')
                    support.append(declaration)
            edges[(source, kind, target)] = {'source': source, 'target': target, 'relation': kind,
                                            'evidence_ids': sorted(set(support))}
        return {'edges': list(edges.values()), 'complete': len(receipt['rows']) < limit,
                'unresolved': []}

    result = traverse(TraversalPlan(tuple(seeds), tuple(plan['relations']), plan['direction'],
        plan['target'], plan['max_hops'], plan['max_nodes'], plan['max_edges']), fetch)
    result['unresolved'] = list(dict.fromkeys([*unresolved, *result['unresolved']]))
    if session.layers:
        coverage = session.layers.status()['layers']['calls' if relation == 'CALLS' else 'dependencies']
        for scope in coverage.get('scopes', {}).values():
            details = scope.get('details', {})
            if details.get('warnings') or details.get('unresolved_calls') or details.get('unresolved_imports'):
                result['unresolved'].append('unresolved_static_references')
    rows = []
    for path in result['paths']:
        rows.append({**path, 'evidence_ids': list(dict.fromkeys(
            e for edge in path['edges'] for e in edge['evidence_ids']))})
    return {'tool': 'context_paths', 'params': {**plan, 'seeds': seeds}, 'rows': rows,
            'status': 'incomplete' if result['unresolved'] else result['status'],
            'unresolved': result['unresolved'], 'frontier': result['frontier'],
            'layer_coverage': {k:v for k,v in session.layers.status()['layers'].items()
                               if k == ('calls' if relation == 'CALLS' else 'dependencies')} if session.layers else {},
            'limit_note': 'Bounded static paths; dynamic dispatch and external implementations remain unproven.'}
