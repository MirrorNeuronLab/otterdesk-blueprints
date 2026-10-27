"""Code verifier's source authority policy; retrieval mechanics live in skills."""
from collections import Counter
from pathlib import PurePosixPath

GENERATED = frozenset({'benchmark-results', 'benchmark_results', 'test-results',
                       'test_results', 'playwright-report', 'coverage'})


def source_role(path):
    parts = [p.casefold() for p in PurePosixPath(path).parts]
    name, suffix = parts[-1], PurePosixPath(path).suffix.casefold()
    if any(p in GENERATED for p in parts[:-1]):
        return 'generated_artifact'
    if path.startswith('knowledge/') or suffix in {'.md', '.rst', '.txt'}:
        return 'documentation'
    if any(p in {'test', 'tests', '__tests__', 'fixtures', '__fixtures__'} for p in parts[:-1]) or any(
            token in name for token in ('test_', '.test.', '.spec.', '_test.')):
        return 'test_source'
    if any(p in {'example', 'examples', 'samples', 'tutorials'} for p in parts[:-1]):
        return 'example'
    if suffix in {'.json', '.yaml', '.yml', '.toml', '.ini', '.cfg'}:
        return 'operational_configuration'
    return 'production_source'


def evidence_paths(rule, sources):
    scope = rule.get('scope', '')
    kind = rule.get('requirement_kind', 'behavior')
    roles = {'production_source'}
    if kind == 'configuration':
        roles.add('operational_configuration')
    # A scoped example/configuration is a living object, not product-wide proof.
    if scope and scope != 'product':
        return [p for p in sources if (p == scope or p.startswith(scope.rstrip('/') + '/'))
                and source_role(p) in roles | {'example', 'operational_configuration'}]
    return [p for p in sources if source_role(p) in roles or
            (kind == 'behavior' and p.startswith('.github/workflows/') and p.endswith(('.yml', '.yaml')))]


def project_map(sources, analysis):
    roots = Counter(p.split('/')[0] for p in sources)
    return {'roles': dict(Counter(source_role(p) for p in sources)),
            'roots': dict(roots.most_common(32)), 'total_roots': len(roots), 'roots_truncated': len(roots) > 32,
            'syntax_coverage': analysis['coverage'],
            'limitations': analysis['limitations'],
            'qualification': 'source_structure_only; not_behavioral_proof'}
