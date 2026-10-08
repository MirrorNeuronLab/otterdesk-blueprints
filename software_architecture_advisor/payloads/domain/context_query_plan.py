"""Bounded architecture-view policy over the existing source-backed graph."""
import re

VERSION = 'architecture-context-views-v2'

# These are discovery views, not claims that a static edge proves runtime behavior.
RULES = (
    (r'\b(retr(?:y|ies)|idempot\w*|duplicate|replay)\b', ('call_state', 'test_call_links', 'control_flow')),
    (r'\b(test\w*|coverage|assert\w*)\b', ('test_call_links', 'tests')),
    (r'\b(state|database|transaction\w*|persist\w*|storage)\b', ('call_state', 'state')),
    (r'\b(data.?flow|transform\w*)\b', ('data_flow',)),
    (r'\b(call\w*|function\w*)\b', ('calls',)),
    (r'\b(deploy\w*|container\w*|service\w*)\b', ('deployment',)),
    (r'\b(security|auth\w*|vulnerab\w*)\b', ('security',)),
    (r'\b(type\w*|inherit\w*)\b', ('types',)),
    (r'\b(event\w*|messag\w*)\b', ('events',)),
)


def views(focus):
    selected = []
    for pattern, tools in RULES:
        if re.search(pattern, focus.lower()):
            selected.extend(t for t in tools if t not in selected)
    if re.search(r'\b(cycl\w*|circular)\b', focus.lower()):
        selected.append('cycles')
    return list(dict.fromkeys(selected))


def plan(task, focus, modules, evidence, config):
    """Bind scope to exact names/paths and ranked original evidence, not name overlap."""
    paths = list(dict.fromkeys([task.get('path'), *(e['path'] for e in evidence)]))
    explicit = [name for name in modules if re.search(
        r'(?<![\w.])' + re.escape(name) + r'(?![\w.])', focus)]
    names = list(dict.fromkeys([*(n for n, m in modules.items() if m['path'] == task.get('path')),
        *explicit, *(n for path in paths for n, m in modules.items() if m['path'] == path)]))
    limits = config.get('graph', {})
    bound = limits.get('seed_limit', 12)
    if type(bound) is not int or not 1 <= bound <= 128:
        raise ValueError('graph.seed_limit must be in 1..128')
    selected = views(focus)
    incoming = bool(re.search(r'\b(callers?|dependents?|blast.radius|affected.by|who.calls)\b', focus.lower()))
    return {'version': VERSION, 'modules': names[:bound], 'views': selected,
        'direction': 'incoming' if incoming else 'outgoing',
        'relations': ['CALLS'] if any(v in selected for v in ('calls', 'call_state', 'test_call_links')) else ['DEPENDS_ON'],
        'max_hops': limits.get('max_hops', 4), 'max_nodes': limits.get('max_nodes', 128),
        'max_edges': limits.get('max_edges', 128), 'target': None,
        'unresolved': (['seed_limit'] if len(names) > bound else []) +
                      ([] if names else ['entity_unresolved'])}
