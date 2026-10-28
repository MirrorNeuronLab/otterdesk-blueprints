"""VC input privacy and actor navigation policy over Markdown memory."""


from mn_sdk.context_session.contracts import digest
from mn_sdk.text_memory import runtime_text_memory, retrieve_memory_context


def actor_query_stages(agent_id, snapshot_id, limit, sources):
    filters = [{'field': 'memory_family', 'op': 'eq', 'value': 'vc_runtime'},
               {'field': 'snapshot_id', 'op': 'eq', 'value': snapshot_id}]
    stages = []
    tools = [r for r in sources if r['runtime_kind'] == 'tool' and r.get('agent_id') == agent_id]
    known = [r for r in tools if r.get('event_time_status') == 'known']
    used = 0
    if known:
        used = min(3, len(known), max(1, limit // 2))
        stages.append({'mode': 'analytical', 'consume': 'none', 'analytical': {
            'operation': 'recent', 'timestamp_field': 'event_timestamp', 'limit': used,
            'filters': [*filters, {'field': 'runtime_kind', 'op': 'eq', 'value': 'tool'},
                        {'field': 'event_time_status', 'op': 'eq', 'value': 'known'},
                        {'field': 'agent_id', 'op': 'eq', 'value': agent_id}]}})
    if len(known) != len(tools) and used < limit:
        stages.append({'mode': 'analytical', 'consume': 'none', 'analytical': {
            'operation': 'rows', 'limit': 1,
            'filters': [*filters, {'field': 'runtime_kind', 'op': 'eq', 'value': 'tool'},
                        {'field': 'event_time_status', 'op': 'eq', 'value': 'unknown'},
                        {'field': 'agent_id', 'op': 'eq', 'value': agent_id}]}})
        used += 1
    remaining = limit - used
    from .common import SCORER_AGENT_BY_METHOD
    selected_method = next((method for method, role in SCORER_AGENT_BY_METHOD.items() if role == agent_id), None)
    methods = [r for r in sources if r['runtime_kind'] == 'method'
               and (selected_method is None or r.get('method_id') == selected_method)]
    if remaining and methods and (selected_method or agent_id in {
            'score_consistency_auditor', 'company_report_writer', 'batch_index_writer'}):
        count = min(remaining, len(methods))
        method_filters = [*filters, {'field': 'runtime_kind', 'op': 'eq', 'value': 'method'}]
        if selected_method:
            method_filters.append({'field': 'method_id', 'op': 'eq', 'value': selected_method})
        stages.append({'mode': 'analytical', 'consume': 'none', 'analytical': {
            'operation': 'rows', 'limit': count, 'filters': method_filters}})
        remaining -= count
    if remaining:
        kinds = ['claim']
        focus = {'company_identity_researcher': ['team', 'product'], 'funding_researcher': ['finance'],
                 'traction_verifier': ['traction'], 'market_comp_researcher': ['market', 'risk']}.get(agent_id)
        eligible = [r for r in sources if r['runtime_kind'] in kinds and
                    (not focus or r.get('claim_family') in focus)]
        if not eligible:
            kinds, focus = ['source'], None
        selected_filters = [*filters, {'field': 'runtime_kind', 'op': 'in', 'value': kinds}]
        if focus:
            selected_filters.append({'field': 'claim_family', 'op': 'in', 'value': focus})
        stages.append({'mode': 'analytical', 'consume': 'none', 'analytical': {
            'operation': 'rows', 'limit': remaining, 'filters': selected_filters}})
    return stages


def snapshot_memory_context(block, state, context, *, role):
    if not block.config.get('actor_review', {}).get('use_context_engine', True):
        return context
    memory = runtime_text_memory(block.config, principal='vc-actor-review',
        scope={'job_id': block.job_id, 'run_id': block.run_id})
    if memory is None:
        return context
    from .runtime_observations import observation_records, publish_observations
    try:
        analyses = dict(state.get('cached', {}).get('analyses', {}))
        branch = state.get('score_branch') or {}
        for company, method in branch.get('scores', {}).items():
            analysis = analyses.get(company) or {}
            analyses[company] = {**analysis, 'methods': {**analysis.get('methods', {}), branch['method']: method}}
        records = list(observation_records(state.get('evidence', {}),
            analyses, block.store.run_dir))
        sources, snapshot_id = publish_observations(memory, records)
        settings = block.config['text_memory']
        if sources:
            packet, receipt = retrieve_memory_context(memory,
                f'{role} {block.step_id} source-qualified runtime evidence',
                # Filters select rows; source scope also bounds canonical-file
                # verification to this snapshot instead of every prior review.
                sources=[source['source_id'] for source in sources],
                stages=actor_query_stages(role, snapshot_id, settings['max_results'], sources),
                max_results=settings['max_results'], max_context_bytes=settings['max_context_bytes'],
                hydrate_runtime_records=True)
        else:
            packet = {'status': 'no_evidence', 'evidence': [], 'incomplete': True,
                'usage': 'No source-qualified runtime observations exist at this workflow stage.'}
            receipt = {'selection': {'omitted': [], 'packet_sha256': digest(packet)}}
        reference = block.store.commit(f'vc/memory/{digest([block.step_id, role, context])}.json',
            {'inputs': sources, 'packet': packet, 'receipt': receipt}, kind='context_witness')
        state.setdefault('memory_witnesses', {})[role] = reference.to_dict()
        return {**context, 'runtime_memory': packet}
    finally:
        memory.close()
