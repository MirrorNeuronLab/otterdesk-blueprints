"""Retrospective questions review the retrieved saved image, without changing monitoring."""
import base64
import copy
import json

import pytest

from mn_context_engine_sdk import MediaReference
from cctv_operator.payloads.domain import history_vision, video_questions
from cctv_operator.payloads.domain.cosmos_access import reserve_calls


def packet():
    data = b'original saved people capture'
    ref = MediaReference.from_bytes(data, uri='artifact://cctv-history/camera/image.jpg', mime_type='image/jpeg')
    capture = {'media': ref.to_dict(), 'captured_at': '2026-10-31T10:00:00Z', 'frame_path': 'frame_batches/old/frame-01.jpg'}
    return {'history': {'status': 'ready', 'evidence': [{'citation': 'm1', 'content': '# Saved\nA person was near the doorway.',
                'captures': [capture]}], 'omitted_count': 0},
        'citations': {'m1': [{'source_id': 'job:original-account', 'revision': 'pinned', 'frames': [capture]}]},
        'frames': [{**capture, 'citation': 'm1', 'data': data}], 'qualification': 'Sampled historical footage only.'}


@pytest.fixture
def review(monkeypatch):
    config = {'visual_memory': {'enabled': True, 'max_review_frames': 2}, 'text_memory': {'enabled': True}}
    evidence, image_calls, text_calls = packet(), [], []
    monkeypatch.setenv('MN_LLM_MODEL', 'prepared-text-model')
    monkeypatch.setenv('MN_LLM_PROVIDER', 'docker_model_runner')
    monkeypatch.setenv('MN_LLM_API_BASE', 'http://prepared-text/v1')
    monkeypatch.setattr(video_questions.history_memory, 'search_video_history', lambda *a, **kw: copy.deepcopy(evidence))
    monkeypatch.setattr(history_vision, 'source_manifest', lambda *a, **kw: {'runtime': {'models': {'vision': {
        'model': 'declared-vision', 'provider': 'docker_model_runner', 'backend': 'vllm',
        'model_spec': {'id': 'declared-vision'}}}}})
    def image(*args, **kwargs):
        image_calls.append((args, kwargs))
        return {'choices': [{'finish_reason': 'stop', 'message': {'content': 'A person in a red coat stands beside the doorway.'}}]}
    def text(system, user, **kwargs):
        text_calls.append((system, json.loads(user), kwargs))
        return kwargs['validator']({'summary': 'At 10:00 on October 31, a person in a red coat stood beside the doorway.', 'citations': ['m1']})
    monkeypatch.setattr(history_vision, 'runtime_model_json_request', image)
    monkeypatch.setattr(video_questions, 'completion_json', text)
    return config, evidence, image_calls, text_calls


def test_history_answer_uses_the_actual_retrieved_image_and_original_capture_citation(review, tmp_path):
    config, evidence, images, texts = review
    result = video_questions.answer_video(config, tmp_path, 'later-run', 'Was anyone wearing red earlier?')
    assert len(images) == len(texts) == 1
    args, options = images[0]
    assert args[:3] == ('vlm', 'declared-vision', '/chat/completions')
    assert options['num_retries'] == 0 and options['backend'] == 'vllm'
    payload = args[3]
    raw = payload['messages'][1]['content'][0]['image_url']['url']
    assert base64.b64decode(raw.split(',', 1)[1]) == evidence['frames'][0]['data']
    assert payload['max_tokens'] <= 512
    history = texts[0][1]['history']
    assert history['evidence'][0]['historical_image_reviews'][0] == {
        'captured_at': '2026-10-31T10:00:00Z', 'media_sha256': evidence['frames'][0]['media']['sha256'],
        'description': 'A person in a red coat stands beside the doorway.'}
    assert 'data:image' not in json.dumps(history) and 'original saved people capture' not in json.dumps(history)
    assert result['reviewed_images'] == result['retrieved_images'] == 1
    assert result['citations'][0]['sources'][0]['revision'] == 'pinned'
    assert '2026-10-31T10:00:00Z' in json.dumps(result['citations'])
    assert 'Image similarity is candidate selection, not proof' in texts[0][0]
    assert texts[0][2]['config'].model == 'prepared-text-model'


def test_failed_or_truncated_historical_image_does_not_fall_back_to_a_text_answer(review, monkeypatch, tmp_path):
    config, _evidence, _images, texts = review
    monkeypatch.setattr(history_vision, 'runtime_model_json_request', lambda *a, **kw: {
        'choices': [{'finish_reason': 'length', 'message': {'content': 'A partial interpretation'}}]})
    with pytest.raises(ValueError, match='complete frame evidence'):
        video_questions.answer_video(config, tmp_path, 'later-run', 'What happened earlier?')
    assert not texts


def test_changed_retrieved_image_fails_before_model_dispatch(review, tmp_path):
    config, evidence, images, texts = review
    evidence['frames'][0]['data'] = b'a substituted image'
    with pytest.raises(ValueError, match='immutable reference'):
        video_questions.answer_video(config, tmp_path, 'later-run', 'What happened earlier?')
    assert not images and not texts


def test_history_review_shares_the_caption_request_budget_and_respects_smaller_runtime_limits(review, monkeypatch, tmp_path):
    config, _evidence, images, texts = review
    assert reserve_calls(tmp_path, 'active-camera-batches', 12, 12)
    with pytest.raises(RuntimeError, match='request limit'):
        video_questions.answer_video(config, tmp_path, 'later-run', 'What happened earlier?')
    assert not images and not texts
    other = tmp_path / 'separate-run'
    monkeypatch.setenv('MN_VLM_MAX_TOKENS', '128')
    monkeypatch.setenv('MN_VLM_TIMEOUT_SECONDS', '15')
    video_questions.answer_video(config, other, 'later-run', 'What happened earlier?')
    assert images[0][0][3]['max_tokens'] == 128 and images[0][1]['timeout_seconds'] == 15


def test_shared_image_admission_is_idempotent_and_ages_out(tmp_path):
    assert reserve_calls(tmp_path, 'caption-1', 2, 3, now=100)
    assert reserve_calls(tmp_path, 'caption-1', 2, 3, now=101)
    assert reserve_calls(tmp_path, 'history-1', 1, 3, now=101)
    assert not reserve_calls(tmp_path, 'caption-2', 1, 3, now=102)
    assert reserve_calls(tmp_path, 'caption-2', 1, 3, now=161)
    with pytest.raises(ValueError, match='changed'):
        reserve_calls(tmp_path, 'caption-2', 2, 3, now=162)


def test_image_review_context_admits_whole_accounts_and_prunes_omitted_citations(review, monkeypatch, tmp_path):
    config, evidence, images, texts = review
    config['visual_memory']['max_context_bytes'] = 2200
    evidence['history']['evidence'][0]['content'] = '# Original complete account\n' + 'A' * 400
    second = copy.deepcopy(evidence['history']['evidence'][0])
    second.update(citation='m2', content='# Another complete account\n' + 'B' * 400)
    evidence['history']['evidence'].append(second)
    evidence['citations']['m2'] = [{'source_id': 'job:other', 'revision': 'other'}]
    monkeypatch.setattr(history_vision, 'runtime_model_json_request', lambda *a, **kw: {
        'choices': [{'finish_reason': 'stop', 'message': {'content': 'Visible detail. ' * 45}}]})
    result = video_questions.answer_video(config, tmp_path, 'later-run', 'What happened earlier?')
    assert result['included_observations'] == 1 and result['omitted_observations'] == 1
    row = texts[0][1]['history']['evidence'][0]
    assert row['content'] == evidence['history']['evidence'][0]['content']
    assert len(json.dumps(texts[0][1]['history'], ensure_ascii=False).encode()) <= 2200
    with pytest.raises(ValueError, match='unavailable observation'):
        texts[0][2]['validator']({'summary': 'An unsupported omitted account', 'citations': ['m2']})
