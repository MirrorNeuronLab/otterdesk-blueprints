"""Image/text camera history in Membrane, paired with immutable captured assets."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os

from mn_context_engine_sdk.intelligent_system import SourceCorpus, SourceSection
from mn_sdk.context_embeddings import RuntimeEmbeddings
from mn_sdk.context_session.contracts import digest
from mn_sdk.source_query import source_text_query
from mn_live_video_analysis_skill import redact_source_uri

from .history_store import CameraHistoryStore
from .video_summary import _time

PRINCIPAL = 'cctv-observer'
QUALIFICATION = ('Retrieved sampled camera evidence, not exhaustive footage or continuous coverage. '
    'Image similarity selects candidates; it does not verify an event or identify a person. '
    'Preserve original capture times and source qualifications. Repeated samples do not establish unique people '
    'or total appearances. Recorded demo timestamps describe playback, not original event times.')


def enabled(config):
    # Existing text-only callers retain their explicit contract. The current
    # CCTV blueprint enables visual history in its authored default config.
    from mn_sdk.context_engine import context_memory_section_enabled
    return ((config.get('visual_memory') or {}).get('enabled') is True and not config.get('offline')
        and context_memory_section_enabled(config.get('text_memory', {})))


class AccountAdapter:
    def sections(self, text, path):
        return [SourceSection('complete_sampled_account', 1, len(text.split('\n')) - int(text.endswith('\n')),
            qualification='sampled_video_account')]

    def locate(self, prompt, sections):
        return []


class CameraHistory:
    def __init__(self, session, store, *, embeddings=None, max_context_bytes=49152, max_review_frames=2):
        self.session, self.store = session, store
        self.embeddings = embeddings or RuntimeEmbeddings()
        self.max_context_bytes = max_context_bytes
        self.max_review_frames = max_review_frames
        if type(max_context_bytes) is not int or not 1024 <= max_context_bytes <= 1024 * 1024:
            raise ValueError('Camera history context bytes exceed bounds')
        if type(max_review_frames) is not int or not 1 <= max_review_frames <= 4:
            raise ValueError('Historical image review must contain 1..4 frames')

    def remember(self, recorded, batch, frames):
        observation = recorded['observation']
        if (observation['camera_id'] != self.store.identity['camera_id']
                or observation['source_key'] != self.store.identity['source_key']
                or observation['batch_id'] != batch['batch_id']
                or len(frames) != len(batch['selected_frames']) or not 1 <= len(frames) <= 10):
            raise ValueError('Historical camera evidence differs from its admitted observation')
        corpus = SourceCorpus(self.session.client)
        identifier = observation['observation_id']
        account_id = 'camera-account-' + identifier
        capture_started = datetime.fromtimestamp(batch['selected_frames'][0]['timestamp'], timezone.utc).isoformat().replace('+00:00', 'Z')
        capture_ended = datetime.fromtimestamp(batch['selected_frames'][-1]['timestamp'], timezone.utc).isoformat().replace('+00:00', 'Z')
        saved = corpus.add(recorded['markdown'], source_id=account_id, path=account_id + '.md',
            event_id=account_id, adapter=AccountAdapter(), allow=[PRINCIPAL],
            upstream=[{'camera_history': self.store.key, 'observation_id': identifier,
                'capture_time': observation['observed_at'], 'run_id': observation['run_id'],
                'capture_started_at': capture_started, 'capture_ended_at': capture_ended,
                'frame_batch_ref': observation['frame_batch_ref'], 'source_profile': observation.get('source_profile')}])
        captures = []
        for index, (frame, row) in enumerate(zip(frames, batch['selected_frames'], strict=True), 1):
            reference = self.store.put_image(frame, row['sha256'])
            timestamp = datetime.fromtimestamp(row['timestamp'], timezone.utc).isoformat().replace('+00:00', 'Z')
            frame_id = 'camera-frame-' + digest([identifier, index, row['sha256'], timestamp])
            source = corpus.add_media(reference, source_id=frame_id, path=frame_id + '.jpg',
                event_id=frame_id, description='', allow=[PRINCIPAL],
                upstream=[{'camera_history': self.store.key, 'observation_id': identifier,
                    'capture_time': timestamp, 'run_id': observation['run_id'],
                    'frame_batch_ref': observation['frame_batch_ref'], 'frame_path': row['path'], 'frame_index': index}])
            captures.append({'source_id': source['source_id'], 'media': reference.to_dict(),
                'source_revision': source['revision'], 'run_id': observation['run_id'],
                'captured_at': timestamp, 'frame_path': row['path'], 'frame_index': index})
        entry = {'id': identifier, 'run_id': observation['run_id'], 'observed_at': observation['observed_at'],
            'source_profile': observation.get('source_profile'), 'caption_source_id': saved['source_id'],
            'frame_batch_ref': observation['frame_batch_ref'], 'frames': captures,
            'capture_started_at': captures[0]['captured_at'], 'capture_ended_at': captures[-1]['captured_at'],
            'catalog': corpus.catalog()}
        self.store.stage(entry)
        result = corpus.units.index(self.embeddings, media_loader=self.store.load_image)
        self.store.indexed(identifier, result['model_identity'])
        return {'observation_id': identifier, 'indexed_units': result['indexed_units'],
                'image_count': len(captures), 'model_identity': list(result['model_identity'])}

    def search(self, question, *, after='', before='', current_run=False, limit=12):
        if not isinstance(question, str) or not 0 < len(question.strip()) <= 1000:
            raise ValueError('Historical camera question exceeds bounds')
        if type(limit) is not int or not 1 <= limit <= 12:
            raise ValueError('Historical camera result limit must be 1..12')
        if any(not isinstance(bound, str) or len(bound) > 64 for bound in (after, before)):
            raise ValueError('Historical camera time bounds exceed limits')
        entries = self.store.entries(after=after, before=before,
            run_id=self.session.client._scope[1] if current_run else None)
        lower, upper = _time(after) if after else None, _time(before) if before else None
        catalog, groups, by_source = [], {}, {}
        pending = []
        for entry, identity in entries:
            if (entry['catalog']['scope'][0] != self.session.client._scope[0]
                    or entry['catalog']['scope'][2] != PRINCIPAL):
                raise ValueError('Camera history catalog belongs to another corpus or principal')
            if current_run and entry['run_id'] != self.session.client._scope[1]:
                raise ValueError('Camera history locator belongs to a different run')
            captures = [frame for frame in entry['frames']
                if (lower is None or _time(frame['captured_at']) >= lower)
                and (upper is None or _time(frame['captured_at']) <= upper)]
            if not captures:
                continue
            selected = {entry['caption_source_id'], *(frame['source_id'] for frame in captures)}
            groups[entry['id']] = {**entry, 'frames': captures}
            if identity is None:
                pending.append(entry['id'])
            for source in entry['catalog']['sources']:
                if source['source_id'] in selected:
                    catalog.append(source)
                    by_source[source['source_id']] = entry['id']
        packet = {'status': 'no_evidence', 'evidence': [], 'incomplete': False, 'omitted_count': 0,
            'query_bounds': {'after': after, 'before': before}, 'result_limit': limit,
            'retrieval': 'embeddinggemma2_image_and_text', 'usage': QUALIFICATION}
        if not catalog:
            return self._result(packet, {}, [], {})
        if len(catalog) > 5000:
            packet.update(status='insufficient_capacity', incomplete=True)
            return self._result(packet, {}, [], {'reason': 'choose_a_shorter_history_interval'})
        corpus = self.session.corpus
        corpus.restore({'version': 'mn.context.source_catalog.v1', 'scope': list(self.session.client._scope),
            'sources': catalog}, adapters={'.md': AccountAdapter()})
        found = corpus.units.discover(question, mode='hybrid', embeddings=self.embeddings,
            limit=min(128, max(32, limit * 3)), candidate_limit=128)
        if found.get('unresolved'):
            packet.update(status='index_incomplete', incomplete=True)
            return self._result(packet, {}, [], {'discovery': found['witness'],
                'unresolved': found['unresolved'], 'pending_observations': pending})
        ranked = list(dict.fromkeys(by_source[hit['source_id']] for hit in found['candidates']))
        citations, selected_frames, omitted, image_count = {}, [], [], 0
        for identifier in ranked:
            entry = groups[identifier]
            source = corpus._sources[entry['caption_source_id']]
            original = corpus.client.read_complete(entry['caption_source_id'], revision=source['revision'])
            if (not original.get('source_is_current') or original.get('dependency_status') != 'valid'
                    or original['revision'] != source['revision']
                    or hashlib.sha256(original['text'].encode()).hexdigest() != source['sha256']):
                raise ValueError('Retrieved historical account changed or became unavailable')
            self._provenance(original, entry, {'capture_time': entry['observed_at'], 'run_id': entry['run_id'],
                'capture_started_at': entry['capture_started_at'], 'capture_ended_at': entry['capture_ended_at'],
                'frame_batch_ref': entry['frame_batch_ref'], 'source_profile': entry['source_profile']})
            for frame in entry['frames']:
                self._verify_capture(entry, frame)
            alias = 'm' + str(len(packet['evidence']) + 1)
            evidence = {'citation': alias, 'content': original['text'],
                'captures': entry['frames'], 'source_profile': entry['source_profile'], 'run_id': entry['run_id']}
            trial = {**packet, 'evidence': [*packet['evidence'], evidence]}
            if len(packet['evidence']) == limit or len(json.dumps(trial, ensure_ascii=False).encode()) > self.max_context_bytes:
                omitted.append(identifier)
                continue
            packet = trial
            image_count += len(entry['frames'])
            citations[alias] = [{'scope': dict(zip(('job_id', 'run_id', 'principal'), corpus.client._scope)),
                'source_id': entry['caption_source_id'], 'revision': source['revision'],
                'start_byte': 0, 'end_byte': len(original['text'].encode()),
                'capture_started_at': entry['capture_started_at'], 'capture_ended_at': entry['capture_ended_at'],
                'captured_run_id': entry['run_id'], 'frame_batch_ref': entry['frame_batch_ref'], 'frames': entry['frames']}]
            for frame in entry['frames']:
                if len(selected_frames) == self.max_review_frames:
                    break
                from mn_context_engine_sdk import MediaReference
                reference = MediaReference.from_dict(frame['media'])
                selected_frames.append({**frame, 'citation': alias, 'data': self.store.load_image(reference)})
        packet.update(status='ready' if packet['evidence'] else 'no_evidence',
            incomplete=bool(pending or omitted or found.get('unresolved')), omitted_count=len(omitted),
            retrieved_image_count=image_count)
        if packet['incomplete']:
            packet['status'] = ('incomplete' if packet['evidence'] else
                'insufficient_capacity' if omitted else 'index_incomplete')
        return self._result(packet, citations, selected_frames, {'discovery': found['witness'],
            'unresolved': found.get('unresolved', []), 'pending_observations': pending, 'omitted': omitted})

    def _provenance(self, original, entry, expected):
        references = [value for value in original.get('metadata', {}).get('upstream', [])
            if isinstance(value, dict) and value.get('camera_history') == self.store.key
            and value.get('observation_id') == entry['id']]
        if len(references) != 1 or any(references[0].get(key) != value for key, value in expected.items()):
            raise ValueError('Historical capture or account provenance differs from its canonical original')

    def _verify_capture(self, entry, frame):
        from mn_context_engine_sdk.intelligent_system.media import parse_media_document
        original = self.session.client.read_complete(frame['source_id'], revision=frame['source_revision'])
        if (original['revision'] != frame['source_revision'] or not original.get('source_is_current')
                or original.get('dependency_status') != 'valid' or frame['run_id'] != entry['run_id']):
            raise ValueError('Historical capture provenance is stale or belongs to a different run')
        reference, _ = parse_media_document(original['text'])
        if reference.to_dict() != frame['media']:
            raise ValueError('Historical image provenance differs from its canonical media manifest')
        self._provenance(original, entry, {'capture_time': frame['captured_at'], 'run_id': entry['run_id'],
            'frame_batch_ref': entry['frame_batch_ref'], 'frame_path': frame['frame_path'], 'frame_index': frame['frame_index']})

    @staticmethod
    def _result(packet, citations, frames, witness):
        return {'schema_version': 'mn.cctv.video_history.v2', 'history': packet, 'citations': citations,
            'frames': frames, 'continuous_coverage': False, 'qualification': QUALIFICATION, 'witness': witness}

    def close(self):
        try:
            self.session.close()
        finally:
            self.store.close()


def open_history(config, *, job_directory=None, scope=None, camera_id=None, source_key=None, embeddings=None):
    if not enabled(config):
        return None
    scope = scope or {'job_id': os.environ.get('MN_JOB_ID'),
        'run_id': os.environ.get('MN_WORKFLOW_RUN_ID') or os.environ.get('MN_RUN_ID')}
    source = config.get('video_source') or {}
    camera_id = camera_id or os.environ.get('VIDEO_SOURCE_CAMERA_ID') or source.get('camera_id') or 'cctv'
    uri = os.environ.get('VIDEO_SOURCE_URI') or source.get('uri', '')
    source_key = source_key or hashlib.sha256(redact_source_uri(uri).encode()).hexdigest()
    store = CameraHistoryStore(job_directory or os.environ.get('MN_JOB_DATA_DIR') or '',
        job_id=scope['job_id'], camera_id=camera_id, source_key=source_key)
    session = None
    try:
        session = source_text_query(config, principal=PRINCIPAL,
            scope={'job_id': 'cctv-history-' + store.key, 'run_id': scope['run_id']})
        if session is None:
            raise ValueError('Enabled visual memory requires the source-context service')
        return CameraHistory(session, store, embeddings=embeddings,
            max_context_bytes=(config.get('visual_memory') or {}).get('max_context_bytes', 49152),
            max_review_frames=(config.get('visual_memory') or {}).get('max_review_frames', 2))
    except BaseException:
        if session is not None:
            session.close()
        store.close()
        raise


def search_video_history(config, run_dir, *, query, after='', before='', current_run=False, request_id='chat-history'):
    history = open_history(config)
    if history is None:
        return {'history': None, 'citations': {}, 'frames': [], 'qualification': QUALIFICATION}
    try:
        result = history.search(query, after=after, before=before, current_run=current_run)
        from mn_sdk.blueprint_support import write_json
        from pathlib import Path
        write_json(Path(run_dir) / 'runtime_memory' / (digest(request_id) + '-visual-recall.json'),
            {key: value for key, value in result.items() if key != 'frames'})
        return result
    finally:
        history.close()
