"""Source-validated architecture investigation projection; no model or source execution."""
from collections import Counter
from copy import deepcopy
import json
from pathlib import Path, PurePosixPath

from .catalog_contract import load_snapshot
from .catalog_store import fingerprint
from .structural_analysis import _components
from .improvement_prompts import build as build_prompts

VERSION = 'mn.architecture.workspace.v1'


def _read(path, default):
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default


def project(context, report, registers):
    root = Path(context['run_dir'])
    snapshot = load_snapshot(root)
    manifest = snapshot['manifest']
    cfg = context['config']
    scope_identity = fingerprint(manifest.get('ingest_config', {}))
    # Delivery folders, staged input paths and review imports are not analysis settings.
    analysis_identity = fingerprint({k: cfg[k] for k in (
        'llm', 'embedding', 'graph', 'source_search', 'analysis', 'investigation',
        'lazy', 'knowledge', 'offline', 'catalog_review', 'opencode', 'text_memory') if k in cfg})
    evidence = {e['id']: deepcopy(e) for e in registers['evidence']}
    structural = _read(root / 'analysis/dependencies.json', {})
    sources = snapshot['sources']
    # A directory grouping is a navigation aid, not a declared business boundary.
    files = [{
        'id': 'file-' + fingerprint([manifest.get('repository_id'), path])[:20],
        'path': path, 'sha256': record['sha256'],
        'component_id': 'component-' + fingerprint(str(PurePosixPath(path).parent))[:16],
        'language': PurePosixPath(path).suffix.lstrip('.') or 'dockerfile',
        'lines': len(record['text'].splitlines()),
        'structural_module': any(m['path'] == path for m in manifest.get('modules', {}).values()),
        'scope': 'test' if any(p in {'test', 'tests'} for p in PurePosixPath(path).parts)
                     or '.test.' in path or '.spec.' in path else 'application',
    } for path, record in sorted(sources.items())]
    by_path = {f['path']: f for f in files}
    components = {}
    for file in files:
        component = components.setdefault(file['component_id'], {
            'id': file['component_id'], 'name': str(PurePosixPath(file['path']).parent),
            'basis': 'inferred directory grouping', 'responsibility': 'Not confirmed; inspect source and findings.',
            'files': [], 'finding_ids': [], 'owner': 'Unknown', 'deployment': 'Not verified',
        })
        component['files'].append(file['path'])

    def citation(location):
        path = location['path']
        source = sources.get(path)
        if source is None or source['sha256'] != location['sha256']:
            raise ValueError('Workspace relationship source does not match frozen snapshot')
        start, end = location['line_start'], location['line_end']
        lines = source['text'].splitlines(keepends=True)
        if type(start) is not int or type(end) is not int or not 1 <= start <= end <= len(lines):
            raise ValueError('Workspace relationship has invalid source lines')
        value = {'path': path, 'sha256': source['sha256'], 'start_line': start, 'end_line': end,
                 'excerpt': ''.join(lines[start-1:end]), 'snapshot': snapshot['snapshot_id'],
                 'revision': manifest.get('git_anchor'), 'basis': 'candidate static'}
        ident = 'E-' + fingerprint(value)[:16]
        evidence[ident] = {'id': ident, **value}
        return ident

    relations, aggregate = [], {}
    modules = manifest.get('modules', {})
    for item in structural.get('dependencies', []):
        if item['source'] not in modules or item['target'] not in modules:
            raise ValueError('Workspace dependency endpoint unavailable')
        a, b = modules[item['source']]['path'], modules[item['target']]['path']
        ids = [citation(c) for c in item['source_locations']]
        relation = {'id': 'edge-' + fingerprint([item['source'], item['target']])[:20],
            'source': item['source'], 'target': item['target'], 'source_path': a, 'target_path': b,
            'source_component': by_path[a]['component_id'], 'target_component': by_path[b]['component_id'],
            'type': 'DEPENDS_ON', 'basis': 'candidate static', 'scope': by_path[a]['scope'],
            'classification': 'Import/reference; type-only and build-only semantics not classified',
            'evidence_ids': ids, 'unit': 'distinct captured source spans', 'source_site_count': len(ids)}
        relations.append(relation)
        key = (relation['source_component'], relation['target_component'], relation['scope'])
        group = aggregate.setdefault(key, {'source': key[0], 'target': key[1], 'scope': key[2],
            'relation_ids': [], 'evidence_ids': [], 'basis': 'candidate static', 'type': 'DEPENDS_ON'})
        group['relation_ids'].append(relation['id'])
        group['evidence_ids'] = sorted(set(group['evidence_ids'] + ids))
    for group in aggregate.values():
        group['id'] = 'group-' + fingerprint([group['source'], group['target'], group['scope']])[:20]
        group['source_site_count'] = len(group['evidence_ids'])
    adjacency = {name: set() for name in structural.get('modules', [])}
    for relation in relations:
        adjacency[relation['source']].add(relation['target'])
    cycles = [c for c in _components(adjacency) if len(c) > 1 or c[0] in adjacency[c[0]]]
    findings = deepcopy(registers['findings'])
    for finding in findings:
        paths = sorted({evidence[e]['path'] for e in finding['evidence_ids']})
        finding['continuity_key'] = 'finding-' + fingerprint([finding['statement'].strip().lower(), paths, sorted(finding['aspect_ids'])])[:20]
        finding['material_digest'] = fingerprint({'assessment': finding, 'scope': scope_identity,
            'analysis': analysis_identity, 'goal': report['goal'],
            'source': [{k: evidence[e][k] for k in ('path', 'sha256', 'start_line', 'end_line', 'excerpt')}
                       for e in finding['evidence_ids'] + finding['counterevidence_ids']],
            'recommendations': [r for r in registers['recommendations'] if finding['id'] in r['finding_ids']],
            'assumptions': registers['assumptions']})
        finding['basis'] = 'source-backed assessment; runtime unverified'
        finding['review_state'] = 'Awaiting review'
        finding['resolution_state'] = 'Open'
        finding['review_history'] = []
        finding['component_ids'] = sorted({by_path[p]['component_id'] for p in paths})
        finding['recommendation_ids'] = [r['id'] for r in registers['recommendations'] if finding['id'] in r['finding_ids']]
        for component in finding['component_ids']:
            components[component]['finding_ids'].append(finding['id'])
    history = _read(root / 'analysis/history.json', {'status': 'unavailable', 'reason': 'Git history was not collected', 'change_sets': None})
    languages = Counter(f['language'] for f in files)
    capabilities = [{'language': language, 'files': count,
        'structural_files': sum(f['language'] == language and f['structural_module'] for f in files),
        'parsing': 'Python/BEAM extractor; see warnings' if language in {'py', 'ex', 'exs', 'erl', 'hrl'} else 'Text review only',
        'symbol_resolution': 'Bounded static candidates; dynamic targets unresolved',
        'runtime': 'Not collected', 'test_results': 'Not run'} for language, count in sorted(languages.items())]
    workspace = {
        'schema_version': VERSION, 'id': 'snapshot-' + fingerprint([context.get('run_id') or root.name, snapshot['snapshot_id']])[:24],
        'snapshot_id': snapshot['snapshot_id'], 'repository_id': manifest.get('repository_id') or fingerprint(report.get('input', {})),
        'run_id': str(context.get('run_id') or root.name), 'captured_at': report['analysis_started'],
        'revision': manifest.get('git_anchor'), 'source_identity': fingerprint(manifest['sources']),
        'worktree_state': manifest.get('worktree_state', 'Not recorded; captured hashes are authoritative'),
        'config_identity': analysis_identity, 'scope_identity': scope_identity,
        'repository': report.get('input', {}).get('location') or manifest.get('repository_id') or 'Captured repository',
        'repository_label': PurePosixPath(str(report.get('input', {}).get('location') or 'Captured repository').rstrip('/')).name.removesuffix('.git'),
        'goal': report['goal'], 'status': report['status'], 'executive': report['executive'],
        'terminal': report['terminal'], 'source_scope': report['scope'],
        'execution': {'model': cfg.get('opencode', {}).get('model'),
            'network': 'Bounded source excerpts sent to selected review provider; browsing this page makes no network requests.',
            'source_execution': 'Reviewed code was not executed'},
        'files': files, 'components': list(components.values()), 'relations': relations,
        'component_relations': list(aggregate.values()), 'cycles': cycles,
        'structural_coverage': structural.get('coverage', {}), 'structural_limits': structural.get('limits', ['Structural analysis not available']),
        'capabilities': capabilities, 'history': history, 'findings': findings,
        'evidence': list(evidence.values()), 'claims': deepcopy(registers['claims']),
        'recommendations': deepcopy(registers['recommendations']), 'work_packages': deepcopy(registers['work_packages']),
        'checks': [{**v, 'execution_status': 'Not run'} for v in registers['verification_tasks']],
        'gaps': [{'id': 'gap-' + v['id'], 'question': v['question'], 'missing': v.get('required_input', ''),
            'closure': v.get('acceptance', ''), 'check_id': v['id'], 'aspect_ids': v['aspect_ids']} for v in registers['verification_tasks']],
        'coverage': deepcopy(registers['coverage']), 'assumptions': deepcopy(registers['assumptions']),
        'limitations': [
            'Directory components are inferred navigation groups, not deployed services or confirmed responsibilities.',
            'Static reachability identifies dependency context, not demonstrated behavioral impact or failure.',
            'No imported compatibility checks, runtime telemetry or approved architecture policy were supplied to this projection.',
            'Other languages retain text review; their missing structural edges cannot establish absence of dependencies.',
            'Finding continuity is conservative: wording, aspect or path changes can require manual reconciliation.',
        ],
    }
    workspace['gaps'].extend([
        {'id': 'gap-runtime', 'question': 'Does the candidate behave as expected at runtime?',
         'missing': 'Source-matched traces and representative workload', 'closure': 'Attach observations with build, environment, interval and sampling basis'},
        {'id': 'gap-checks', 'question': 'Do proposed compatibility and reliability checks pass?',
         'missing': 'Recorded check executions and exact tested source versions', 'closure': 'Run separately authorized checks and retain actual inputs, assertions and outcomes'},
        {'id': 'gap-external', 'question': 'Which dynamic bindings and external consumers remain outside this source?',
         'missing': 'Authoritative external inventory and unresolved binding evidence', 'closure': 'Obtain scoped consumer and configuration evidence; do not infer completeness from imports'},
        {'id': 'gap-policy', 'question': 'Which architecture boundaries are approved?',
         'missing': 'Versioned rule register, owners, scope and exceptions in the dashboard projection', 'closure': 'Review declared intent before classifying a relationship as a policy violation'},
    ])
    workspace['improvement_prompts'] = build_prompts(workspace)
    return workspace


def cochange(workspace, first, second, *, exclude_mechanical=False):
    """Exact commit-set intersection; denominators are inspectable, not probabilities."""
    history = workspace['history']
    if history['status'] != 'available':
        return {'status': 'unavailable', 'reason': history.get('reason', 'No captured history')}
    groups = {c['id']: set(c['files']) for c in workspace['components']}
    if first not in groups or second not in groups:
        raise ValueError('Unknown co-change component')
    commits = [c for c in history['change_sets'] if not (exclude_mechanical and c.get('mechanical') is True)]
    left = {c['id'] for c in commits if groups[first].intersection(c['paths'])}
    right = {c['id'] for c in commits if groups[second].intersection(c['paths'])}
    shared, union = left & right, left | right
    return {'status': 'available', 'left': len(left), 'right': len(right), 'shared': len(shared), 'union': len(union),
        'right_given_left': len(shared)/len(left) if left else None,
        'left_given_right': len(shared)/len(right) if right else None,
        'jaccard': len(shared)/len(union) if union else None,
        'matching': [c for c in commits if c['id'] in shared],
        'mechanical_classification': 'Not inferred; exclusion applies only to explicitly classified records'}


def compare(current, previous):
    if previous is None or current['repository_id'] != previous['repository_id']:
        return {'status': 'unavailable', 'reason': 'No earlier snapshot of this repository in this Job', 'files': [], 'findings': [], 'impacts': []}
    old_files = {f['path']: f for f in previous['files']}
    new_files = {f['path']: f for f in current['files']}
    comparable = current['scope_identity'] == previous['scope_identity']
    changes = []
    for path in sorted(set(old_files) | set(new_files)):
        before, after = old_files.get(path), new_files.get(path)
        if before is None or after is None or before['sha256'] != after['sha256']:
            changes.append({'path': path, 'kind': 'Added' if before is None else 'Removed' if after is None else 'Modified',
                'before_sha256': before['sha256'] if before else None, 'after_sha256': after['sha256'] if after else None,
                'before_evidence': [e for e in previous['evidence'] if e['path'] == path],
                'after_evidence_ids': [e['id'] for e in current['evidence'] if e['path'] == path]})
    old_findings = {f['continuity_key']: f for f in previous['findings']}
    finding_changes = []
    for finding in current['findings']:
        old = old_findings.pop(finding['continuity_key'], None)
        changed = old is None or old['material_digest'] != finding['material_digest']
        finding['revision'] = (old.get('revision', 1) if old else 0) + int(changed)
        if old:
            finding['review_history'] = deepcopy(old['review_history'])
            finding['review_state'] = 'Needs reassessment' if changed and old['review_history'] else old['review_state']
        if changed:
            finding_changes.append({'id': finding['id'], 'kind': 'Newly surfaced' if old is None else 'Revised assessment',
                'note': 'Discovery in this review does not establish source introduction date'})
    finding_changes += [{'id': f['id'], 'kind': 'No longer evaluated', 'note': 'Not verified resolved; prior evidence retained'} for f in old_findings.values()]
    # Bounded reverse traversal per changed file. Exact paths disclose each edge.
    reverse = {}
    for source in (current, previous):
        for edge in source['relations']:
            qualified = {**edge, 'snapshot': source['snapshot_id']}
            reverse.setdefault(edge['target_path'], {})[edge['id'] + source['snapshot_id']] = qualified
    impacts = []
    frontiers = []
    for change in changes[:100]:
        pending, seen = [(change['path'], [])], {change['path']}
        for path, route in pending:
            if len(route) == 4:
                if reverse.get(path):
                    frontiers.append({'root': change['path'], 'path': path, 'reason': 'hop limit'})
                continue
            for edge in reverse.get(path, {}).values():
                source = edge['source_path']
                if source in seen:
                    continue
                if len(seen) >= 128:
                    frontiers.append({'root': change['path'], 'path': source, 'reason': 'node limit'})
                    continue
                seen.add(source)
                trail = route + [edge]
                impacts.append({'changed_path': change['path'], 'dependent_path': source,
                    'classification': 'Directly dependent' if len(trail) == 1 else 'Transitively connected',
                    'behavior': 'Unknown; validate scenario and guards', 'path': trail})
                pending.append((source, trail))
    baseline_ids = {eid for impact in impacts for edge in impact['path'] for eid in edge['evidence_ids']}
    return {'status': 'available', 'baseline': previous['id'], 'candidate': current['id'],
        'baseline_definition': 'Previous retained Job snapshot; not a PR parent or merge base',
        'scope_comparable': comparable, 'analysis_comparable': current['config_identity'] == previous['config_identity'],
        'files': changes, 'findings': finding_changes, 'impacts': impacts,
        'baseline_evidence': [e for e in previous['evidence'] if e['id'] in baseline_ids],
        'frontiers': frontiers, 'omitted_changed_roots': max(0, len(changes)-100),
        'bounds': {'max_changed_roots': 100, 'max_hops': 4, 'max_nodes_per_root': 128},
        'limitations': ['Hash comparison; semantic contract compatibility is not computed.',
            'Changed exclusions can remove files without remediation.', 'Missing dynamic and external relationships remain unknown.']}
