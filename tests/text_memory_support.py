"""Offline TextMemory transport; Rust tests own filesystem/index semantics."""
import hashlib
import re
import grpc


class Missing(grpc.RpcError):
    def code(self):
        return grpc.StatusCode.NOT_FOUND


class MemoryService:
    def __init__(self):
        self.scopes = {}
        self.metadata = {}
        self.calls = []

    def client(self, job_id, run_id, principal, **kwargs):
        service = self
        files = self.scopes.setdefault((job_id, run_id), {})
        metadata = self.metadata.setdefault((job_id, run_id), {})

        class Client:
            def ingest_text(self, text, *, record_id, namespace, event_id, **values):
                source_id = namespace + ':' + record_id
                if source_id in files and files[source_id] != text:
                    raise ValueError('immutable event changed')
                files[source_id] = text
                metadata[source_id] = values
                service.calls.append(('put', source_id, (job_id, run_id, principal)))
                return {'source_id': source_id, 'revision': digest(text), 'indexing': 'ready'}

            def read_complete(self, source_id, **kwargs):
                if source_id not in files:
                    raise Missing()
                return {'text': files[source_id], 'revision': digest(files[source_id]), 'metadata': metadata.get(source_id, {})}

            def compile_evidence(self, request):
                service.calls.append(('compile', request, (job_id, run_id, principal)))
                query = request['retrieval']
                words = set(re.findall(r'\w+', query['query'].lower()))
                bundles = []
                for source_id, text in sorted(files.items()):
                    allow = metadata.get(source_id, {}).get('allow', [])
                    if allow and principal not in allow:
                        continue
                    if query.get('sources') and source_id not in query['sources']:
                        continue
                    if words and not any(word in text.lower() for word in words):
                        continue
                    bundles.append({'bundle_id': source_id, 'required': False, 'items': [{
                        'evidence_id': source_id, 'content': text,
                        'handle': {'source_id': source_id, 'record_revision': digest(text),
                                   'scope': {'job_id': job_id, 'run_id': run_id, 'principal': principal}},
                    }]})
                bundles.sort(key=lambda b: (-sum(word in b['items'][0]['content'].lower() for word in words), b['bundle_id']))
                bundles = bundles[:query['limit']]
                return {'version': 'mn.context.evidence.v2', 'status': 'ready' if bundles else 'not_found_in_searched_scope',
                        'bundles': bundles, 'unresolved': [], 'witness': {'fixture_witness': 'sideband only'}}

            def close(self):
                pass

        return Client()


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()
