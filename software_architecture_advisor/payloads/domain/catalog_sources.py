"""Original code publication and whole revision-bound source query evidence."""
import hashlib

from mn_sdk.source_query import source_text_query
from .catalog_store import fingerprint
from .review_prompts import evidence_record

VERSION = 'architecture-original-sources-v3'


def input_binding(request, snapshot):
    return fingerprint([VERSION,request['memory_scope'],snapshot['snapshot_id'],
                        {p:r['sha256'] for p,r in snapshot['sources'].items()},
                        request['retrieval_config'].get('source_search', {}),
                        request['retrieval_config'].get('embedding', {})])


class AvailablePython:
    """Use native text for explicitly recorded syntax-unavailable originals."""
    def __init__(self, unavailable):
        from mn_context_source_code import PythonCodeAdapter
        from mn_context_engine_sdk.intelligent_system import TextDocumentAdapter
        self.adapter, self.unavailable = PythonCodeAdapter(), set(unavailable)
        self.text = TextDocumentAdapter()

    def sections(self, text, path):
        return self.text.sections(text, path) if path in self.unavailable else self.adapter.sections(text, path)

    def locate(self, prompt, sections):
        return self.adapter.locate(prompt, sections)


def session(request):
    return source_text_query(request['retrieval_config'], principal='architecture-source-query',
                             scope=request['memory_scope'])


def adapters(snapshot, unavailable):
    from pathlib import PurePosixPath
    from mn_context_engine_sdk.intelligent_system import TextDocumentAdapter
    text = TextDocumentAdapter()
    return {**{PurePosixPath(path).suffix: text for path in snapshot['sources']},
            '.py': AvailablePython(unavailable)}


def publish_inputs(store, request, snapshot):
    sources = session(request)
    if sources is None:
        return
    try:
        from mn_context_source_code import PythonCodeAdapter
        adapter = PythonCodeAdapter()
        binding = input_binding(request,snapshot)
        marker = 'catalog/source-inputs.json'
        if store.path(marker).exists():
            if store.read(marker)['binding'] != binding:
                raise ValueError('Original source publication changed on replay')
            return
        records, text_only, limitations = [], [], []
        for path, record in sorted(snapshot['sources'].items()):
            if hashlib.sha256(record['text'].encode()).hexdigest() != record['sha256']:
                raise ValueError('Original source differs from frozen snapshot')
            value = {'source_ref':path, 'text':record['text'],
                'upstream':[{'snapshot_id':snapshot['snapshot_id'],'sha256':record['sha256']}],
                'allow':['architecture-source-query']}
            try:
                if path.endswith('.py'):
                    adapter.sections(record['text'],path)
            except SyntaxError:
                # Capture already permits syntax-error sources with no static
                # facts. Preserve originals for explicit native text search.
                text_only.append(value)
                limitations.append({'path':path,'status':'syntax_unavailable','mode':'structural_text_units'})
            else:
                records.append(value)
        mapping = adapters(snapshot, [r['path'] for r in limitations])
        sources.ingest([*records, *text_only], adapters=mapping)
        mode = request['retrieval_config'].get('source_search', {}).get('mode', 'lexical')
        if mode not in {'lexical', 'hybrid'}:
            raise ValueError('source_search.mode must be lexical or hybrid')
        if mode == 'hybrid' and (records or text_only):
            from .source_embeddings import SourceEmbeddings
            store.path('catalog').mkdir(parents=True, exist_ok=True)
            encoder = SourceEmbeddings(request['retrieval_config'], store.path('catalog/source-vectors.sqlite3'))
            try:
                sources.corpus.units.index(encoder)
            finally:
                encoder.close()
        store.write(marker, {'version':VERSION,'binding':binding,'catalog':sources.catalog(),
                             'limitations':limitations})
    finally:
        sources.close()


def source_context(store, request, snapshot, task, focus):
    sources = session(request)
    if sources is None:
        return {'status':'disabled','incomplete':True}, []
    try:
        saved = store.read('catalog/source-inputs.json')
        if saved['binding'] != input_binding(request,snapshot):
            raise ValueError('Original source publication changed on replay')
        binding = fingerprint(['context-quality-v1',saved['binding'],task,focus,
                               request['retrieval_config']['text_memory']])
        path = f"catalog/source-context/{task['task_id']}.json"
        if store.path(path).exists():
            cached = store.read(path)
            if cached['binding'] != binding:
                raise ValueError('Original source query changed on replay')
            for bundle in cached['compiled']['bundles']:
                for item in bundle['items']:
                    handle = item['handle']
                    sources.read_source({'source_id':handle['source_id'],
                        'revision':handle['record_revision'],'scope':sources.scope})
            return cached['packet'], cached['evidence']
        catalog = saved['catalog']
        limitations = {row['path'] for row in saved['limitations']}
        # Recompute trusted locators only for valid Python entries. Syntax-error
        # entries retain native text retrieval with an explicit limitation.
        sources.restore(catalog,adapters=adapters(snapshot, limitations))
        settings = request['retrieval_config']['text_memory']
        mode = request['retrieval_config'].get('source_search', {}).get('mode', 'lexical')
        encoder = None
        if mode == 'hybrid':
            from .source_embeddings import SourceEmbeddings
            encoder = SourceEmbeddings(request['retrieval_config'], store.path('catalog/source-vectors.sqlite3'))
        try:
            from mn_sdk.memory_quality import context_requirements
            compiled = sources.corpus.search(focus, mode=mode, embeddings=encoder,
                limit=settings['max_results'], candidate_limit=max(32, settings['max_results']),
                requirements=context_requirements(request['retrieval_config'],
                    required_checks=('source_binding','support_complete')))
        finally:
            if encoder is not None:
                encoder.close()
        by_id = {entry['source_id']:entry for entry in catalog['sources']}
        evidence, spans = {}, []
        for bundle in compiled['bundles']:
            for item in bundle['items']:
                handle = item['handle']
                original = by_id[handle['source_id']]
                canonical = sources.read_source({'source_id':handle['source_id'],
                    'revision':original['revision'],'scope':sources.scope})
                if handle['record_revision'] != original['revision']:
                    raise ValueError('Original source query revision changed')
                body = snapshot['sources'][original['path']]
                if body['sha256'] != original['sha256'] or canonical['text'] != body['text']:
                    raise ValueError('Source query differs from frozen original')
                data = body['text'].encode()
                start = handle['start_byte']-canonical['body_offset']
                end = handle['end_byte']-canonical['body_offset']
                if not 0 <= start < end <= len(data) or data[start:end].decode() != item['content']:
                    raise ValueError('Original query span differs from its citation')
                start_char, end_char = len(data[:start].decode()), len(data[:end].decode())
                record = evidence_record({'path':original['path'],'sha256':body['sha256'],
                    'start_offset':start_char,'end_offset':end_char,
                    'start_line':body['text'].count('\n',0,start_char)+1,
                    'end_line':body['text'].count('\n',0,max(start_char,end_char-1))+1,
                    'text':item['content']})
                evidence[record['id']] = record
                spans.append({'id':record['id'], 'source_id':handle['source_id'],
                    'source_revision':original['revision'], 'start_byte':start, 'end_byte':end})
        from mn_context_engine_sdk.intelligent_system.source_selection import bind_support_groups
        groups = bind_support_groups(compiled.get('source_selection', {}), spans)
        packet = {'status':compiled['status'],
            'incomplete':compiled['status']!='ready' or bool(compiled.get('unresolved')) or any(not g['complete'] for g in groups),
            'selected_spans':len(evidence),'strategy':'pinned_originals_and_local_static_support',
            'support_groups':groups, 'unresolved':compiled.get('unresolved', []),
            **({'quality':compiled['quality']} if 'quality' in compiled else {}),
            'limitations':saved['limitations'],
            'usage':'Static source spans are supplied as S- evidence. This bounded search does not prove absence.'}
        store.write(path, {'binding':binding,'packet':packet,'evidence':list(evidence.values()),
                           'compiled':compiled})
        return packet, list(evidence.values())
    finally:
        sources.close()


def hydrate_witnesses(store, request, snapshot, witnesses):
    """Expand edge witnesses to complete enclosing units and static dependencies."""
    sources = session(request)
    if sources is None:
        from .graph_source_support import local_support
        return local_support(snapshot, witnesses)
    try:
        saved = store.read('catalog/source-inputs.json')
        if saved['binding'] != input_binding(request, snapshot):
            raise ValueError('Graph source publication changed')
        sources.restore(saved['catalog'], adapters=adapters(snapshot,
            [r['path'] for r in saved['limitations']]))
        by_path = {s['path']:s for s in saved['catalog']['sources']}
        selections, roots = [], {}
        for witness_id, witness in witnesses.items():
            entry = by_path[witness['path']]
            candidates = [s for s in entry['sections'] if
                s['start_line'] <= witness['line_start'] <= witness['line_end'] <= s['end_line']]
            if not candidates:
                roots[witness_id] = []
                continue
            smallest = min(s['end_line']-s['start_line'] for s in candidates)
            chosen = [s for s in candidates if s['end_line']-s['start_line'] == smallest]
            roots[witness_id] = [(entry['source_id'], s['name']) for s in chosen]
            selections.extend({'source_id':entry['source_id'], 'name':s['name']} for s in chosen)
        selections = [dict(values) for values in dict.fromkeys(tuple(sorted(s.items())) for s in selections)]
        if len(selections) > 128:
            return {key: [] for key in witnesses}, [], ['source_span_capacity_exceeded']
        compiled = sources.corpus.select_sections('Hydrate graph source support', selections)
        by_id = {s['source_id']:s for s in saved['catalog']['sources']}
        evidence, spans = {}, []
        for bundle in compiled.get('bundles', []):
            for item in bundle['items']:
                handle = item['handle']; entry = by_id[handle['source_id']]
                current = sources.read_source({'source_id':handle['source_id'],
                    'revision':entry['revision'], 'scope':sources.scope})
                body = snapshot['sources'][entry['path']]
                if current['text'] != body['text'] or body['sha256'] != entry['sha256']:
                    raise ValueError('Graph source differs from frozen original')
                a, b = handle['start_byte']-current['body_offset'], handle['end_byte']-current['body_offset']
                data = body['text'].encode()
                if not 0 <= a < b <= len(data) or data[a:b].decode() != item['content']:
                    raise ValueError('Graph support span changed')
                start, end = len(data[:a].decode()), len(data[:b].decode())
                record = evidence_record({'path':entry['path'], 'sha256':entry['sha256'],
                    'start_offset':start, 'end_offset':end, 'start_line':body['text'].count('\n',0,start)+1,
                    'end_line':body['text'].count('\n',0,max(start,end-1))+1, 'text':item['content']})
                evidence[record['id']] = record
                spans.append({'id':record['id'], 'source_id':entry['source_id'],
                    'source_revision':entry['revision'], 'start_byte':a, 'end_byte':b})
        from mn_context_engine_sdk.intelligent_system.source_selection import bind_support_groups
        selection = compiled.get('source_selection', {})
        units = {u['unit_id']:u for u in selection.get('units', [])}
        groups = bind_support_groups(selection, spans)
        bound = {}
        for witness, names in roots.items():
            matched = [g for g in groups if g['complete'] and any(
                (units[m]['source_id'], g['root']) in names for m in g['members'])]
            bound[witness] = list(dict.fromkeys(e for g in matched for e in g['source_evidence_ids']))
        return bound, list(evidence.values()), compiled.get('unresolved', [])
    finally:
        sources.close()
