"""Exercise the lab's hardware floor through the actual placement contract."""

from pathlib import Path

import pytest

from mn_sdk.blueprints import compile_blueprint, read_blueprint
from mn_sdk.workflow_placement import resolve_and_apply_workflow_placement


ROOT = Path(__file__).resolve().parents[1] / 'web_lab_operator'


def runtime_node(name, vendor, memory_mb, *, local):
    return {
        'name': name, 'status': 'healthy', 'self': local, 'scheduling_eligible': True,
        'coordination_store': {'identity': 'test-cluster', 'healthy': True, 'writable_primary': True},
        'devices': [{'id': name + '-gpu', 'kind': 'gpu', 'vendor': vendor,
                     'type': 'integrated_gpu' if vendor == 'apple' else 'gpu',
                     'memory_total_mb': memory_mb, 'memory_free_mb': memory_mb}],
        'hardware': {
            'cpu': {'logical_processors': 12}, 'memory': {'total_mb': 64 * 1024},
            'disk': {'available_mb': 128 * 1024},
            'native_sdk_grpc': {'enabled': True, 'target': name + ':55052',
                                'capabilities': ['exclusive_run_v1', 'docker_worker_prepare_v1']},
        },
    }


def test_lab_compiles_a_hard_48_gb_job_requirement():
    package = read_blueprint(ROOT)
    required = {'min_count': 1, 'min_memory_mb': 48 * 1024,
                'memory_operator': '>=', 'enforcement': 'hard'}
    assert package.document('execution')['requirements']['gpu'] == required
    assert compile_blueprint(package).manifest['requirements']['gpu'] == required


@pytest.mark.parametrize('vendor', ['nvidia', 'amd', 'apple'])
@pytest.mark.parametrize('memory_mb', [48 * 1024, 128 * 1024])
def test_lab_places_on_qualifying_gpu_of_any_vendor(tmp_path, monkeypatch, vendor, memory_mb):
    monkeypatch.setenv('MN_HOME', str(tmp_path / 'mn'))
    manifest = compile_blueprint(read_blueprint(ROOT)).manifest
    nodes = [runtime_node('mini', 'apple', 24 * 1024, local=True),
             runtime_node('qualified', vendor, memory_mb, local=False)]

    placement = resolve_and_apply_workflow_placement(
        manifest, resource_report={'nodes': nodes}, system_summary={'nodes': nodes}, env={})

    assert placement['selected_node'] == 'qualified'
    assert placement['requirements']['min_gpu_memory_mb'] == 48 * 1024
    assert placement['requirements']['requires_nvidia'] is False
    for node in manifest['agents']['nodes']:
        assert any(constraint.get('attribute') == 'node.name'
                   and constraint.get('value') == 'qualified' for constraint in node['constraints'])


@pytest.mark.parametrize('memory_mb', [24 * 1024, 48 * 1024 - 1])
def test_lab_rejects_gpu_below_48_gb(tmp_path, monkeypatch, memory_mb):
    monkeypatch.setenv('MN_HOME', str(tmp_path / 'mn'))
    manifest = compile_blueprint(read_blueprint(ROOT)).manifest
    nodes = [runtime_node('mini', 'apple', memory_mb, local=True)]

    with pytest.raises(RuntimeError, match='gpu_memory'):
        resolve_and_apply_workflow_placement(
            manifest, resource_report={'nodes': nodes}, system_summary={'nodes': nodes}, env={})


def test_lab_cannot_force_24_gb_mini_when_spark_is_available(tmp_path, monkeypatch):
    monkeypatch.setenv('MN_HOME', str(tmp_path / 'mn'))
    manifest = compile_blueprint(read_blueprint(ROOT)).manifest
    nodes = [runtime_node('mini', 'apple', 24 * 1024, local=True),
             runtime_node('spark', 'nvidia', 128 * 1024, local=False)]

    with pytest.raises(RuntimeError, match='gpu_memory'):
        resolve_and_apply_workflow_placement(
            manifest, resource_report={'nodes': nodes}, system_summary={'nodes': nodes},
            env={'MN_SELECTED_RUNTIME_NODE': 'mini'})
