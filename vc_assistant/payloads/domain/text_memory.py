"""VC input privacy and actor navigation policy over Markdown memory."""

import json
import os

from mn_sdk.context_session.contracts import digest
from mn_sdk.text_memory import runtime_text_memory, compile_memory_context
from mn_sdk.blueprint_support.workflow_state import write_workflow_state


def actor_memory_context(ctx, context, *, step_id, agent_id):
    if not ctx['config'].get('actor_review', {}).get('use_context_engine', True):
        return context
    memory = runtime_text_memory(ctx['config'], principal='vc-actor-review', scope={
        'job_id': ctx.get('job_id') or os.environ.get('MN_JOB_ID'),
        'run_id': os.environ.get('MN_WORKFLOW_RUN_ID') or ctx.get('run_id') or os.environ.get('MN_RUN_ID'),
    })
    if memory is None:
        return context
    try:
        # This observation contains the existing privacy-approved actor context,
        # never confidential document bodies. Store it complete, without preview.
        source = memory.observe(json.dumps(context, ensure_ascii=False),
            event_id=['actor-context', step_id, agent_id, digest(context)], kind='observation',
            allow=['vc-actor-review'], upstream=[{'workflow_step_id': step_id, 'agent_id': agent_id}])
        settings = ctx['config']['text_memory']
        packet, receipt = compile_memory_context(memory, f'{agent_id} {step_id} workflow evidence',
            max_results=settings['max_results'], max_context_bytes=settings['max_context_bytes'])
        write_workflow_state(ctx['run_dir'], f'membrane-{digest([step_id, agent_id, context])}.json',
            {'input': source, 'packet': packet, 'receipt': receipt})
        return {**context, 'runtime_memory': packet}
    finally:
        memory.close()
