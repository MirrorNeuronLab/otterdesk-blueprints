"""Offline compiled-handler fixture, without Core scheduling or native execution.

Samples run the installed block workers and the compiled source/sink mappings.
Core's parallel scheduling, durable joins, retry, and child workflows are tested
separately; this fixture executes dependency-ready branches serially.
"""
import json
import os
from pathlib import Path
from uuid import uuid4

from mn_sdk.blueprints import compile_blueprint, read_blueprint, resolve_config
from mn_sdk.blueprints.worker_descriptors import resolved_worker_descriptor
from mn_sdk.components import ComponentRegistry
from mn_sdk.step_runtime import StepContext, invoke_handler
from mn_sdk_common.committed_artifacts import CommittedJsonStore
from mn_sdk.blueprint_support.local_inputs import stage_local_input_payloads, config_path_get, config_path_set, linked_config_paths


def run_sample(blueprint_id, *, inputs=None, config=None, runs_root=None, run_id=None, llm_client=None, through_step=None):
    inputs = dict(inputs or {})
    root = Path(__file__).resolve().parents[1] / blueprint_id
    package = read_blueprint(root)
    configuration = resolve_config(package, config or {})
    run_id = run_id or f'sample-{uuid4().hex}'
    run_dir = Path(runs_root) / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    runtime_config = configuration.data
    run_values = {"inputs": {"payload": inputs}}
    specifications = [item for kind in ("folders", "files") for item in runtime_config.get("local_inputs", {}).get(kind, [])]
    for specification in specifications:
        for path in [specification["config_path"], *linked_config_paths(specification)]:
            value = config_path_get(run_values, path)
            if isinstance(value, str) and value.strip() not in {"", "."}:
                config_path_set(runtime_config, specification["config_path"], value)
                break
    payloads = {}
    staged = stage_local_input_payloads(runtime_config, payloads, bundle_dir=root)
    worker = CommittedJsonStore(run_dir / "fixture-payloads")
    for path, content in payloads.items():
        worker.commit_bytes(path, content, kind="fixture_input")
    for item in staged["folders"]:
        selected = str((worker.run_dir / "runtime" / item["runtime_path"]).resolve())
        config_path_set(runtime_config, item["config_path"], selected)
        config_path_set(run_values, item["config_path"], selected)
        for specification in specifications:
            if specification["config_path"] == item["config_path"]:
                for linked in linked_config_paths(specification):
                    config_path_set(runtime_config, linked, selected)
                    config_path_set(run_values, linked, selected)
    configuration = resolve_config(package, runtime_config)
    compiled = compile_blueprint(package, configuration).manifest
    descriptor = run_dir / 'fixture-manifest.json'
    descriptor.write_text(json.dumps(resolved_worker_descriptor(package, compiled, configuration)))
    environment = {**os.environ, 'MN_WORKDIR': str(worker.run_dir / 'runtime'), 'MN_RUN_ID': run_id, 'MN_RUN_DIR': str(run_dir),
        'MN_RUNS_ROOT': str(run_dir.parent), 'MN_BLUEPRINT_BUNDLE_DIR': str(root),
        'MN_BLUEPRINT_MANIFEST_PATH': str(descriptor),
        'MN_SDK_COMPONENTS_JSON': json.dumps(sorted(ComponentRegistry.from_manifest(compiled).enabled))}
    if inputs.get("output_folder") and not os.environ.get("MN_JOB_OUTPUT_DIR"):
        environment["MN_JOB_OUTPUT_DIR"] = str(Path(inputs["output_folder"]).expanduser().resolve())
    store = CommittedJsonStore(run_dir)
    nodes = {node['node_id']: node for node in compiled['agents']['nodes']}
    upstream = {}
    previous_environment = dict(os.environ)

    def mapped(value, flow=None):
        if isinstance(value, dict):
            reference = value.get('$ref')
            if reference in {'run_input', 'upstream', 'flow_output'}:
                selected = {'run_input': run_values['inputs']['payload'], 'upstream': upstream.get(value.get('step_id')), 'flow_output': flow}[reference]
                for part in value.get('path', []):
                    selected = selected.get(part) if isinstance(selected, dict) else None
                return selected
            return {key: mapped(item, flow) for key, item in value.items()}
        if isinstance(value, list):
            return [mapped(item, flow) for item in value]
        return value

    def execute(flow, payload, step_id):
        if flow['type'] == 'sequence':
            for item in flow['items']:
                payload = execute(item, payload, step_id)
            return payload
        if flow['type'] == 'parallel':
            return {item.get('alias', item.get('agent_id')): execute(item, payload, step_id) for item in flow['items']}
        assert flow['type'] == 'agent', 'The fixture does not execute child workflows.'
        call = flow.get('alias', flow['agent_id'])
        node = nodes[f'{step_id}__{call}']
        binding = node['config']['environment']
        context = StepContext(step_id=step_id, agent_id=flow['agent_id'], run_id=run_id,
            job_id=environment.get('MN_JOB_ID') or f'offline:{blueprint_id}',
            invocation_id=binding['MN_WORKFLOW_INVOCATION_ID'],
            idempotency_key=f'{run_id}/{step_id}/{call}', environment=environment,
            config=configuration.data, message={'body': {'step_input': payload}})
        parameters = json.loads(binding['MN_WORKFLOW_STEP_WITH_JSON'])
        return invoke_handler(binding['MN_WORKFLOW_STEP_HANDLER'], context=context,
            parameters={**parameters, 'resources': {'llm': llm_client} if llm_client else {}})['outputs']

    try:
        os.environ.update(environment)
        for step in compiled['workflow']['steps']:
            assert set(step.get('needs', [])) <= set(upstream)
            spec = step['implementation']['step_graph']
            flow = execute(spec['flow'], mapped(spec['input']['fields']), step['id'])
            upstream[step['id']] = mapped(spec['output']['fields'], flow)
            if step['id'] == through_step:
                payload = store.read(flow['result']) if isinstance(flow, dict) and 'result' in flow else flow
                return {**payload, 'outputs': payload, 'workflow_step_id': step['id'],
                    'run_id': run_id, 'runtime_step_mode': 'agent_invocation',
                    'status': payload.get('status', 'completed'), 'upstream_outputs': upstream}
        if through_step is not None:
            raise ValueError('Unknown compiled workflow step: ' + through_step)
        final = store.read_path('final_artifact.json')
        status = 'completed_with_fallback' if (final.get('llm_generation') or {}).get('status') == 'completed_with_fallback' else 'completed'
        return {'run_id': run_id, 'blueprint_id': package.manifest['id'], 'status': status, 'final_artifact': final, 'upstream_outputs': upstream}
    finally:
        os.environ.clear()
        os.environ.update(previous_environment)
