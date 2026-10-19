"""Advisor structural score v1: transparent product policy, not ISO/SIG ratings."""
from pathlib import PurePosixPath
from collections import Counter
from math import log

MODEL = 'advisor-structural-v1'
DIMENSIONS = [
    ('modularity', 'Modularity & cohesion', 25),
    ('dependencies', 'Dependency health & cycles', 25),
    ('change_isolation', 'Change isolation', 20),
    ('data_ownership', 'Data ownership', 15),
    ('conformance', 'Architecture rule conformance', 15),
]


def assess(facts, history, *, supplemental=None):
    """Evaluate observed syntax/Git proxies; unknown weights are never reassigned.

    Supplemental measurements are caller-declared evidence, not auto-discovered
    facts: each requires complete=True, passed/total counts and source witnesses.
    They support future source-backed ownership/rule analyzers without changing
    this model's aggregation. The blueprint currently supplies neither.
    """
    if facts.get('snapshot_id') != history.get('snapshot_id'):
        raise ValueError('Score inputs belong to different snapshots')
    group = lambda path: str(PurePosixPath(path).parent)
    components = facts['components']
    known = {c['id'] for c in components if c['status'] in {'parsed','partial'}}
    parsed = sum(c['status'] == 'parsed' for c in components)
    syntax_coverage = parsed / len(components) if components else 0
    edges = {(e['source'],e['target']) for e in facts['component_edges']
             if e['source'] in known and e['target'] in known and e['source'] != e['target']}
    groups = {group(p) for p in known}
    rows = {key:{'id':key,'label':label,'weight':weight,'points':None,'status':'not_assessed',
                 'basis':'','metrics':{},'formula':''} for key,label,weight in DIMENSIONS}
    def measured(key, ratio, basis, metrics, formula):
        if not 0 <= ratio <= 1: raise ValueError('Invalid scoring ratio')
        rows[key].update(points=round(rows[key]['weight']*ratio, 2), status='provisional',
                         basis=basis, metrics=metrics, formula=formula)
    usable = syntax_coverage >= .8 and bool(edges)
    if usable and len(groups) > 1:
        internal = sum(group(a) == group(b) for a,b in edges)
        sizes = Counter(group(p) for p in known)
        entropy = -sum((n/len(known))*log(n/len(known)) for n in sizes.values())/log(len(sizes))
        points = 15*internal/len(edges) + 10*entropy
        measured('modularity', points/25, 'Directory cohesion and distribution proxies; directories are not approved business boundaries.',
            {'internal_pairs':internal,'all_pairs':len(edges),'directory_groups':len(groups),'normalized_group_entropy':round(entropy,6)},
            '15 × internal dependency fraction + 10 × normalized directory-size entropy')
    else:
        rows['modularity']['basis'] = 'Requires at least 80% fully parsed files, extracted dependencies and two directory groups. One directory does not earn perfect cohesion.'
    if usable and len(known) > 1:
        cyclic = set(p for cycle in facts['cycles'] for p in cycle) & known
        density = len(edges)/(len(known)*(len(known)-1))
        points = 20*(1-len(cyclic)/len(known)) + 5*(1-density)
        measured('dependencies', points/25, 'Observed candidate graph only; unresolved calls and parser gaps can hide cycles.',
            {'cyclic_files':len(cyclic),'known_files':len(known),'directed_density':round(density,6)},
            '20 × (1 − cyclic-file fraction) + 5 × (1 − directed dependency density)')
    else:
        rows['dependencies']['basis'] = 'Requires at least 80% fully parsed files and an extracted dependency graph. An empty graph is not proof of health.'
    frames = (history.get('timeline') or {}).get('frames',[])
    commits = [f for f in frames if not f.get('baseline') and 0 < len(f.get('changed_paths',[])) <= 20]
    history_groups = {group(p) for f in commits for p in f['changed_paths']}
    if history.get('status') in {'ready','partial'} and len(commits) >= 10 and len(history_groups) > 1:
        isolated = sum(len({group(p) for p in f['changed_paths']}) == 1 for f in commits)
        measured('change_isolation', isolated/len(commits), 'Directory-local co-change proxy; formatting and coordinated changes are not defects.',
            {'single_group_commits':isolated,'eligible_commits':len(commits),
             'excluded_broad_commits':sum(not f.get('baseline') and len(f.get('changed_paths',[]))>20 for f in frames)},
            '20 × commits confined to one directory group / eligible commits (1–20 changed source paths)')
    else:
        rows['change_isolation']['basis'] = 'Requires at least 10 eligible source-changing commits and two directory groups. Missing/shallow history is not zero isolation.'
    for key in ('data_ownership','conformance'):
        rows[key]['basis'] = ('No complete source-backed datastore ownership inventory was supplied.' if key == 'data_ownership'
                              else 'No approved rule set and source-backed rule evaluation were supplied.')
        rows[key]['formula'] = ('15 × single-owner-conforming accesses / assessed datastore accesses' if key == 'data_ownership'
                                else '15 × passing dependency evaluations / all evaluated dependencies')
        value = (supplemental or {}).get(key)
        if value is None: continue
        if not isinstance(value,dict): raise ValueError('Supplemental score must be a measurement object')
        passed,total = value.get('passed'),value.get('total')
        witnesses = value.get('evidence',[])
        if value.get('complete') is not True or type(passed) is not int or type(total) is not int or not 0 <= passed <= total or total <= 0:
            raise ValueError('Supplemental scores require complete, nonempty integer measurements')
        hashes = {f['path']:f['evidence']['sha256'] for f in facts['functions']}
        bounds = {c['id']:c.get('physical_lines',0) for c in components}
        if not witnesses or any(w.get('path') not in known or hashes.get(w.get('path')) != w.get('sha256')
            or type(w.get('line_start')) is not int or type(w.get('line_end')) is not int or not 1 <= w['line_start'] <= w['line_end'] <= bounds.get(w.get('path'),0) for w in witnesses):
            raise ValueError('Supplemental score evidence must match captured source')
        if key == 'conformance' and not value.get('approved_rules'):
            raise ValueError('Conformance requires approved architecture rules')
        measured(key,passed/total,'Caller-declared complete evidence; its substantive assessment still requires review.',
                 {'passed':passed,'total':total,'evidence':witnesses},rows[key]['formula'])
    dimensions = list(rows.values())
    assessed = sum(d['weight'] for d in dimensions if d['points'] is not None)
    earned = round(sum(d['points'] or 0 for d in dimensions),2)
    return {'schema_version':'mn.architecture.score.v1','model':MODEL,'snapshot_id':facts.get('snapshot_id'),
        'extractor':facts.get('analysis_version',facts['schema_version']), 'maximum':100,
        'score':earned if assessed == 100 else None,'range':{'lower':earned,'upper':round(earned+100-assessed,2)},
        'assessed_weight':assessed,'unassessed_weight':100-assessed,'status':'provisional' if assessed else 'not_assessed',
        'source_parse_coverage':round(syntax_coverage*100,1),'dimensions':dimensions,
        'limitations':['Custom diagnostic model; not an ISO, SIG or industry benchmark score.',
          'The range assigns only unassessed dimensions 0–full credit; it is not a statistical confidence interval.',
          'Directory and static-graph proxies do not establish business cohesion, runtime quality, correctness or security.',
          'Directory naming, file granularity and incomplete bindings can materially affect proxy scores.',
          'Do not rank different repositories or compare different scopes, extractors or score-model versions.']}


def markdown(score):
    lower,upper=score['range']['lower'],score['range']['upper']
    lines=['# Architecture score', '', f"Model: `{score['model']}` · provisional.", '',
        f"{lower}–{upper}/100 possible; {score['assessed_weight']}/100 points assessed. Unknown dimensions are not reassigned.", '',
        '| Dimension | Points | Basis |', '| --- | --- | --- |']
    for row in score['dimensions']:
        points='Not assessed' if row['points'] is None else str(row['points'])+'/'+str(row['weight'])
        lines.append(f"| {row['label']} | {points} | {row['basis']} {row['formula']} |")
    return '\n'.join(lines+['','## Limits','',*['- '+s for s in score['limitations']],''])
