"""Opt-in real Rust/DuckDB/RPC history flow; model responses stay deterministic."""
import base64
from datetime import datetime, timezone
import hashlib
import io
import os
from pathlib import Path
import socket
import subprocess

import grpc
import pytest

pytestmark = pytest.mark.skipif(not os.environ.get('MN_TEST_MEMBRANE_BINARY'),
    reason='Set MN_TEST_MEMBRANE_BINARY to the source-built Membrane engine')


def test_native_membrane_retrieves_an_old_people_image_and_answers_with_its_capture_provenance(tmp_path, monkeypatch):
    from PIL import Image, ImageDraw
    from mn_context_engine_sdk import EvidenceClient
    from mn_sdk.context_embeddings import RuntimeEmbeddings
    from cctv_operator.payloads.domain import history_memory, history_vision, video_questions

    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        port = listener.getsockname()[1]
    binary = Path(os.environ['MN_TEST_MEMBRANE_BINARY']).resolve(strict=True)
    environment = {**os.environ, 'MN_CONTEXT_ADDR': f'127.0.0.1:{port}',
        'MN_CONTEXT_FS_MEMORY_ROOT': str(tmp_path / 'native-memory'), 'MN_CONTEXT_AUTH_TOKEN': 'local-history-test'}
    log = (tmp_path / 'engine.log').open('w+')
    process = subprocess.Popen([str(binary)], env=environment, stdout=log, stderr=log)
    ready = grpc.insecure_channel(f'127.0.0.1:{port}')
    owner = None
    try:
        grpc.channel_ready_future(ready).result(timeout=10)
        def client(job_id, run_id, principal, **options):
            channel = grpc.insecure_channel(f'127.0.0.1:{port}')
            result = EvidenceClient(channel, job_id=job_id, run_id=run_id, principal=principal,
                auth_token='local-history-test')
            result.close = channel.close
            return result
        monkeypatch.setattr('mn_sdk.source_query.runtime_client', client)
        monkeypatch.setenv('MN_JOB_ID', 'camera-job')
        monkeypatch.setenv('MN_WORKFLOW_RUN_ID', 'later-run')
        monkeypatch.setenv('MN_JOB_DATA_DIR', str(tmp_path / 'camera-job'))
        monkeypatch.setenv('MN_LLM_MODEL', 'synthetic-text')
        monkeypatch.setenv('MN_LLM_PROVIDER', 'docker_model_runner')
        monkeypatch.setenv('MN_LLM_API_BASE', 'http://synthetic-text/v1')
        old_image = Image.new('RGB', (64, 64), 'white')
        draw = ImageDraw.Draw(old_image)
        draw.ellipse((27, 6, 37, 16), fill='black')
        draw.rectangle((24, 18, 40, 41), fill='red')
        draw.line((27, 41, 22, 60), fill='black', width=3)
        draw.line((37, 41, 42, 60), fill='black', width=3)
        encoded = io.BytesIO()
        old_image.save(encoded, 'JPEG')
        original = encoded.getvalue()
        model_inputs = []
        def embed(purpose, model, path, payload, **options):
            assert purpose == 'embedding' and path == '/embeddings' and options['num_retries'] == 0
            model_inputs.append(payload)
            item = payload['input'][0]
            if isinstance(item, str):
                position = 0 if item.startswith('task: search result | query: ') else 2
            else:
                assert len(item['content']) == 1
                data = base64.b64decode(item['content'][0]['image_url']['url'].split(',', 1)[1])
                position = 0 if data == original else 1
            vector = [0.] * 768
            vector[position] = 1.
            return {'data': [{'index': 0, 'embedding': vector}], 'usage': {'prompt_tokens': 100}}
        monkeypatch.setattr('mn_sdk.context_embeddings.runtime_model_json_request', embed)
        config = {'text_memory': {'enabled': True}, 'visual_memory': {'enabled': True, 'max_context_bytes': 49152},
            'video_source': {'camera_id': 'entrance', 'uri': 'rtsp://approved-camera/view'}}
        owner = history_memory.open_history(config, job_directory=tmp_path / 'camera-job',
            scope={'job_id': 'camera-job', 'run_id': 'old-run'}, embeddings=RuntimeEmbeddings(env={}))
        first_capture = None
        for n in range(15):
            timestamp = 1793500000 + n * 10
            captured_at = datetime.fromtimestamp(timestamp, timezone.utc).isoformat().replace('+00:00', 'Z')
            data = original
            if n:
                ordinary = Image.new('RGB', (64, 64), 'gray')
                drawing = ImageDraw.Draw(ordinary)
                drawing.ellipse((27, 6, 37, 16), fill='black')
                drawing.rectangle((24, 18, 40, 41), fill='blue')
                drawing.text((2, 45), str(n), fill='white')
                output = io.BytesIO()
                ordinary.save(output, 'JPEG')
                data = output.getvalue()
            identifier = hashlib.sha256(f'camera-sample-{n}'.encode()).hexdigest()
            recorded = {'markdown': f'# Complete sampled account {n}\n\nA person was visible by the doorway.\n',
                'observation': {'observation_id': identifier, 'camera_id': 'entrance',
                    'source_key': owner.store.identity['source_key'], 'run_id': 'old-run',
                    'observed_at': captured_at, 'batch_id': f'batch-{n}',
                    'frame_batch_ref': f'frame_batches/batch-{n}/batch.json', 'source_profile': 'external'}}
            batch = {'batch_id': f'batch-{n}', 'selected_frames': [{'timestamp': timestamp,
                'sha256': hashlib.sha256(data).hexdigest(), 'path': f'frame_batches/batch-{n}/frame-01.jpg'}]}
            owner.remember(recorded, batch, [data])
            first_capture = first_capture or captured_at
        owner.close()
        owner = None
        reviews = []
        monkeypatch.setattr(history_vision, 'source_manifest', lambda *a, **kw: {'runtime': {'models': {'vision': {
            'model': 'synthetic-vision', 'provider': 'docker_model_runner', 'backend': 'vllm',
            'model_spec': {'id': 'synthetic-vision'}}}}})
        def describe(*args, **options):
            image = args[3]['messages'][1]['content'][0]['image_url']['url']
            data = base64.b64decode(image.split(',', 1)[1])
            reviews.append(data)
            description = ('A person in a red coat stands by the doorway.' if data == original
                else 'A person in blue stands in the saved image.')
            return {'choices': [{'finish_reason': 'stop', 'message': {'content': description}}]}
        monkeypatch.setattr(history_vision, 'runtime_model_json_request', describe)
        def answer(system, user, **options):
            import json
            evidence = json.loads(user)['history']['evidence']
            assert evidence[0]['historical_image_reviews'][0]['captured_at'] == first_capture
            return options['validator']({'summary': 'A person in a red coat was visible in the earlier saved capture.', 'citations': ['m1']})
        monkeypatch.setattr(video_questions, 'completion_json', answer)
        result = video_questions.answer_video(config, tmp_path / 'later', 'later-run', 'Who wore red earlier?')
        assert reviews[0] == original
        handle = result['citations'][0]['sources'][0]
        assert handle['captured_run_id'] == 'old-run'
        assert handle['frames'][0]['captured_at'] == first_capture
        assert handle['frames'][0]['media']['sha256'] == hashlib.sha256(original).hexdigest()
        assert handle['frames'][0]['source_revision']
        assert result['reviewed_images'] == 2 and result['continuous_coverage'] is False
        assert not (tmp_path / 'later/monitoring_state.json').exists()
        assert len([p for p in model_inputs if isinstance(p['input'][0], dict)]) == 15
        later = history_memory.open_history(config)
        try:
            assert later.search('Summarize', current_run=True)['history']['status'] == 'no_evidence'
            # Rebuilt locators cannot claim old disposable vectors are present.
            later.session.client.reindex()
            assert later.search('Who wore red earlier?')['history']['status'] == 'index_incomplete'
        finally:
            later.close()
    finally:
        if owner is not None:
            owner.close()
        ready.close()
        process.terminate()
        process.wait(timeout=5)
        log.close()
