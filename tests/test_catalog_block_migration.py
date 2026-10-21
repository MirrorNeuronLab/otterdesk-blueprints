"""Catalog-wide composition contracts for the migration to stock blocks."""
import importlib
import json
from pathlib import Path

import pytest
from mn_blueprint_blocks import validate_instance
from mn_sdk.blueprints import blueprint_definition, compile_blueprint, read_blueprint
from mn_sdk.blueprints.block_lock import block_revision

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = json.loads((Path(__file__).parent / 'fixtures/block_migration_topology.json').read_text())


@pytest.mark.parametrize('blueprint_id', list(GOLDEN))
def test_catalog_uses_stock_blocks_and_preserves_product_composition(blueprint_id, monkeypatch):
    root = ROOT / blueprint_id
    monkeypatch.syspath_prepend(str(root / 'payloads'))
    package = read_blueprint(root)
    source = blueprint_definition(package)
    compiled = compile_blueprint(package).manifest
    expected = GOLDEN[blueprint_id]
    assert [{'id': step['id'], 'needs': step.get('needs', [])} for step in source['workflow']['steps']] == expected['steps']
    assert source['workflow'].get('edges', []) == expected['edges']
    workers = [node for node in compiled['agents']['nodes']
               if (node.get('config', {}).get('environment', {}).get('MN_WORKFLOW_STEP_HANDLER') or '').startswith('mn_sdk.integrations.block_')]
    assert workers, 'Every catalog blueprint must use a stock block worker.'
    assert any(item['name'] == 'mn-blueprint-blocks' for item in source['packages'])
    for step_id, flow in expected['collaboration'].items():
        actual = next(step for step in compiled['workflow']['steps'] if step['id'] == step_id)
        assert actual['implementation']['step_graph']['flow'] == flow
    lock = compiled.get('metadata', {}).get('mn_blocks_lock')
    instances = []
    if lock:
        assert block_revision(lock['source_revision'], lock['components'], lock['steps'],
            services=lock.get('services'), operations=lock.get('operations'), events=lock.get('events')) == lock['revision']
        for collection in ['steps', 'services', 'operations', 'events']:
            instances.extend(lock.get(collection, {}).values())
    for node in workers:
        parameters = json.loads(node['config']['environment']['MN_WORKFLOW_STEP_WITH_JSON'])
        if 'instance' in parameters:
            assert parameters['revision'] == f'{blueprint_id}@{package.manifest["version"]}'
            instances.append(parameters['instance'])
    for instance in instances:
        validated = validate_instance(instance)
        for reference in validated.hooks.values():
            module, function = reference.split(':')
            assert callable(getattr(importlib.import_module(module), function))
    for identifier, contract in expected['native'].items():
        node = next(node for node in compiled['agents']['nodes'] if node['node_id'] == identifier)
        assert node.get('resources') == contract['resources']
        assert node.get('constraints') == contract['constraints']
        assert node['config'].get('runner_module') == contract['runner_module']
