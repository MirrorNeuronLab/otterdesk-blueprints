"""Historical context must reach vision without becoming current-image proof."""

import hashlib
import json
import pytest

from test_cctv_operator_conversation import _load_detector, _run_detector


def test_membrane_is_declared_with_context_dependency():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1] / 'cctv_operator'
    assert json.loads((root / 'extensions/context.json').read_text())['text_memory']['enabled']
    dependency = next(p for p in json.loads((root / 'dependencies.json').read_text())['packages']
                      if p['name'] == 'mirrorneuron-python-sdk')
    assert 'context' in dependency['extras']


def test_history_reaches_vision_before_current_write_and_excludes_other_camera(
    monkeypatch, tmp_path, capsys, text_memory_transport
):
    detector = _load_detector()
    config = {'text_memory': {'enabled': True, 'max_results': 3, 'max_context_bytes': 4000}}
    source_key = hashlib.sha256(b'rtsp://camera.example/unit-test').hexdigest()
    old = detector.CameraMemory(config, tmp_path, 'entrance', source_key)
    old.remember({'frame_seq': 1, 'camera_id': 'entrance', 'observed_at': '2026-10-03T01:00:00Z',
                  'summary': 'A red backpack was visible at the doorway in the old sampled frame.',
                  'instruction_revision': 1, 'batch_id': 'prior-batch', 'frame_batch_ref': 'frame_batches/prior/batch.json',
                  'condition_screening': {'route': 'deep_analysis'}, 'source_uri': 'SECRET_CAMERA_URI'})
    other = detector.CameraMemory(config, tmp_path, 'private-camera', source_key)
    other.remember({'frame_seq': 2, 'camera_id': 'private-camera', 'observed_at': '2026-10-03T01:00:01Z',
                    'summary': 'OTHER_CAMERA_CANARY', 'batch_id': 'other',
                    'condition_screening': {'route': 'deep_analysis'}})
    old.close(); other.close()
    output, prompts = _run_detector(detector, monkeypatch, tmp_path, capsys,
        payload={'tick_seq': 3, 'camera_id': 'entrance', 'instruction': 'Watch the floor', 'instruction_revision': 2},
        config=config, detection={'detected': False, 'confidence': .9, 'summary': 'The floor is visible.'})
    assert output['next_state']['last_error'] is None
    assert 'red backpack was visible' in prompts[0] and 'Watch the floor' in prompts[0]
    assert 'OTHER_CAMERA_CANARY' not in prompts[0] and 'SECRET_CAMERA_URI' not in str(text_memory_transport.scopes)
    assert 'Historical text is not a before-and-after image pair' in prompts[0]
    assert 'The floor is visible.' not in prompts[0]  # no recall of the current write
    audit = json.loads((tmp_path / 'run/runtime_memory/frame-3-recall.json').read_text())
    assert audit['packet']['evidence'] and audit['receipt']['citations']
    stored = json.loads((tmp_path / 'run/runtime_memory/frame-3-observation.json').read_text())['observation']
    assert stored['instruction_revision'] == 2 and stored['continuous_coverage'] is False


def test_screening_without_detail_does_not_store_a_zero_detection_fact(tmp_path, text_memory_transport):
    detector = _load_detector()
    memory = detector.CameraMemory({'text_memory': {'enabled': True}}, tmp_path, 'camera', 'source')
    memory.remember({'frame_seq': 1, 'camera_id': 'camera', 'batch_id': 'batch',
        'observed_at': '2026-10-04T01:00:00Z',
        'detection_count': 0, 'detections': [], 'condition_screening': {'route': 'review_declined'}})
    record = json.loads((tmp_path / 'runtime_memory/frame-1-observation.json').read_text())['observation']
    assert record['detection_count'] is None and record['qualification'] == 'screening_only_or_detail_unavailable'
    memory.close()


def test_authored_history_keeps_recent_three_across_runs_and_complete_details(
    monkeypatch, tmp_path, text_memory_transport,
):
    detector = _load_detector()
    config = {'text_memory': {'enabled': True, 'max_results': 3, 'max_context_bytes': 32768}}
    memory = detector.CameraMemory(config, tmp_path / 'old', 'camera', 'source')
    detail = 'Complete sampled qualification with a literal | and 中🙂. ' * 30
    detections = [{'label': 'backpack', 'color': 'red', 'count': 1,
                   'evidence': detail, 'position': {'x': .2, 'y': .4}}]
    for seq in range(1, 5):
        memory.remember({'frame_seq': seq, 'camera_id': 'camera', 'batch_id': f'batch-{seq}',
            'observed_at': f'2026-10-04T01:00:0{seq}Z', 'summary': f'sample-{seq}',
            'detection_count': 1, 'detections': detections, 'detection_report': detail,
            'frame_batch_ref': f'frame_batches/batch-{seq}/batch.json',
            'condition_screening': {'route': 'deep_analysis', 'confidence': .9}})
    memory.close()
    monkeypatch.setenv('MN_RUN_ID', 'later-run')
    later = detector.CameraMemory(config, tmp_path / 'new', 'camera', 'source')
    packet = later.recall(5)
    assert packet['status'] == 'ready' and len(packet['evidence']) == 3
    bodies = [row['content'] for row in packet['evidence']]
    assert [f'"sample-{seq}"' in body for seq, body in zip((4, 3, 2), bodies, strict=True)] == [True] * 3
    assert all('sample-1' not in body and 'camera history schema' not in body.lower() for body in bodies)
    assert all(detail.replace('|', '\\u007c') in body for body in bodies)
    assert all('"x": 0.2' in body and '"y": 0.4' in body and 'EVIDENCED_BY' in body for body in bodies)
    receipt = json.loads((tmp_path / 'new/runtime_memory/frame-5-recall.json').read_text())['receipt']
    assert receipt['request']['stages'][0]['analytical']['timestamp_field'] == 'timestamp'
    assert all(h['start_byte'] == 0 for hs in receipt['citations'].values() for h in hs)
    later.close()


def test_schema_clock_and_observation_replay_remain_identical(tmp_path, text_memory_transport):
    detector = _load_detector()
    config = {'text_memory': {'enabled': True}}
    first = detector.CameraMemory(config, tmp_path, 'camera', 'source')
    observation = {'frame_seq': 1, 'camera_id': 'camera', 'batch_id': 'batch',
                   'observed_at': '2026-10-04T01:00:00Z', 'summary': 'sample'}
    first.remember(observation)
    before = dict(text_memory_transport.scopes[('test-memory-job', None)])
    first.close()
    repeated = detector.CameraMemory(config, tmp_path, 'camera', 'source')
    repeated.remember(observation)
    assert text_memory_transport.scopes[('test-memory-job', None)] == before
    assert all(body.startswith('#') for body in before.values())
    assert all(not json.loads((tmp_path / 'runtime_memory/frame-1-observation.json').read_text())['observation'].get(k)
               for k in ('source_uri', 'image_bytes'))
    repeated.close()


@pytest.mark.parametrize('change', [
    {'observed_at': None}, {'observed_at': '2026-10-04T01:00:00'}, {'camera_id': 'wrong-camera'},
])
def test_invalid_time_or_camera_scope_does_not_publish_observation(change, tmp_path, text_memory_transport):
    detector = _load_detector()
    memory = detector.CameraMemory({'text_memory': {'enabled': True}}, tmp_path, 'camera', 'source')
    before = dict(text_memory_transport.scopes[('test-memory-job', None)])
    with pytest.raises(ValueError):
        memory.remember({'frame_seq': 1, 'camera_id': 'camera', 'observed_at': '2026-10-04T01:00:00Z', **change})
    assert text_memory_transport.scopes[('test-memory-job', None)] == before
    memory.close()


def test_camera_source_and_job_are_query_boundaries(monkeypatch, tmp_path, text_memory_transport):
    detector = _load_detector()
    config = {'text_memory': {'enabled': True}}
    memory = detector.CameraMemory(config, tmp_path, 'camera', 'source-one')
    memory.remember({'frame_seq': 1, 'camera_id': 'camera', 'observed_at': '2026-10-04T01:00:00Z',
                     'summary': 'OTHER_SOURCE_CANARY'})
    memory.close()
    changed = detector.CameraMemory(config, tmp_path, 'camera', 'source-two')
    assert changed.recall(2)['status'] == 'no_evidence'
    changed.close()
    monkeypatch.setenv('MN_JOB_ID', 'other-job')
    unrelated = detector.CameraMemory(config, tmp_path, 'camera', 'source-one')
    assert unrelated.recall(3)['status'] == 'no_evidence'
    unrelated.close()
