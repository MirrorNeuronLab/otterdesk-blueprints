import base64
import json
import threading
from types import SimpleNamespace

import pytest

from cctv_operator.payloads.domain import perception, video_questions
from cctv_operator.payloads.domain.detection_policy import DEFAULT_MONITORING_GOAL
from mn_sdk_mcp import JobExchangeStore


def test_person_gate_treats_a_lone_person_as_positive():
    positive, reference = perception.gate_prompts(DEFAULT_MONITORING_GOAL)
    assert all('person' in prompt.lower() for prompt in positive)
    assert all('empty' in prompt.lower() for prompt in reference)
    assert not any('group' in prompt.lower() for prompt in positive)


def test_gate_debounces_retries_and_rearms_an_episode_after_quiet():
    state = {}
    positive = {'positive_similarity': .4, 'reference_similarity': .2}
    negative = {'positive_similarity': .1, 'reference_similarity': .3}
    def check(score, t, goal=DEFAULT_MONITORING_GOAL):
        return perception.admit_candidate(state, score, goal, t, {})
    assert check(positive, 100)['admit'] is False
    matched = check(positive, 101)
    assert matched['admit'] is True and matched['interpretation'] == 'candidate_only'
    assert check(positive, 102)['admit'] is False
    assert check(negative, 103)['admit'] is False
    assert check(negative, 104)['admit'] is False
    assert check(positive, 105)['admit'] is False
    repeated = check(positive, 106)
    assert repeated['admit'] is True and repeated['episode'] != matched['episode']
    assert check(positive, 107, 'Watch a box')['admit'] is False
    assert check(positive, 108, 'Watch a box')['admit'] is True
    episode = state['semantic_gate']['episode']
    assert check(positive, 200, 'Watch a box')['admit'] is False
    assert check(positive, 201, 'Watch a box')['episode'] == episode
    assert check(negative, 202, 'Watch a box')['admit'] is False
    assert check(negative, 203, 'Watch a box')['episode'] != episode
    with pytest.raises(ValueError):
        check({'positive_similarity': float('nan'), 'reference_similarity': .3}, 204)


def test_resident_gate_archives_nonmatching_frames(monkeypatch, tmp_path):
    saved = []
    encoder = SimpleNamespace(encode_image=lambda _: [1, 0], encode_text=lambda _: [0, 1])
    archive = SimpleNamespace(add=lambda *args: saved.append(args))
    owner = perception.CCTVPerception(tmp_path, 'run', {}, encoder=encoder, archive=archive)
    monkeypatch.setattr(perception, '_preview_bytes', lambda value: value)
    result = owner.request({'operation': 'score', 'image': base64.b64encode(b'jpeg').decode(),
                            'goal': DEFAULT_MONITORING_GOAL, 'timestamp': 100})
    assert result['positive_similarity'] == 0
    assert len(saved) == 1 and saved[0][4]['run_id'] == 'run'


def test_video_question_reads_complete_markdown_without_vision(monkeypatch, tmp_path, text_memory_transport):
    import hashlib
    from cctv_operator.payloads.domain.runtime_memory import CameraMemory
    monkeypatch.setenv('MN_RUN_ID', 'run')
    config = {'text_memory': {'enabled': True, 'max_context_bytes': 49152},
              'video_source': {'camera_id': 'camera', 'uri': 'rtsp://camera.example/test'},
              'llm': {'configs': {'primary': {'model': 'text-model', 'backend': 'llama.cpp'}}}}
    memory = CameraMemory(config, tmp_path, 'camera', hashlib.sha256(b'rtsp://camera.example/test').hexdigest())
    detail = 'Complete account with | and 中🙂. ' * 100
    memory.remember({'frame_seq': 1, 'camera_id': 'camera', 'batch_id': 'one',
        'observed_at': '2026-10-07T10:00:00Z', 'summary': 'One person in the aisle.',
        'scene_understanding': detail, 'frame_batch_ref': 'frame_batches/one/batch.json',
        'condition_screening': {'route': 'deep_analysis'}})
    memory.close()
    requests = []
    def text(system, user, **kwargs):
        requests.append((system, json.loads(user), kwargs))
        return kwargs['validator']({'summary': 'One person was visible at 10:00; a unique total cannot be determined.', 'citations': ['m1']})
    monkeypatch.setattr(video_questions, 'completion_json', text)
    result = video_questions.answer_video(config, tmp_path, 'run', 'How many people appeared so far?')
    assert result['citations'][0]['citation'] == 'm1' and result['citations'][0]['sources']
    assert result['included_observations'] == 1 and result['continuous_coverage'] is False
    assert detail.replace('|', '\\u007c') in requests[0][1]['history']['evidence'][0]['content']
    assert 'Never sum repeated frame counts' in requests[0][0]
    assert requests[0][2]['config'].model == 'text-model'
    assert 'image_input' not in requests[0][2]['config'].required_capabilities
    with pytest.raises(ValueError, match='unavailable observation'):
        requests[0][2]['validator']({'summary': 'Invented', 'citations': ['m99']})
    with pytest.raises(ValueError, match='supporting observations'):
        requests[0][2]['validator']({'summary': 'Uncited', 'citations': []})
    # The question path is scoped to this run, while the history tool spans runs.
    monkeypatch.setenv('MN_RUN_ID', 'later')
    assert video_questions.answer_video(config, tmp_path, 'later', 'How many people?')['history_status'] == 'no_evidence'
    assert len(requests) == 1


@pytest.mark.parametrize('status, enabled, message', [
    ('no_evidence', True, 'does not mean zero'),
    ('insufficient_capacity', True, 'exceed the history context capacity'),
    ('disabled', False, 'disabled'),
])
def test_missing_history_does_not_call_any_model(monkeypatch, tmp_path, status, enabled, message):
    monkeypatch.setattr(video_questions, 'read_video_history', lambda *a, **kw: {
        'history': {'status': status, 'evidence': []} if enabled else None,
        'qualification': 'Sampled only.', 'citations': {}})
    monkeypatch.setattr(video_questions, 'completion_json', lambda *a, **kw: pytest.fail('No model without history'))
    result = video_questions.answer_video({}, tmp_path, 'run', 'How many people?')
    assert message in result['summary'] and result['citations'] == []


def test_requested_review_is_async_bounded_idempotent_and_publishes_final_summary(monkeypatch, tmp_path):
    store = JobExchangeStore(tmp_path / 'commands.sqlite3', allowed_root=tmp_path, job_id='job', blueprint_id='cctv_operator', run_id='run')
    entered, finish = threading.Event(), threading.Event()
    def answer(*args, **kwargs):
        entered.set()
        assert finish.wait(5)
        return {'summary': 'The group appeared at 10:00. ' + 'Evidence. ' * 250 + 'Sampled evidence only.', 'citations': []}
    monkeypatch.setattr(video_questions, 'answer_video', answer)
    questions = video_questions.VideoQuestions(tmp_path, 'run', store, {})
    command = '11111111-1111-4111-8111-111111111111'
    result = questions.submit(command, 'When did the group appear?')
    assert result['state'] == 'accepted' and entered.wait(2)
    assert questions.submit(command, 'When did the group appear?')['state'] == 'accepted'
    assert questions.submit('22222222-2222-4222-8222-222222222222', 'Another question')['ok'] is False
    finish.set()
    # Taking capacity waits on actual completion rather than a fixed sleep.
    assert questions.capacity.acquire(timeout=5)
    questions.capacity.release()
    final = questions.status(command)
    assert final['state'] == 'completed' and final['summary'].startswith('The group appeared')
    assert final['summary'].endswith('Sampled evidence only.') and len(final['summary']) > 2000
    assert questions.status(command)['evidence']['citations'] == []


def test_quiet_gate_is_monitoring_even_when_last_verified_account_is_old():
    from cctv_operator.payloads.domain.dashboard import operator_state
    state = operator_state(run_id='run', config={}, report={'observations': [{'observed_at': 1, 'summary': 'Earlier scene'}]},
        latest_frame={}, monitoring={}, supplemental_events=[{'type': 'cctv_operator_candidate_gate_checked',
        'payload': {'sampled_at': 999, 'admit': False}}], preview_status='running', preview_warning='', now=1000)
    assert state['metrics']['status'] == 'Monitoring'
    assert state['metrics']['last sampled'] != 'waiting'
    assert state['warning'] == '' and state['events'][0]['summary'] == 'Earlier scene'


def test_failed_receipt_does_not_exhaust_review_capacity(tmp_path):
    def fail(*args, **kwargs):
        raise OSError('storage unavailable')
    store = SimpleNamespace(get_record=lambda *args, **kwargs: None, publish_status=fail)
    questions = video_questions.VideoQuestions(tmp_path, 'run', store, {})
    with pytest.raises(OSError, match='storage unavailable'):
        questions.submit('11111111-1111-4111-8111-111111111111', 'Question')
    assert questions.capacity.acquire(blocking=False)
    questions.capacity.release()
