"""Exercise the uploaded worker with a different same-version SDK on its host."""

import json
from importlib.metadata import distribution as installed_distribution
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys

from mn_sdk.blueprints import compile_blueprint, read_blueprint, resolve_config
from mn_sdk.blueprints.worker_descriptors import resolved_worker_descriptor
from mn_sdk.submission_preparation import (
    normalize_host_local_uploads,
    stage_sdk_payloads_for_manifest,
)

PACKAGE = Path(__file__).resolve().parents[1] / 'code_verifier'


def test_all_phases_start_at_the_uploaded_root_with_live_supervision():
    manifest = compile_blueprint(read_blueprint(PACKAGE)).manifest
    normalize_host_local_uploads(manifest)
    workers = [node['config'] for node in manifest['agents']['nodes']
               if node.get('agent_type') == 'executor']
    assert len(workers) == len(manifest['workflow']['steps']) == 5
    assert manifest['workflow']['execution']['supervision'] == 'activity'
    for worker in workers:
        assert worker['runner_module'] == 'MirrorNeuron.Runner.HostLocal'
        assert worker['upload_path'] == worker['upload_as'] == '.'
        assert worker['workdir'] == '/sandbox/job'
        assert worker['beacon_enabled'] and worker['agent_beacon_required']


def test_capture_uses_staged_components_and_still_rejects_changed_code(tmp_path):
    source = tmp_path / 'repository'
    source.mkdir()
    (source / 'SPEC.md').write_text('The software must reject an empty name.\n')
    (source / 'store.py').write_text('def save(name):\n    return bool(name)\n')
    package = read_blueprint(PACKAGE)
    configuration = resolve_config(package, {'inputs': {'payload': {'input_folder': str(source)}}})
    manifest = compile_blueprint(package, configuration).manifest
    normalize_host_local_uploads(manifest)
    worker = next(node['config'] for node in manifest['agents']['nodes']
                  if node.get('agent_type') == 'executor')

    workspace = tmp_path / 'worker'
    shutil.copytree(PACKAGE / 'payloads', workspace)
    payloads = {}
    stage_sdk_payloads_for_manifest(manifest, payloads, bundle_dir=PACKAGE)
    for name, content in payloads.items():
        path = workspace / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    descriptor = workspace / 'runtime/manifest.json'
    descriptor.parent.mkdir(exist_ok=True)
    descriptor.write_text(json.dumps(resolved_worker_descriptor(package, manifest, configuration)))

    # Model a remote host with the same package versions but different SDK code.
    # The staged bundle must take precedence without disabling the block check.
    installed = tmp_path / 'host-packages'
    shutil.copytree(workspace / 'mn_sdk', installed / 'mn_sdk')
    with (installed / 'mn_sdk/manifest_converter.py').open('a') as stream:
        stream.write('\n# Different SDK checkout on the execution computer.\n')
    for component in manifest['metadata']['mn_blocks_lock']['components']:
        distribution, version = component['distribution'], component['version']
        metadata = installed / f"{distribution.replace('-', '_')}-{version}.dist-info"
        metadata.mkdir()
        (metadata / 'METADATA').write_text(f'Name: {distribution}\nVersion: {version}\n')
        entry_points = installed_distribution(distribution).read_text('entry_points.txt')
        if entry_points:
            (metadata / 'entry_points.txt').write_text(entry_points)

    message = tmp_path / 'message.json'
    message.write_text(json.dumps({'body': {'step_input': {}}}))
    run_dir = tmp_path / 'run'
    environment = {
        **os.environ,
        **worker['environment'],
        'MN_HOME': str(tmp_path / 'mn'),
        'MN_BUNDLE_ROOT': str(workspace),
        'MN_BLUEPRINT_MANIFEST_PATH': str(descriptor),
        'MN_BLUEPRINT_CONFIG_JSON': json.dumps(configuration.data),
        'MN_SDK_COMPONENTS_JSON': '["blueprint-blocks"]',
        'MN_JOB_ID': 'code-verifier-worker-test',
        'MN_RUN_ID': 'capture-test',
        'MN_RUN_DIR': str(run_dir),
        'MN_JOB_DATA_DIR': str(tmp_path / 'job-data'),
        'MN_JOB_OUTPUT_DIR': str(tmp_path / 'outputs'),
        'MN_MESSAGE_FILE': str(message),
        'MN_WORKFLOW_IDEMPOTENCY_KEY': 'capture-test/1',
        'PYTHONPATH': os.pathsep.join([str(installed), *[str(Path(p).resolve()) for p in sys.path if p]]),
    }

    def invoke(directory):
        return subprocess.run(
            [sys.executable, '-B', '-m', 'mn_sdk.step_runtime',
             '--handler', worker['environment']['MN_WORKFLOW_STEP_HANDLER'],
             '--with-json', worker['environment']['MN_WORKFLOW_STEP_WITH_JSON']],
            cwd=directory, env=environment, capture_output=True, text=True, timeout=30,
        )

    wrong_directory = invoke(descriptor.parent)
    assert wrong_directory.returncode != 0
    assert 'Block worker component code differs' in wrong_directory.stderr
    assert not (run_dir / 'capture.json').exists()

    directory = workspace / PurePosixPath(worker['workdir']).relative_to('/sandbox/job')
    captured = invoke(directory)
    assert captured.returncode == 0, captured.stderr
    assert json.loads((run_dir / 'capture.json').read_text())['sources'] == {
        path.name: path.read_text() for path in source.iterdir()
    }
    with (workspace / 'mn_sdk/manifest_converter.py').open('a') as stream:
        stream.write('\n# Changed after compilation.\n')
    tampered = invoke(directory)
    assert tampered.returncode != 0
    assert 'Block worker component code differs' in tampered.stderr
