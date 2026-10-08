"""Offline TextMemory transport; Rust tests own filesystem/index semantics."""
import hashlib
import re
import json
import grpc


class Missing(grpc.RpcError):
    def code(self):
        return grpc.StatusCode.NOT_FOUND


class MemoryService:
    def __init__(self):
        self.scopes = {}
        self.metadata = {}
        self.calls = []
        self.source_units = {}

    def client(self, job_id, run_id, principal, **kwargs):
        service = self
        files = self.scopes.setdefault((job_id, run_id), {})
        metadata = self.metadata.setdefault((job_id, run_id), {})
        job_files = self.scopes.setdefault((job_id, None), {})
        job_metadata = self.metadata.setdefault((job_id, None), {})

        def visible():
            return {**job_files, **files}, {**job_metadata, **metadata}

        class Client:
            _scope = (job_id, run_id, principal)

            def command(self, operation, **request):
                files, metadata = visible()
                units = service.source_units.setdefault((job_id, principal), {})
                service.calls.append((operation, request, self._scope))
                if operation == 'register_source_units':
                    source_id = request['source_id']
                    catalog_id = 'job:units-' + digest(source_id)
                    values = [{**v, 'source_id':source_id, 'source_revision':request['source_revision'],
                        'source_sha256':request['source_sha256'], 'unit_id':digest(
                            f"{catalog_id}:{request['source_revision']}:{v['start_byte']}:{v['end_byte']}:{v['sha256']}")}
                        for v in request['units']]
                    units[source_id] = values
                    return {'source_id':catalog_id}
                if operation == 'source_unit_vectors':
                    return {'indexed_vectors':len(request['vectors'])}
                if operation == 'discover_source_units':
                    plan = request['request']; words = set(re.findall(r'\w+', plan['query'].casefold()))
                    ranked = []
                    for source_id in plan['sources']:
                        if metadata.get(source_id, {}).get('allow') and principal not in metadata[source_id]['allow']:
                            continue
                        for unit in units.get(source_id, []):
                            text = files[source_id].encode()[unit['start_byte']:unit['end_byte']].decode()
                            score = len(words & set(re.findall(r'\w+', text.casefold())))
                            if score:
                                ranked.append((score, unit))
                    ranked.sort(key=lambda row:(-row[0], row[1]['source_id'], row[1]['start_byte']))
                    found = [u for _,u in ranked[:plan['limit']]]
                    return {'status':'ready' if found else 'not_found_in_searched_scope',
                            'candidates':found, 'unresolved':[], 'witness':{'fixture_witness':'unit transport only'}}
                raise AssertionError(operation)

            def ingest_text(self, text, *, record_id, namespace, event_id, **values):
                source_id = namespace + ':' + record_id
                target, attributes = (job_files, job_metadata) if namespace == 'job' else (files, metadata)
                if source_id in target and target[source_id] != text and not values.get('expected_version'):
                    raise ValueError('immutable event changed')
                target[source_id] = text
                attributes[source_id] = {**values, 'event_id': event_id,
                                         'roles': list(values.get('roles', []))}
                service.calls.append(('put', source_id, (job_id, run_id, principal)))
                return {'source_id': source_id, 'revision': digest(text), 'indexing': 'ready'}

            def read_complete(self, source_id, **kwargs):
                files, metadata = visible()
                if source_id not in files:
                    raise Missing()
                return {'text': files[source_id], 'revision': digest(files[source_id]), 'body_offset': 0,
                        'metadata': metadata.get(source_id, {}),
                        'source_is_current': True, 'dependency_status': 'valid'}

            def compile_evidence(self, request):
                files, metadata = visible()
                service.calls.append(('compile', request, (job_id, run_id, principal)))
                query = request['retrieval']
                words = set(re.findall(r'\w+', query['query'].lower()))
                bundles = []
                specs = {s['source_id']:s for s in request.get('sources',[])}
                for source_id, text in sorted(files.items()):
                    allow = metadata.get(source_id, {}).get('allow', [])
                    if allow and principal not in allow:
                        continue
                    if query.get('sources') and source_id not in query['sources']:
                        continue
                    if source_id not in specs and words and not any(word in text.lower() for word in words):
                        continue
                    start, end = 0, len(text.encode())
                    if source_id in specs:
                        spec = specs[source_id]
                        if 'start_byte' in spec:
                            start, end = spec['start_byte'], spec['end_byte']
                        else:
                            lines = text.splitlines(keepends=True)
                            start = len(''.join(lines[:spec['start_line']-1]).encode())
                            end = len(''.join(lines[:spec['end_line']]).encode())
                    elif query.get('intent') == 'raw':
                        lines = text.splitlines(keepends=True)
                        matches = [n for n,line in enumerate(lines)
                                   if any(word in set(re.findall(r'\w+',line.lower())) for word in words)]
                        if not matches:
                            continue
                        start = len(''.join(lines[:matches[0]]).encode())
                        end = len(''.join(lines[:matches[-1]+1]).encode())
                    text = text.encode()[start:end].decode()
                    bundles.append({'bundle_id': source_id, 'required': False, 'items': [{
                        'evidence_id': source_id, 'content': text,
                        'handle': {'source_id': source_id, 'record_revision': digest(files[source_id]),
                                   'source_version': digest(files[source_id]),
                                   'start_byte':start,'end_byte':end,
                                   'scope': {'job_id': job_id, 'run_id': run_id, 'principal': principal}},
                    }]})
                bundles.sort(key=lambda b: (-sum(word in b['items'][0]['content'].lower() for word in words), b['bundle_id']))
                bundles = bundles[:query['limit']]
                return {'version': 'mn.context.evidence.v2', 'status': 'ready' if bundles else 'not_found_in_searched_scope',
                        'bundles': bundles, 'unresolved': [], 'witness': {'fixture_witness': 'sideband only'}}

            def retrieve(self, request):
                files, metadata = visible()
                service.calls.append(('retrieve', request, (job_id, run_id, principal)))
                if request['stages'][0]['mode'] == 'raw':
                    words = set(re.findall(r'\w+', request['query'].lower()))
                    found = [{'source_id': id, 'text': text, 'handle': {'source_id': id, 'record_revision': digest(text),
                              'start_byte': 0, 'end_byte': len(text.encode())}}
                             for id, text in sorted(files.items())
                             if any(word in text.lower() for word in words)
                             and (not metadata.get(id, {}).get('allow') or principal in metadata[id]['allow'])]
                    found.sort(key=lambda r: (-sum(word in r['text'].lower() for word in words), r['source_id']))
                    return {'status': 'ready' if found else 'not_found_in_searched_scope',
                            'records': found[:request['limit']], 'witness': {'fixture_witness': 'sideband only'}}
                projected = []
                for source_id, text in sorted(files.items()):
                    allow = metadata.get(source_id, {}).get('allow', [])
                    if allow and principal not in allow:
                        continue
                    try:
                        fields = json.loads(text)
                    except ValueError:
                        if metadata.get(source_id, {}).get('upstream', [])[-1:] != [{'runtime_format': 'mn.runtime.markdown.v1'}]:
                            continue
                        lines = text.splitlines()
                        start = lines.index('## Facts') + 2
                        columns = [x.strip() for x in lines[start].strip('|').split('|')]
                        cells = [json.loads(x.strip()) for x in lines[start + 2].strip('|').split('|')]
                        fields = dict(zip(columns, cells, strict=True))
                    if not isinstance(fields, dict):
                        continue
                    projected.append({'fields': fields, 'supporting_sources': [{'source_id': source_id,
                        'revision': digest(text), 'start_byte': 0, 'end_byte': len(text.encode())}]})
                computed = []
                for stage in request['stages']:
                    plan = stage['analytical']
                    rows = [row for row in projected if all(
                        row['fields'].get(f['field']) == f['value'] if f['op'] == 'eq'
                        else row['fields'].get(f['field']) in f['value'] for f in plan.get('filters', []))]
                    if plan['operation'] == 'recent':
                        rows = [row for row in rows if row['fields'].get(plan['timestamp_field'])]
                        rows.sort(key=lambda r: r['fields'][plan['timestamp_field']], reverse=True)
                    computed.append(rows[:plan['limit']])
                return {'version': 'mn.context.text.v1', 'status': 'ready', 'records': [],
                        'computed': computed, 'graph_facts': [],
                        'witness': {'fixture_witness': 'sideband only'}}

            def close(self):
                pass

        return Client()


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()
