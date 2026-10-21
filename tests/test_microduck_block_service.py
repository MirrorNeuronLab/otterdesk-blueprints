"""Stock service supervision around a real ASGI listener, with no browser physics."""
import importlib
import json
from pathlib import Path
import shutil

import pytest
from mn_sdk.blueprints import compile_blueprint, read_blueprint
from mn_sdk.blueprints.worker_descriptors import resolved_worker_descriptor
from mn_sdk.integrations.block_worker import run
from mn_sdk.step_runtime import StepContext
from mn_sdk_common.committed_artifacts import CommittedJsonStore

ROOT = Path(__file__).resolve().parents[1] / 'microduck_controller'


@pytest.mark.parametrize('failure', [None, 'startup', 'health'])
def test_service_block_stops_listener_after_completion_or_partial_start(tmp_path, monkeypatch, failure):
    root = tmp_path / 'blueprint'
    shutil.copytree(ROOT, root, ignore=shutil.ignore_patterns('__pycache__'))
    extension = root / 'extensions/blocks.json'
    value = json.loads(extension.read_text())
    value['steps']['run_microduck_service']['config'].update(max_cycles=2, interval_seconds=0)
    extension.write_text(json.dumps(value))
    static = tmp_path / 'static'
    static.mkdir()
    (static / 'index.html').write_text('<!doctype html><title>Listener fixture</title>')
    monkeypatch.syspath_prepend(str(root / 'payloads'))
    lifecycle = importlib.import_module('domain.service_lifecycle')
    service = importlib.import_module('services.duck_control_service')
    listeners = []
    original = service._open_listener

    def listener(host, port):
        sock, actual = original(host, port)
        listeners.append(sock)
        return sock, actual

    monkeypatch.setattr(service, '_open_listener', listener)
    if failure == 'startup':
        def failed(**kwargs):
            raise RuntimeError('injected ASGI construction failure')
        monkeypatch.setattr(service, 'create_app', failed)
    if failure == 'health':
        monkeypatch.setattr(lifecycle, 'health', lambda block, inputs: False)
    package = read_blueprint(root)
    compiled = compile_blueprint(package).manifest
    descriptor = tmp_path / 'worker.json'
    descriptor.write_text(json.dumps(resolved_worker_descriptor(package, compiled)))
    for key, value in {'MN_BLUEPRINT_MANIFEST_PATH': descriptor, 'MN_RUN_DIR': tmp_path / 'run',
        'MN_BLUEPRINT_BUNDLE_DIR': root, 'MN_SDK_COMPONENTS_JSON': '["blueprint-blocks"]',
        'MICRODUCK_STATIC_DIR': static}.items():
        monkeypatch.setenv(key, str(value))
    context = StepContext(step_id='run_microduck_service', run_id='listener-fixture',
        idempotency_key='listener-fixture/service', message={'body': {'step_input': {}}},
        config={'web_ui': {'service': {'host': '127.0.0.1', 'listen_host': '127.0.0.1', 'port': 0}}})
    resources = {}
    options = {'block_step_id': 'run_microduck_service', 'revision': compiled['metadata']['mn_blocks_lock']['revision'], 'resources': resources}
    if failure:
        with pytest.raises(Exception, match='injected|health'):
            run(context, **options)
    else:
        result = run(context, **options)
        assert CommittedJsonStore(tmp_path / 'run').read(result.outputs['result'])['cycles_completed'] == 2
        assert run(context, **options) == result
    assert listeners and all(sock.fileno() == -1 for sock in listeners)
    assert 'worker' not in resources or not resources['worker'].is_alive()
