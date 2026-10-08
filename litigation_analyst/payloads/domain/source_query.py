"""Case policy binding for separate, immutable original-document retrieval."""
from dataclasses import asdict
import hashlib
import json
from pathlib import PurePosixPath

from mn_sdk.source_query import source_text_query
from .round_state import read, save

PRINCIPAL = 'round-specialists'
VERSION = 'litigation.original_sources.v2'


def _binding(case, scope, documents):
    inventory = read(case / 'source_inventory.json')
    return {'version': VERSION, 'scope': scope, 'sources_sha256': inventory['sources_sha256'],
            'access_scopes': sorted({d.access_scope for d in documents})}


def _adapters(documents):
    from .legal_sources import LegalSourceAdapter
    adapter = LegalSourceAdapter()
    return {PurePosixPath(d.relative_path).suffix: adapter for d in documents if d.text is not None}


def publish(context, documents, scope):
    root = context['run_dir']; case = root / 'case'
    session = source_text_query(context['config'], principal=PRINCIPAL, scope=scope)
    if session is None:
        return
    try:
        binding = _binding(case, scope, documents)
        path = root / 'case/source-query.json'
        if path.exists():
            existing = read(path)
            if existing['binding'] != binding:
                raise ValueError('Original case source publication binding changed')
            session.restore(existing['catalog'], adapters=_adapters(documents))
            return
        readable = [d for d in documents if d.text is not None]
        originals = {entry['path']:entry['sha256']
                     for entry in read(case/'source_inventory.json')['files']}
        receipts = session.ingest([{'source_ref': d.relative_path, 'text': d.text,
            'allow': [PRINCIPAL], 'upstream': [{**asdict(d), 'text': None,
                'normalized_sha256': hashlib.sha256(d.text.encode()).hexdigest(),
                'original_sha256': originals[(d.container_source_id.removeprefix('case:')
                                             if d.container_source_id else d.relative_path)]}]}
            for d in readable], adapters=_adapters(readable))
        references = {d.source_id: {**ref, 'scope': session.scope}
                      for d, ref in zip(readable, receipts, strict=True)}
        save(root, 'case/source-query.json', {'binding': binding,
             'source_records': references, 'catalog': session.catalog()})
    finally:
        session.close()


def search(case, corpus, config, scope, query, top_k, *, source_names=()):
    if not isinstance(query, str) or not query.strip() or len(query) > 4000:
        raise ValueError('query must contain 1..4000 characters')
    if type(top_k) is not int or not 1 <= top_k <= 20:
        raise ValueError('top_k must be in 1..20')
    documents = tuple(corpus.scan())
    manifest = read(case / 'source-query.json')
    if manifest['binding'] != _binding(case, scope, documents):
        raise ValueError('Original case source query binding changed')
    session = source_text_query(config, principal=PRINCIPAL, scope=scope)
    if session is None:
        raise ValueError('Original source query requires the enabled context engine')
    try:
        session.restore(manifest['catalog'], adapters=_adapters(documents))
        from mn_sdk.memory_quality import context_requirements
        result = session.corpus.search(query, limit=top_k, source_names=source_names,
            requirements=context_requirements(config,required_checks=('source_binding','support_complete')))
        mapping = {ref['source_id']: (d, ref) for d in documents if d.text is not None
                   for ref in [manifest['source_records'][d.source_id]]}
        passages, seen, spans = [], set(), []
        for bundle in result.get('bundles', []):
            for item in bundle['items']:
                handle = item['handle']; document, reference = mapping[handle['source_id']]
                current = session.read_source(reference)
                if (handle.get('record_revision') != reference['revision']
                        or handle.get('scope') != {**session.scope, 'principal': PRINCIPAL}
                        or current['text'] != document.text):
                    raise ValueError('Original case source evidence revision changed')
                begin = handle['start_byte'] - current.get('body_offset', 0)
                end = handle['end_byte'] - current.get('body_offset', 0)
                body = document.text.encode()
                if not 0 <= begin < end <= len(body) or body[begin:end].decode() != item['content']:
                    raise ValueError('Original case source evidence span changed')
                start_offset = len(body[:begin].decode()); end_offset = len(body[:end].decode())
                identity = hashlib.sha256(f'{document.source_id}|{document.content_sha256}|{start_offset}|{end_offset}'.encode()).hexdigest()[:32]
                if identity in seen:
                    continue
                seen.add(identity)
                passages.append({'evidence_id': identity, 'source_id': document.source_id,
                    'content_sha256': document.content_sha256, 'start_offset': start_offset,
                    'end_offset': end_offset, 'text': item['content']})
                spans.append({'id':identity, 'source_id':handle['source_id'],
                    'source_revision':reference['revision'], 'start_byte':begin, 'end_byte':end})
        from mn_context_engine_sdk.intelligent_system.source_selection import bind_support_groups
        groups = bind_support_groups(result.get('source_selection', {}), spans)
        structural_coverage = []
        for source_id in dict.fromkeys(s['source_id'] for s in spans):
            source = session.corpus._sources[source_id]
            structural_coverage.append(source['adapter'].coverage[source['path']])
        # Only declared references in selected complete units are obligations
        # for this packet. Other clauses' unresolved references stay coverage
        # limitations and do not falsely invalidate unrelated quoted passages.
        selected_names = {section.name for unit in result.get('source_selection',{}).get('units',[])
            for section in session.corpus._sources[unit['source_id']]['sections']
            if section.start_byte is not None and
               unit['start_byte'] <= section.start_byte < section.end_byte <= unit['end_byte']}
        unresolved = [*result.get('unresolved', []),
            *('legal_reference_unresolved:' + r['unit'] + ':' + r['reference']
              for coverage in structural_coverage for r in coverage['unresolved'] if r['unit'] in selected_names)]
        return {'passages': passages, 'exhaustive': False,
                'support_groups':groups,
                **({'quality':result['quality']} if 'quality' in result else {}),
                'retrieval': 'membrane_original_source_units', 'status': 'incomplete' if unresolved else result['status'],
                'receipt': {**result.get('witness', {}), 'structural_coverage':structural_coverage}, 'unresolved':unresolved}
    finally:
        session.close()
