"""Adapt the declared architecture encoder to Membrane whole-unit discovery."""
import hashlib
import json

from .ingest import CachedEmbedder


class SourceEmbeddings:
    def __init__(self, config, path):
        self.encoder = CachedEmbedder(config, path)
        identity = hashlib.sha256(json.dumps([config['embedding'], self.encoder.version], sort_keys=True).encode()).hexdigest()
        self.metadata = {'model':identity, 'tokenizer':self.encoder.version + ':utf8-256'}

    @staticmethod
    def pieces(text):
        current, size, offset = '', 0, 0
        for char in text:
            width = len(char.encode())
            if size + width > 256:
                yield offset, current
                offset += size; current, size = '', 0
            current += char; size += width
        if current:
            yield offset, current

    def embed(self, chunks):
        vectors = []
        for chunk in chunks:
            for offset, text in self.pieces(chunk['text']):
                start = chunk['start_byte'] + offset
                vectors.append({'source_id':chunk['source_id'], 'revision':chunk['revision'],
                    'start_byte':start, 'end_byte':start+len(text.encode()), 'values':list(self.encoder.embed(text))})
        return {'vectors':vectors}

    def embed_query(self, prompt):
        from mn_context_engine_sdk.intelligent_system.source_units import pool
        method = getattr(self.encoder.provider, 'embed_query', self.encoder.provider.embed)
        vectors = [{'source_id':'query', 'revision':'query', 'start_byte':offset,
                    'end_byte':offset+len(text.encode()), 'values':list(method(text))}
                   for offset,text in self.pieces(prompt)]
        vector = pool(vectors, source_id='query', revision='query', start=0, end=len(prompt.encode()))
        return {'vector':vector, **self.metadata}

    def close(self):
        self.encoder.close()
