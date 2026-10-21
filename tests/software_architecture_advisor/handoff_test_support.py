"""Domain test adapter using Core's actual seal and immutable publication code."""
import importlib.util
import json
import os
from pathlib import Path
import sys
from unittest.mock import patch
from workspace_paths import companion_workspace


def review_task(ctx, reference, node, model):
    from dataclasses import asdict
    from mn_sdk.integrations.block_worker import run
    from mn_sdk.step_runtime import StepContext
    from domain.review_admission import reconcile
    from domain.catalog_store import CatalogStore
    from mn_sdk.artifact_handoff import resolve_committed, store_root, reference_key
    core = companion_workspace(Path(__file__).resolve().parents[2]) / 'MirrorNeuron/priv/openshell_handoff'
    if str(core) not in sys.path: sys.path.insert(0, str(core))
    import store as core_store
    import worker as core_worker
    from files import write
    identity={'job_id':'test','run_id':os.environ['MN_WORKFLOW_RUN_ID'],'step_instance':node['id'],'attempt':1,'lease_epoch':1}
    base={'root':str(store_root()),'identity':identity}
    state=core_store.handle({**base,'op':'begin','request_hash':node['review_input']['sha256'],'workspace':str(Path(ctx['run_dir'])/'sandbox'),'sandbox':{'sandbox_name':'test'}})
    if state['phase']=='committed':
        reconcile(CatalogStore(ctx['run_dir']))
        return
    workspace=Path(state['workspace'])
    workspace.mkdir(parents=True,exist_ok=True)
    inputs=core_store.handle({**base,'op':'inputs','payload':node,'target':str(workspace/'.inputs')})
    core_store.handle({**base,'op':'started'})
    spec={**state,'workspace':str(workspace),'inputs':inputs,'max_bytes':8000000,'max_files':16}
    env={'MN_ARTIFACT_OUTPUT_DIR':str(workspace/'outputs'),'MN_ARTIFACT_INPUT_INDEX':str(workspace/'.inputs/index.json'),
         'MN_ARTIFACT_PRODUCER':json.dumps(identity),'MN_ARTIFACT_COMMIT_ID':state['commit_id'],
         'MN_RUN_DIR':str(workspace/'local/runs'/identity['run_id']),
         'MN_SDK_COMPONENTS_JSON':'["blueprint-blocks"]'}
    source=Path(__file__).resolve().parents[2]/'software_architecture_advisor'
    parameters=json.loads((source/'execution.json').read_text())['agents']['registry']['architecture_packet_reviewer']['with']
    with patch.dict(os.environ,env):
        result=run(StepContext(step_id=node['id'],run_id=identity['run_id'],job_id=identity['job_id'],
            agent_id='architecture_packet_reviewer',idempotency_key=identity['run_id']+'/'+node['id'],
            environment=dict(os.environ),config=ctx['config'],message={'_mn_step':{'step_input':node}}),
            resources={'llm':model},**parameters)
    execution={'exit_code':0,'structured_result':asdict(result),'stdout':'','stderr':''}
    core_worker.seal(workspace,spec,execution)
    assert 'seal_error' not in execution, execution
    # Transfer only sealed manifest and declared outputs, matching the runner.
    import shutil
    stage=workspace/'transfer'
    stage.mkdir(exist_ok=True)
    shutil.copyfile(workspace/'sealed/manifest.json',stage/'manifest.json')
    shutil.copytree(workspace/'outputs',stage/'outputs')
    core_store.handle({**base,'op':'commit','stage':str(stage),'execution':execution,'max_files':16,'max_bytes':8000000})
    reconcile(CatalogStore(ctx['run_dir']))
