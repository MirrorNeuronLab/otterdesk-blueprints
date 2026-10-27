"""Rule-local evidence workspaces over one shared offline source/syntax index."""
from mn_code_search_skill import SyntaxIndex, TextSearchIndex

from .evidence import evidence_handle
from .source_policy import evidence_paths, project_map, source_role


class EvidenceWorkspace:
    def __init__(self, sources, analysis):
        self.sources = sources
        self.index = TextSearchIndex(sources)
        self.syntax = SyntaxIndex.from_analysis(analysis, sources)
        self.map = project_map(sources, analysis)

    def rank(self, rule, query):
        preferred = self.index.rank(query, paths=evidence_paths(rule, self.sources), limit=8)
        return {**preferred, 'scope': 'rule_implementation',
                'other_captured_matches': self.index.rank(query, limit=4)['matches']}

    def read(self, path, start, end):
        span = self.index.read(path, start, end)
        function = self.syntax.enclosing(path, start)
        return {**span, 'evidence_id': evidence_handle(span), 'source_role': source_role(path),
                'definition_complete': bool(function and start <= function['evidence']['line_start']
                                             and end >= function['evidence']['line_end'])}

    def symbols(self, query):
        found = self.syntax.lookup(query, limit=8)
        return {**found, 'definitions': [{k: f[k] for k in ('id', 'name', 'path', 'lines', 'ambiguous', 'evidence')}
                                         for f in found['definitions']]}

    def trace(self, symbol, depth):
        graph = self.syntax.trace(symbol, depth)
        nodes, calls = list(graph['nodes'].values()), graph['calls']
        return {'roots': graph['roots'], 'ambiguous_matches': graph['ambiguous_matches'],
                'nodes': [{k: f[k] for k in ('id', 'name', 'path', 'evidence')} for f in nodes[:16]],
                'calls': [{k: c[k] for k in ('source', 'target', 'name', 'status', 'evidence')} for c in calls[:16]],
                'total_nodes': len(nodes), 'total_calls': len(calls),
                'truncated': len(nodes) > 16 or len(calls) > 16,
                'qualification': 'syntax_navigation_only; unresolved_bindings_are_not_runtime_proof'}

    def seed(self, rule):
        hits = self.rank(rule, rule['statement'][:4000])
        seen, selected, size = [], set(), 0
        for hit in hits['matches']:
            function = self.syntax.enclosing(hit['path'], hit['line'])
            start, end = hit['start_line'], hit['end_line']
            if function and function['lines'] <= 200:
                start, end = function['evidence']['line_start'], function['evidence']['line_end']
            key = (hit['path'], start, end)
            if key in selected:
                continue
            try:
                span = self.read(*key)
            except ValueError:
                continue  # Candidate remains visible; read it in smaller whole-line spans.
            length = len(span['text'].encode())
            if size + length > 16_000:
                continue
            seen.append(span)
            selected.add(key)
            size += length
            if len(seen) == 4:
                break
        return hits, seen


def compact_observations(history, seen):
    """Keep whole recent observations and a stable catalog of every read handle."""
    import json
    working = []
    size = 0
    for item in reversed(history):
        length = len(json.dumps(item, ensure_ascii=False).encode())
        if size + length > 24_000:
            continue
        working.insert(0, item)
        size += length
    catalog = [{'evidence_id': evidence_handle(s), 'path': s['path'],
                'start_line': s['start_line'], 'end_line': s['end_line']} for s in seen]
    return working, catalog
