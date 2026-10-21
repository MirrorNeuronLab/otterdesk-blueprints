"""Completion gates for native block implementation, beyond worker coverage.

A stock worker invoking a legacy operation adapter does not satisfy these gates.
Every catalog package stays parametrized so future changes cannot reintroduce
legacy boundaries behind rollout flags or selective skips.
"""
import ast
import json
from pathlib import Path

import pytest
from mn_sdk.blueprints import blueprint_definition, compile_blueprint, read_blueprint

ROOT = Path(__file__).resolve().parents[1]
CATALOG = json.loads((ROOT / 'index.json').read_text())
LEGACY_BOUNDARIES = {'runtime_context_for_step', 'execute_runtime_handler',
    'create_domain_message_agent', '_phase', '_block_operation', '_context', '_task'}


def _hook_failures(root, reference):
    module, symbol = reference.split(':')
    if module.startswith(('mn_sdk.', 'mn_blueprint_blocks.')):
        return []  # A directly referenced stock hook owns its public contract.
    if not module.startswith('domain.'):
        return [f'{reference}: hook must be a native domain function or stock block hook']
    path = root / 'payloads' / Path(*module.split('.')).with_suffix('.py')
    if not path.is_file():
        return [f'{reference}: unresolved native hook source']
    definitions = {getattr(node, 'name', None): node for node in ast.parse(path.read_text()).body
                   if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}
    if symbol not in definitions:
        return [f'{reference}: hook is an alias/factory binding rather than a native implementation']
    node = definitions[symbol]
    called = {call.func.id if isinstance(call.func, ast.Name) else call.func.attr
              for call in ast.walk(node) if isinstance(call, ast.Call)
              and isinstance(call.func, (ast.Name, ast.Attribute))}
    return [f'{reference}: invokes legacy boundary {name}' for name in sorted(called & LEGACY_BOUNDARIES)]


@pytest.mark.parametrize('blueprint_id', CATALOG)
def test_all_catalog_phases_are_native_blocks_without_legacy_adapters(blueprint_id):
    root = ROOT / blueprint_id
    package = read_blueprint(root)
    source = blueprint_definition(package)
    compiled = compile_blueprint(package).manifest
    nodes = {node['node_id']: node for node in compiled['agents']['nodes']}
    source_steps = {step['id']: step for step in source['workflow']['steps']}
    failures, instances = [], []
    for step in compiled['workflow']['steps']:
        members = step.get('agent_ids') or [step.get('agent_id') or
            source_steps[step['id']].get('run', {}).get('agent') or step['id']]
        workers = [nodes[key] for key in members if key in nodes and nodes[key]['agent_type'] == 'executor']
        if not workers:
            failures.append(f'{step["id"]}: no native block implementation')
        for worker in workers:
            config = worker['config']
            # Compose is a prebuilt Core lifecycle component, not a Python shim.
            if config.get('runner_module') == 'MirrorNeuron.Runner.DockerCompose':
                continue
            environment = config.get('environment', {})
            if environment.get('MN_WORKFLOW_STEP_HANDLER') != 'mn_sdk.integrations.block_worker':
                failures.append(f'{step["id"]}: custom executor instead of a block')
            parameters = json.loads(environment.get('MN_WORKFLOW_STEP_WITH_JSON', '{}'))
            if 'instance' in parameters:
                instances.append(parameters['instance'])
    lock = compiled.get('metadata', {}).get('mn_blocks_lock', {})
    for collection in ['steps', 'services', 'operations', 'events']:
        instances.extend(lock.get(collection, {}).values())
    for child in compiled['workflow'].get('child_workflows', {}).values():
        for name, template in child.get('templates', {}).items():
            implementation = template.get('implementation', {})
            if implementation.get('handler') != 'mn_sdk.integrations.block_worker':
                failures.append(f'{name}: child worker still uses a legacy handler')
            parameters = implementation.get('with', {})
            if 'instance' in parameters:
                instances.append(parameters['instance'])
    for instance in instances:
        if instance.get('adapters'):
            failures.append(f'{instance["uses"]}: blueprint-owned capability adapters remain')
        for reference in instance.get('hooks', {}).values():
            failures.extend(_hook_failures(root, reference))
    assert not failures, '\n'.join(dict.fromkeys(failures))
