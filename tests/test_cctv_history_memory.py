"""Camera image/text recall across runs, including evidence older than recent captions."""
import hashlib
import json
from types import SimpleNamespace

import pytest

from mn_context_engine_sdk import MediaReference
from mn_sdk.source_query import SourceQuerySession
from text_memory_support import MemoryService

from cctv_operator.payloads.domain.history_memory import CameraHistory, open_history
from cctv_operator.payloads.domain.history_store import CameraHistoryStore


class Embeddings:
    metadata = {'model': 'gemma2-test', 'tokenizer': 'shared-test-space'}

    def __init__(self):
        self.images, self.texts, self.queries = [], [], []

    def embed(self, chunks):
        self.texts.extend(c['text'] for c in chunks)
        return {'vectors': [{**{k: c[k] for k in ('source_id', 'revision', 'start_byte')},
            'end_byte': c['start_byte'] + len(c['text'].encode()), 'values': [-1., 0.]} for c in chunks]}

    def embed_media(self, media):
        self.images.append(media)
        return {'vector': [1., 0.] if b'target' in media.data else [0., 1.], **self.metadata}

    def embed_query(self, question):
        self.queries.append(question)
        return {'vector': [1., 0.], **self.metadata}


@pytest.fixture
def native_transport():
    service, vectors = MemoryService(), {}
    def client(job_id, run_id, principal, **options):
        bound = service.client(job_id, run_id, principal, **options)
        original = bound.command
        def command(operation, **request):
            if operation == 'source_unit_vectors':
                for vector in request['vectors']:
                    vectors[job_id, principal, vector['unit_id'], request['model'], request['tokenizer']] = vector['values']
            if operation == 'discover_source_units':
                query = request['request']
                units = service.source_units.get((job_id, principal), {})
                ranked = []
                for source in query['sources']:
                    for unit in units.get(source, []):
                        values = vectors.get((job_id, principal, unit['unit_id'], query['model'], query['tokenizer']))
                        if values is not None:
                            score = sum(a*b for a,b in zip(values, query['query_vector'], strict=True))
                            ranked.append((score, unit))
                ranked.sort(key=lambda item: (-item[0], item[1]['source_id']))
                return {'status': 'ready' if ranked else 'incomplete',
                    'candidates': [u for _,u in ranked[:query['limit']]], 'unresolved': [],
                    'witness': {'fixture': 'transport only; native Rust rankings verified separately'}}
            return original(operation, **request)
        bound.command = command
        return bound
    return SimpleNamespace(service=service, client=client, vectors=vectors)


def history(tmp_path, transport, *, job='job', camera='entrance', source='approved-source', run='run-one', byte_limit=49152):
    store = CameraHistoryStore(tmp_path / job, job_id=job, camera_id=camera, source_key=source)
    scope = {'job_id': 'sources-' + store.key, 'run_id': run}
    client = transport.client(**scope, principal='cctv-observer')
    session = SourceQuerySession(scope=scope, principal='cctv-observer', client=client)
    return CameraHistory(session, store, embeddings=Embeddings(), max_context_bytes=byte_limit)


def captured(owner, number, *, target=False, timestamps=None, markdown=None):
    identifier = hashlib.sha256(f"{owner.session.scope}:{number}".encode()).hexdigest()
    timestamps = timestamps or [1793500000 + number * 10]
    from datetime import datetime, timezone
    when = datetime.fromtimestamp(timestamps[-1], timezone.utc).isoformat().replace('+00:00', 'Z')
    observation = {'camera_id': owner.store.identity['camera_id'], 'source_key': owner.store.identity['source_key'],
        'run_id': owner.session.scope['run_id'], 'observation_id': identifier, 'observed_at': when,
        'batch_id': 'batch-' + str(number), 'frame_batch_ref': f'frame_batches/batch-{number}/batch.json',
        'source_profile': 'external'}
    frames = [f'JPEG {"target" if target else "ordinary"} people image {number}-{n}'.encode() for n in range(len(timestamps))]
    batch = {'batch_id': observation['batch_id'], 'selected_frames': [
        {'timestamp': timestamp, 'sha256': hashlib.sha256(frame).hexdigest(),
            'path': f'frame_batches/batch-{number}/frame-{index:02d}.jpg'}
        for index, (timestamp, frame) in enumerate(zip(timestamps, frames, strict=True), 1)]}
    return {'observation': observation, 'markdown': markdown or f'# Sampled account {number}\n\nComplete original camera account {number}.\n'}, batch, frames


def test_image_relevance_recalls_older_people_capture_beyond_the_latest_twelve_accounts(tmp_path, native_transport):
    owner = history(tmp_path, native_transport)
    old = captured(owner, 1, target=True)
    for number in range(1, 16):
        owner.remember(*(old if number == 1 else captured(owner, number)))
    assert len(owner.embeddings.images) == 15 and len(owner.embeddings.texts) == 15
    assert owner.embeddings.images[0].data == old[2][0]
    result = owner.search('Who wore a red coat earlier?', limit=1)
    assert result['history']['status'] == 'incomplete' and len(result['history']['evidence']) == 1
    assert result['history']['omitted_count'] == 14
    assert 'Complete original camera account 1.' in result['history']['evidence'][0]['content']
    assert result['frames'][0]['data'] == old[2][0]
    assert result['citations']['m1'][0]['frames'][0]['media']['sha256'] == hashlib.sha256(old[2][0]).hexdigest()
    assert owner.embeddings.queries == ['Who wore a red coat earlier?']
    # No image bytes or duplicate source prose enter the local locator catalog.
    serialized = owner.store.db.execute('SELECT entry FROM observations').fetchall()
    assert all('Complete original camera account' not in entry and 'JPEG target' not in entry for (entry,) in serialized)
    owner.close()


def test_previous_run_images_survive_restart_and_run_summary_stays_scoped(tmp_path, native_transport):
    owner = history(tmp_path, native_transport)
    evidence = captured(owner, 1, target=True)
    owner.remember(*evidence)
    owner.close()
    later = history(tmp_path, native_transport, run='run-two')
    assert later.search('Earlier person')['frames'][0]['data'] == evidence[2][0]
    assert later.search('Summarize', current_run=True)['history']['status'] == 'no_evidence'
    later.remember(*captured(later, 2))
    current = later.search('Summarize', current_run=True)
    assert {e['run_id'] for e in current['history']['evidence']} == {'run-two'}
    later.close()


@pytest.mark.parametrize('change', [{'camera': 'private-camera'}, {'source': 'different-stream'}, {'job': 'other-job'}])
def test_camera_source_and_job_boundaries_do_not_recall_another_view(tmp_path, native_transport, change):
    owner = history(tmp_path, native_transport)
    owner.remember(*captured(owner, 1, target=True))
    owner.close()
    other = history(tmp_path, native_transport, **change)
    result = other.search('Earlier person')
    assert result['history']['status'] == 'no_evidence' and not result['frames']
    other.close()


def test_capture_times_are_filtered_before_image_ranking_and_keep_original_spans(tmp_path, native_transport):
    from datetime import datetime, timezone
    def at(value):
        return datetime.fromtimestamp(value, timezone.utc).isoformat().replace('+00:00', 'Z')
    owner = history(tmp_path, native_transport)
    record = captured(owner, 1, target=True, timestamps=[1793500001, 1793500003])
    owner.remember(*record)
    result = owner.search('Earlier person', after=at(1793500000), before=at(1793500002))
    assert [frame['captured_at'] for frame in result['frames']] == [at(1793500001)]
    assert result['history']['evidence'][0]['content'] == record[0]['markdown']
    assert owner.search('Earlier person', before=at(1793499990))['history']['status'] == 'no_evidence'
    for options in ({'after': '2026-11-01T10:00:00'}, {'after': at(1793500004), 'before': at(1793500000)}):
        with pytest.raises(ValueError):
            owner.search('Earlier person', **options)
    owner.close()


def test_immutable_replay_and_changed_or_missing_assets_fail_explicitly(tmp_path, native_transport):
    owner = history(tmp_path, native_transport)
    record = captured(owner, 1, target=True)
    owner.remember(*record)
    owner.remember(*record)
    assert len(owner.store.entries()) == 1
    entry = owner.store.entries()[0][0]
    ref = MediaReference.from_dict(entry['frames'][0]['media'])
    path = owner.store.root / 'images' / (ref.sha256 + '.jpg')
    path.write_bytes(b'tampered')
    with pytest.raises(ValueError, match='immutable reference'):
        owner.search('Earlier person')
    path.unlink()
    with pytest.raises(FileNotFoundError):
        owner.search('Earlier person')
    owner.close()


@pytest.mark.parametrize('field', ['media', 'captured_at', 'run_id', 'source_profile', 'capture_started_at'])
def test_local_locators_cannot_swap_a_capture_or_change_its_canonical_time(tmp_path, native_transport, field):
    owner = history(tmp_path, native_transport)
    first = captured(owner, 1, target=True)
    owner.remember(*first)
    owner.remember(*captured(owner, 2))
    entries = [entry for entry, _ in owner.store.entries()]
    entry = next(entry for entry in entries if entry['id'] == first[0]['observation']['observation_id'])
    if field == 'media':
        entry['frames'][0]['media'] = next(value for value in entries if value['id'] != entry['id'])['frames'][0]['media']
    elif field in {'source_profile', 'capture_started_at'}:
        entry[field] = 'bundled_demo' if field == 'source_profile' else '2026-10-30T00:00:00Z'
    else:
        entry['frames'][0][field] = '2026-10-30T00:00:00Z' if field == 'captured_at' else 'another-run'
    with owner.store.db:
        owner.store.db.execute('UPDATE observations SET entry=? WHERE id=?', (json.dumps(entry), entry['id']))
    with pytest.raises(ValueError, match='provenance'):
        owner.search('Earlier person')
    owner.close()


def test_indexing_failure_preserves_pending_evidence_and_does_not_claim_a_ready_history(tmp_path, native_transport):
    owner = history(tmp_path, native_transport)
    def fail(_media): raise RuntimeError('embedding service unavailable')
    owner.embeddings.embed_media = fail
    with pytest.raises(RuntimeError, match='embedding service'):
        owner.remember(*captured(owner, 1, target=True))
    assert owner.store.entries()[0][1] is None
    assert owner.search('Earlier person')['history']['status'] == 'index_incomplete'
    owner.close()


def test_whole_caption_capacity_never_silently_truncates_the_account(tmp_path, native_transport):
    owner = history(tmp_path, native_transport, byte_limit=1024)
    owner.remember(*captured(owner, 1, target=True, markdown='# Complete\n' + 'Original full detail. ' * 200))
    result = owner.search('Earlier person')
    assert result['history']['status'] == 'insufficient_capacity'
    assert result['history']['omitted_count'] == 1 and not result['history']['evidence']
    owner.close()


def test_current_blueprint_uses_job_storage_and_runtime_owned_embedding_access(monkeypatch, tmp_path, native_transport):
    config = {'visual_memory': {'enabled': True}, 'text_memory': {'enabled': True},
        'video_source': {'camera_id': 'entrance', 'uri': 'rtsp://user:SECRET@camera.example/view'}}
    monkeypatch.setattr('mn_sdk.source_query.runtime_client', native_transport.client)
    owner = open_history(config, scope={'job_id': 'job', 'run_id': 'run-one'},
        job_directory=tmp_path / 'job', embeddings=Embeddings())
    assert owner is not None and 'SECRET' not in json.dumps(owner.store.identity)
    owner.close()
    with pytest.raises(ValueError, match='Job data directory'):
        open_history(config, scope={'job_id': 'job', 'run_id': 'run-one'}, job_directory=tmp_path / 'other')
