"""Historical context must reach vision without becoming current-image proof."""

import hashlib
import json

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
        'detection_count': 0, 'detections': [], 'condition_screening': {'route': 'review_declined'}})
    record = json.loads((tmp_path / 'runtime_memory/frame-1-observation.json').read_text())['observation']
    assert record['detection_count'] is None and record['qualification'] == 'screening_only_or_detail_unavailable'
    memory.close()
