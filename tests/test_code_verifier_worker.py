"""Exercise the uploaded worker with a different same-version SDK on its host."""

from pathlib import Path

from mn_sdk.blueprints import compile_blueprint, read_blueprint
from mn_sdk.dependencies.wit import compose_wit_agents
from mn_sdk.submission_preparation import normalize_host_local_uploads

PACKAGE = Path(__file__).resolve().parents[1] / 'software_verifier_suite'


def test_all_phases_start_at_the_uploaded_root_with_live_supervision():
    manifest = compile_blueprint(read_blueprint(PACKAGE)).manifest
    normalize_host_local_uploads(manifest)
    workers = [node['config'] for node in manifest['agents']['nodes']
               if node.get('agent_type') == 'executor']
    assert len(manifest['workflow']['steps']) == 7
    assert len(workers) == 7 + len(manifest['workflow']['child_workflows']['coordinate_verification']['templates'])
    assert manifest['workflow']['execution']['supervision'] == 'activity'
    native = [worker for worker in workers if worker['runner_module'] == 'MirrorNeuron.Runner.Wasmtime']
    assert len(native) == len(workers)
    assert all(worker['beacon_enabled'] and worker['agent_beacon_required'] for worker in workers)
    operations = {worker['wasm_config']['operation'] for worker in native}
    assert {'admit', 'coordinate', 'plan-round', 'review-rules', 'publish-suite'} <= operations
    assert all('command' not in worker for worker in native)
    assert all(worker.get('wasm_capabilities') for worker in native if worker['wasm_config']['operation'] != 'admit')


def test_changed_submitted_wasm_is_rejected_before_capture(tmp_path):
    from wit_workflow_fixture import invoke_phase
    import pytest

    package = read_blueprint(PACKAGE)
    manifest = compile_blueprint(package).manifest
    payloads = {}
    targets = compose_wit_agents(manifest, payloads, PACKAGE)
    capture = next(n['config'] for n in manifest['agents']['nodes'] if n.get('config',{}).get('wasm_config',{}).get('operation')=='coordinator-capture')
    assert capture['wasm_component'] in targets
    component = tmp_path / capture['wasm_component']
    component.parent.mkdir(parents=True)
    component.write_bytes(payloads[capture['wasm_component']] + b'tampered')
    with pytest.raises(ValueError,match='submission digest'):
        invoke_phase(capture,{}, {'MN_BUNDLE_ROOT':str(tmp_path),'MN_RUN_DIR':str(tmp_path/'run'),'MN_RUN_ID':'capture-test'})
    assert not (tmp_path/'run'/'capture.json').exists()
