"""Authored runtime enquiry → evidence locator → original-source navigation."""
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json

from mn_sdk.context_session.contracts import digest
from mn_sdk.source_query import source_text_query
from mn_sdk.text_memory import runtime_text_memory
from .round_state import read, save
from .evidence.store import EvidenceStore


def _notes(value):
    return '| field | complete JSON value |\n| --- | --- |\n| detail | ' + json.dumps(
        value, ensure_ascii=False, allow_nan=False).replace('|', '\\u007c') + ' |'


def publish(root, frozen, prefix, assessment):
    memory = runtime_text_memory(frozen['config'], principal='round-specialists', scope=frozen['memory_scope'])
    if memory is None:
        return
    from mn_context_engine_sdk.intelligent_system import RuntimeRecord
    marker = f'case/rounds/{prefix}-memory-graph.json'
    sources = None
    try:
        if (root / marker).exists():
            return
        manifest = read(root / 'case/source-query.json')
        source_records = manifest['source_records']
        sources = source_text_query(frozen['config'], principal='round-specialists', scope=frozen['memory_scope'])
        hypothesis = assessment['hypothesis']
        support, counter = hypothesis['supporting_evidence'], hypothesis['contradictory_evidence']
        cited = set(support + counter)
        cited.update(id for f in assessment['report']['findings'] for id in f['evidence_ids'])
        spans = {e.evidence_id: e for e in EvidenceStore(root / 'case/evidence.sqlite3').evidence_for(frozen['investigation_id'])}
        binding = digest([manifest['binding'], prefix, assessment])
        clock = root / f'case/rounds/{prefix}-memory-publication.json'
        if clock.exists():
            publication = read(clock)
            if publication['binding'] != binding:
                raise ValueError('Case runtime publication context changed')
        else:
            publication = {'binding': binding, 'published_at': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')}
            save(root, clock.relative_to(root).as_posix(), publication)
        relations, receipts = [], []
        claim_id = 'case-enquiry-' + binding
        # Runtime dependency IDs do not cross corpora. Revalidate originals and
        # retain scoped references explicitly; graph nodes are navigation only.
        for id in sorted(cited):
            span = spans[id]; reference = source_records[span.source_id]
            original = sources.read_source(reference)
            text = original['text']
            if (hashlib.sha256(text.encode()).hexdigest() != span.content_sha256
                    or not 0 <= span.start_offset < span.end_offset <= len(text)
                    or text[span.start_offset:span.end_offset] != span.text):
                raise ValueError('Cited original case evidence changed')
            evidence_id = 'case-evidence-' + digest([manifest['binding'], prefix, id])
            source_entity = 'case-source-' + digest(reference)
            locator = {**asdict(span), 'text': None, 'source_reference': reference,
                'qualification': 'Source statement; authenticity and legal significance unverified.'}
            record = RuntimeRecord(evidence_id, 'Case evidence locator', publication['published_at'],
                'source_navigation_not_case_evidence',
                {'memory_family': 'litigation_evidence_locator', 'case_snapshot': manifest['binding']['sources_sha256'],
                 'evidence_id': id, 'clock_basis': 'runtime_publication'},
                notes=_notes(locator), relations=((evidence_id, 'CITES', source_entity),))
            receipts.append(memory.record(record, event_id=['case-evidence-locator', evidence_id],
                upstream=[reference], allow=['round-specialists']))
            for relation, ids in [('SUPPORTED_BY', support), ('OPPOSED_BY', counter),
                                  ('CITES', [i for i in cited if i not in support and i not in counter])]:
                if id in ids:
                    relations.append((claim_id, relation, evidence_id))
        record = RuntimeRecord(claim_id, 'Case enquiry assessment', publication['published_at'],
            'inferred_assessment_not_established_fact_or_legal_evidence',
            {'memory_family': 'litigation_review', 'case_snapshot': manifest['binding']['sources_sha256'],
             'hypothesis_id': hypothesis['id'], 'assessment_status': hypothesis['status'],
             'clock_basis': 'runtime_publication'}, notes=_notes(assessment),
            relations=tuple(relations), kind='hypothesis')
        receipt = memory.record(record, event_id=['case-enquiry', binding],
            upstream=[{'source_ref': f'case/rounds/{prefix}-assessment.json'}], allow=['round-specialists'])
        save(root, marker, {'claim': receipt, 'evidence': receipts, 'qualification': 'runtime_navigation',
                           'source_dependency_scope': 'explicit_cross_corpus_revalidation'})
    finally:
        memory.close()
        if sources is not None:
            sources.close()
