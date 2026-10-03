"""VC input privacy and actor navigation policy over Markdown memory."""

import os

from mn_sdk.context_session.contracts import digest
from mn_sdk.text_memory import runtime_text_memory, retrieve_memory_context
from mn_sdk.blueprint_support.workflow_state import write_workflow_state
from .runtime_observations import ingest_runtime_observations


def actor_query_stages(agent_id, snapshot_id, limit, sources):
    filters = [{'field': 'memory_family', 'op': 'eq', 'value': 'vc_runtime'},
               {'field': 'snapshot_id', 'op': 'eq', 'value': snapshot_id}]
    stages = []
    if any(r['runtime_kind'] == 'tool' for r in sources):
        stages.append({'mode': 'analytical', 'consume': 'none', 'analytical': {
            'operation': 'recent', 'timestamp_field': 'timestamp', 'limit': 1,
            'filters': [*filters, {'field': 'kind', 'op': 'eq', 'value': 'tool'},
                        {'field': 'agent_id', 'op': 'eq', 'value': agent_id}]}})
    remaining = limit - len(stages)
    if remaining:
        kinds = ['method', 'claim', 'source'] if 'scor' in agent_id or 'report' in agent_id else ['claim', 'source']
        focus = {'company_identity_researcher': ['team', 'product'], 'funding_researcher': ['finance'],
                 'traction_verifier': ['traction'], 'market_comp_researcher': ['market', 'risk']}.get(agent_id)
        selected_filters = [*filters, {'field': 'kind', 'op': 'in', 'value': kinds}]
        if focus:
            selected_filters.append({'field': 'claim_family', 'op': 'in', 'value': focus})
        stages.append({'mode': 'analytical', 'consume': 'none', 'analytical': {
            'operation': 'rows', 'limit': remaining, 'filters': selected_filters}})
    return stages


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
        sources, snapshot_id = ingest_runtime_observations(memory, ctx)
        settings = ctx['config']['text_memory']
        if sources:
            packet, receipt = retrieve_memory_context(memory, f'{agent_id} {step_id} source-qualified runtime evidence',
                stages=actor_query_stages(agent_id, snapshot_id, settings['max_results'], sources),
                max_results=settings['max_results'], max_context_bytes=settings['max_context_bytes'],
                hydrate_json_records=True)
        else:
            packet = {'status': 'no_evidence', 'evidence': [], 'incomplete': True,
                      'usage': 'No source-qualified runtime observations exist at this workflow stage.'}
            receipt = {'selection': {'omitted': [], 'packet_sha256': digest(packet)}}
        write_workflow_state(ctx['run_dir'], f'membrane-{digest([step_id, agent_id, context])}.json',
            {'inputs': sources, 'packet': packet, 'receipt': receipt})
        return {**context, 'runtime_memory': packet}
    finally:
        memory.close()
