"""Admit legal source dependencies and path exhibits as complete components."""
import json
from mn_context_engine_sdk.evidence import EvidenceGroup, admit_groups


def assess_admitted(packet, records):
    from mn_context_engine_sdk.evidence import ContextRequirements, assess_context
    gaps = [gap for r in records if r['purpose'] in {'support','counter'}
            for gap in r['result'].get('unresolved', [])]
    attempted = any(r['result'].get('quality',{}).get('repair_attempted') for r in records)
    quality = assess_context(ContextRequirements(),has_evidence=bool(packet['evidence']),
        checks={'support_complete':not packet['support_admission']['unresolved_groups'],
                'capacity':packet['support_admission']['status'] not in {'insufficient_capacity','insufficient_budget'}},
        unresolved=gaps,repair_attempted=attempted).witness()
    if quality['action']=='repair':
        quality['action']='insufficient_evidence'
    return quality


def coverage(records, visible):
    return [{'purpose':r['purpose'], 'status':r['result'].get('status', 'unknown'),
             'exhaustive':r['result'].get('exhaustive', False),
             'unresolved':r['result'].get('unresolved', [])[:16],
             'unresolved_count':len(r['result'].get('unresolved', [])),
             'unresolved_details_omitted':max(0,len(r['result'].get('unresolved', []))-16),
             'passage_count':len(r['result'].get('passages', [])),
             'evidence_ids':[p['evidence_id'] for p in r['result'].get('passages', [])
                             if p['evidence_id'] in visible]} for r in records]


def review_closure(spans, records, cited):
    """Review the same complete dependency components as the assessor."""
    selected = set(cited)
    groups = [g for r in records for g in r['result'].get('support_groups', [])]
    pending = True
    while pending:
        pending = False
        for group in groups:
            aliases = set(group['source_evidence_ids'])
            if not aliases & selected:
                continue
            if not group['complete']:
                raise ValueError('Cited source has unresolved dependency support')
            if not aliases <= selected:
                selected.update(aliases)
                pending = True
    if not selected <= {s['evidence_id'] for s in spans}:
        raise ValueError('Cited source dependency is unavailable for independent review')
    return [s for s in spans if s['evidence_id'] in selected]


def admit(spans, records, limit):
    evidence = {s['evidence_id']:s for s in spans}
    groups, paths, unresolved, bound = [], {}, {}, set()
    for n, record in enumerate(records):
        result = record['result']
        for group in result.get('support_groups', []):
            key = str(n) + ':' + group['id']
            aliases = group['source_evidence_ids']
            bound.update(aliases)
            if not group['complete'] or not aliases or not set(aliases) <= evidence.keys():
                unresolved[key] = 'unavailable_source_dependency'
                continue
            matching = [p for p in result.get('paths', []) if p['source_evidence_ids'] == aliases]
            if matching:
                paths[key] = {'view':result.get('view'), 'paths':matching,
                              'status':result['status'], 'unresolved':result.get('unresolved', [])}
            groups.append(EvidenceGroup(key, tuple(dict.fromkeys([key, *aliases])), group.get('required',False)))
    for alias in evidence:
        if alias not in bound:
            groups.append(EvidenceGroup('source:'+alias, (alias,)))
    by_id = {g.group_id:g for g in groups}
    def render(selected):
        allowed = {m for key in selected for m in by_id[key].members if m in evidence}
        return {'evidence':[e for key,e in evidence.items() if key in allowed],
                'graph_paths':[paths[key] for key in selected if key in paths],
                'support_admission':{'status':'incomplete' if unresolved or len(selected)<len(groups) else 'complete',
                    'unresolved_groups':len(unresolved), 'omitted_groups':len(groups)-len(selected)}}
    outcome = admit_groups(groups, render,
        measure=lambda v:len(json.dumps(v, ensure_ascii=False).encode()), limit=max(1,limit))
    return outcome.rendered or {'evidence':[], 'graph_paths':[], 'support_admission':{
        'status':outcome.status, 'unresolved_groups':len(unresolved), 'omitted_groups':len(groups)}}
