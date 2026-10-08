"""Architecture source/relationship obligations using SDK support components."""
import copy
import json

from mn_context_engine_sdk.evidence import EvidenceGroup, admit_groups
from .catalog_store import fingerprint


def citation_id(citation):
    return 'S-' + fingerprint({k: citation[k] for k in
                              ('path', 'sha256', 'start_offset', 'end_offset')})[:20]


def compact_prior(item):
    compact = {k: copy.deepcopy(v) for k, v in item.items() if k not in {
        'request_hash', 'elapsed_seconds', 'model', 'proposed_followups', 'input_task_ids'}}
    for key in ('claims', 'observations'):
        for claim in compact.get(key, []):
            for field in ('evidence', 'counterevidence_citations'):
                if field in claim:
                    claim[field] = [citation_id(e) for e in claim[field]]
    return compact


def admit_support(base, evidence, prior, budget):
    """Render each graph row or prior claim with all original support, atomically."""
    graph = base.get('architecture_graph', {})
    rows = {}
    groups = []
    unresolved = {}
    bound_sources = set()
    for group in base.get('source_query', {}).get('support_groups', []):
        key = 'source-support:' + group['id']
        aliases = group['source_evidence_ids']
        bound_sources.update(aliases)
        if not group['complete'] or not aliases or not set(aliases) <= evidence.keys():
            unresolved[key] = 'unresolved_source_support'
            continue
        groups.append(EvidenceGroup(key, tuple(aliases), required=group.get('required', False)))
    for q, query in enumerate(graph.get('queries', [])):
        for r, row in enumerate(query.get('rows', [])):
            key = f'graph:{q}:{r}'
            aliases = row.get('source_evidence_ids', [])
            if not isinstance(aliases, list) or any(not isinstance(a, str) for a in aliases):
                raise ValueError('Invalid graph source support contract')
            bound_sources.update(aliases)
            if row.get('support_complete') is False or not aliases or not set(aliases) <= evidence.keys():
                unresolved[key] = 'unresolved_source_support'
                continue
            rows[key] = (q, row)
            groups.append(EvidenceGroup(key, tuple(dict.fromkeys([key, *aliases]))))
    history = {}
    for n, item in enumerate(prior):
        compact = compact_prior(item)
        aliases = list(dict.fromkeys(a for field in ('claims', 'observations')
            for claim in compact.get(field, [])
            for a in claim.get('evidence', []) + claim.get('counterevidence_citations', [])))
        key = f'prior:{n}'
        bound_sources.update(aliases)
        if not set(aliases) <= evidence.keys():
            unresolved[key] = 'unresolved_source_support'
            continue
        history[key] = compact
        groups.append(EvidenceGroup(key, (key, *aliases)))
    # Optional whole search units do not become one mandatory evidence package.
    # Already bound witnesses cannot sneak back in after their group is omitted.
    for alias in evidence:
        if alias not in bound_sources:
            groups.append(EvidenceGroup('source:' + alias, (alias,)))
    by_id = {group.group_id: group for group in groups}

    def render(selected):
        request = copy.deepcopy(base)
        selected_ids = {member for key in selected for member in by_id[key].members
                        if member in evidence}
        request['evidence'] = [e for alias, e in evidence.items() if alias in selected_ids]
        request['prior_results'] = [history[key] for key in selected if key in history]
        request['omissions']['evidence_spans'] = len(evidence) - len(selected_ids)
        request['omissions']['prior_results'] = len(prior) - len(request['prior_results'])
        for q, query in enumerate(request.get('architecture_graph', {}).get('queries', [])):
            original = graph['queries'][q].get('rows', [])
            query['rows'] = [rows[key][1] for key in selected if key in rows and rows[key][0] == q]
            query['rows_omitted'] = query.get('rows_omitted', 0) + len(original) - len(query['rows'])
        request['support_admission'] = {
            'status': 'insufficient_capacity' if groups and not selected else
                      'incomplete' if unresolved or len(selected) < len(groups) else 'complete',
            'groups_selected': len(selected), 'groups_omitted': len(groups) - len(selected),
            'unresolved_groups': len(unresolved),
            'capacity_limited': len(selected) < len(groups)}
        if 'source_query' in request:
            for group in request['source_query'].get('support_groups', []):
                group['admitted'] = 'source-support:' + group['id'] in selected
            if any(not g['admitted'] for g in request['source_query'].get('support_groups', [])):
                request['source_query']['incomplete'] = True
                request['source_query']['status'] = 'incomplete'
        if any(q.get('rows_omitted') for q in request.get('architecture_graph', {}).get('queries', [])):
            request['architecture_graph']['incomplete'] = True
            request['architecture_graph']['status'] = 'incomplete'
        return request

    encode = lambda value: json.dumps(value, ensure_ascii=False, separators=(',', ':'))
    admission = admit_groups(groups, render, measure=lambda value: len(encode(value).encode()), limit=budget)
    if admission.rendered is None:
        raise ValueError('Prompt budget cannot fit mandatory specification and output contract')
    receipt = {
        'version': 'mn.context.support_admission.v1',
        'status': admission.rendered['support_admission']['status'],
        'unit': 'utf8_bytes', 'limit': budget, 'support_prompt_bytes': admission.usage,
        'selected_groups': list(admission.selected_groups),
        'omissions': {**unresolved, **admission.omissions},
        'groups': [{'id': g.group_id, 'members': list(g.members), 'required': g.required} for g in groups],
        'verified_serving_tokens': False}
    return admission.rendered, receipt
