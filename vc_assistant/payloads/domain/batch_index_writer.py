"""Native terminal VC review, report projection and SDK publication."""

import json

from mn_sdk.agent_events import activity_operation
from mn_sdk.blueprint_support import bounded_int, elapsed_ms_from_started_at, observation_trace_summary, utc_now_iso
from mn_sdk.integrations.block_publication_files import freeze_file_publication, merge_publications, deliver_files
from mn_sdk_common.publication import ArtifactWrite
from mn_public_research_orchestrator_skill import flatten_research_ledger

from .analysis import build_company_evidence_summaries
from .artifact_sources import index_output_artifacts
from .common import BLUEPRINT_ID, BLUEPRINT_NAME, METHOD_IDS, OUTPUT_TYPE, RECOMMENDED_ACTION, RESEARCH_AGENT_IDS, WORKFLOW_STEP_IDS
from .execution_policy import company_worker_count, scoring_worker_count
from .intake import build_cache_policy_summary, processed_and_skipped_company_names
from .intake_state import checkpoint_path, read_snapshot
from .intake_review import review_snapshot, complete_findings
from .knowledge import active_knowledge_reference, public_knowledge_rag_state
from .reporting import build_artifact_quality_report, build_method_coverage, build_research_coverage, build_run_health_report
from .research_core import actor_review_config
from .research_services import research_resources
from .runtime_tools import merged_observation_trace


def ledger_usage(ledger):
    calls = [action for action in ledger['actions'] if action['action_type'] == 'llm_call' and action['cost']]
    providers = sorted({action['metadata'].get('provider', 'unknown') for action in calls})
    models = sorted({action['metadata'].get('model', 'unknown') for action in calls})
    return {'provider': providers[0] if len(providers) == 1 else ('mixed' if providers else 'none'),
            'model': models[0] if len(models) == 1 else ('mixed' if models else 'none'),
            'calls': len(calls), 'unknown_calls': sum(action['status'] == 'started' for action in calls),
            'accounting': 'core_action_ledger'}


def compose_batch(block, state, resources, observation_summary):
    company_records, company_work_queue = state['records'], state['queue']
    analyses = sorted(state['cached']['analyses'].values(), key=lambda value: value['company_slug'])
    research_ledgers = state['cached']['research_ledgers']
    output_files = state['output_files']
    active_knowledge, knowledge_rag = resources.knowledge, resources.rag
    action_ledger = state['action_ledger']
    actor_findings, actor_review_warnings = state['actor_findings'], state['actor_review_warnings']
    processed_company_names, skipped_company_names = (
        processed_and_skipped_company_names(company_work_queue)
    )
    generated_at = utc_now_iso()
    research_coverage = build_research_coverage(research_ledgers, generated_at=generated_at)
    method_coverage = build_method_coverage(analyses, generated_at=generated_at)
    cache_policy_summary = build_cache_policy_summary(
        company_work_queue,
        processed_company_names=processed_company_names,
        skipped_company_names=skipped_company_names,
    )
    artifact_quality = build_artifact_quality_report(
        analyses=analyses,
        company_records=company_records,
        research_ledgers=research_ledgers,
        output_files=output_files,
        knowledge_rag=knowledge_rag,
        actor_findings=actor_findings,
        actor_review_settings=actor_review_config(block.config),
    )
    run_health = build_run_health_report(
        run_id=block.run_id,
        started_at=state["started_at"],
        elapsed_ms=elapsed_ms_from_started_at(state["started_at"]),
        artifact_quality=artifact_quality,
        observation_summary=observation_summary,
        action_ledger=action_ledger,
        knowledge_rag=knowledge_rag,
        research_ledgers=research_ledgers,
        cache_policy_summary=cache_policy_summary,
        actor_review_warnings=actor_review_warnings,
        actor_review_settings=actor_review_config(block.config),
        llm_limiter=resources.limiter,
    )
    budget_warnings = []
    if action_ledger["exhausted"]:
        budget_warnings.append(
            {
                "kind": "budget",
                "status": "budget_exhausted",
                "message": "The VC Assistant action budget was exhausted; later research, financial-tool, or actor-review calls may be partial.",
            }
        )
    knowledge_rag_warnings = list(knowledge_rag.get("warnings") or [])
    company_evidence_summaries = build_company_evidence_summaries(
        analyses, company_records, research_ledgers
    )
    final_artifact = {
        "type": OUTPUT_TYPE,
        "executive_summary": f"{BLUEPRINT_NAME} prepared score-only VC heuristic reports for {len(analyses)} startup companies; {len(skipped_company_names)} unchanged companies used cached reports.",
        "recommended_action": RECOMMENDED_ACTION,
        "confidence": 0.74
        if any(item["composite_score"] is not None for item in analyses)
        else 0.35,
        "evidence": [
            record for records in company_records.values() for record in records[:5]
        ],
        "next_steps": [
            "Review each company subfolder before deciding what to diligence next.",
            "Check insufficient_evidence method sections and add source documents where needed.",
            "Use public source refs only as context; verify material claims independently.",
        ],
        "source_refs": [
            "inputs.json",
            "events.jsonl",
            "llm_rag_trace.jsonl",
            "result.json",
            "final_artifact.json",
            "action_ledger.json",
            "artifact_quality.json",
            "run_health.json",
            "company_index.json",
            *(item["path"] for item in active_knowledge.get("documents") or []),
        ],
        "active_knowledge": active_knowledge_reference(active_knowledge),
        "knowledge_rag": public_knowledge_rag_state(knowledge_rag),
        "research_summary": {
            "company_count": len(research_ledgers),
            "processed_company_count": len(processed_company_names),
            "skipped_company_count": len(skipped_company_names),
            "privacy_policy": "no confidential excerpts in public research queries",
            "agent_ids": RESEARCH_AGENT_IDS,
            "coverage": research_coverage,
            "knowledge_rag": public_knowledge_rag_state(knowledge_rag),
        },
        "research_sources": [
            source
            for ledger in research_ledgers.values()
            for source in flatten_research_ledger(ledger)
        ],
        "company_evidence_summaries": company_evidence_summaries,
        "research_warnings": [*budget_warnings, *knowledge_rag_warnings],
        "actor_review_warnings": actor_review_warnings,
        "report_only": True,
        "company_reports": analyses,
        "method_ids": METHOD_IDS,
        "workflow_step_ids": WORKFLOW_STEP_IDS,
        "company_work_queue": company_work_queue,
        "cache_policy": cache_policy_summary,
        "method_coverage": method_coverage,
        "artifact_quality": artifact_quality,
        "run_health": {
            "status": run_health["status"],
            "warning_count": len(run_health["warnings"]),
            "failure_count": len(run_health["failures"]),
            "elapsed_ms": run_health["elapsed_ms"],
            "artifact": "run_health.json",
        },
        "parallel_execution": {
            "max_company_workers": company_worker_count(
                block.config, len(company_records)
            ),
            "max_parallel_research_agents": bounded_int(
                (block.config.get("internet_research") or {}).get(
                    "max_parallel_research_agents"
                ),
                default=len(RESEARCH_AGENT_IDS),
                maximum=len(RESEARCH_AGENT_IDS),
            ),
            "max_scoring_workers": scoring_worker_count(block.config),
            "llm_backpressure": resources.limiter.config_summary(),
            "company_processing_order": [
                analysis["company_slug"] for analysis in analyses
            ],
        },
        "actor_review": {
            "llm_actor_ids": actor_review_config(block.config)["llm_actor_ids"],
            "max_context_chars": actor_review_config(block.config)[
                "max_context_chars"
            ],
            "context_json_chars": None,
            "prompt_context_json_chars": None,
            "context_compression": {"distributed_by_workflow_step": True},
        },
        "observability": observation_summary,
        "memory_boundary": {
            "rag_knowledge": {
                "storage": "duckdb",
                "purpose": "durable playbook and method knowledge used to do the VC job",
                "namespace": (knowledge_rag.get("config") or {}).get("namespace")
                if isinstance(knowledge_rag.get("config"), dict)
                else "",
            },
            "artifact_sources": {
                "storage": "shared Markdown files",
                "synchronization": "syncthing",
                "index": "Membrane SourceCorpus",
                "catalogs": "context_sources/inputs.json and context_sources/outputs.json",
            },
            "runtime_memory": {
                "storage": "markdown",
                "index": "duckdb_per_job",
                "device": "cpu",
                "enabled": bool(block.config.get("text_memory", {}).get("enabled")),
                "purpose": "privacy-approved execution observations, claims and method outcomes",
            },
        },
        "monitor_state": {
            "mode": "folder_monitoring",
            "cycles_completed": 1,
            "max_cycles": int((state["inputs"].get("monitoring") or {}).get("max_cycles") or 1),
            "processed_company_count": len(processed_company_names),
            "skipped_company_count": len(skipped_company_names),
            "watch_state": state["watch_state"],
        },
        "output_files": output_files,
        "actor_findings": actor_findings,
        "llm_usage": ledger_usage(action_ledger),
        "action_ledger": action_ledger,
    }
    final_artifact['output_files'] = [*output_files,
        *[{'kind': kind, 'path': name} for kind, name in (
            ('final_artifact_json', 'final_artifact.json'), ('action_ledger_json', 'action_ledger.json'),
            ('artifact_quality_json', 'artifact_quality.json'), ('run_health_json', 'run_health.json'),
            ('llm_rag_trace_jsonl', 'llm_rag_trace.jsonl'))]]
    return final_artifact, run_health


def prepare_batch(block, state):
    review_snapshot(block, state, 'batch_index_writer')
    complete_findings(block, state)
    resources = research_resources(block, state, 'batch_index_writer', need_model=False, budget_scope='publication')
    state['action_ledger'] = resources.budget.summary(include_actions=True)
    trace_path = block.root + '/batch-trace.jsonl'
    trace = block.store.commit_bytes(trace_path, merged_observation_trace(state, block.store.run_dir), kind='observation_trace')
    observations = observation_trace_summary(block.store.run_dir, file_name=trace_path)
    observations['trace_artifact'] = 'llm_rag_trace.jsonl'
    observations['coverage'] = 'local trace plus qualified upstream specialist records; private initialization diagnostics may be local only'
    artifact, health = compose_batch(block, state, resources, observations)
    return {'state': state, 'artifact': artifact, 'health': health, 'trace': trace.to_dict()}


@activity_operation('Writing the batch index', completed='Writing the batch index: completed')
def batch_index_writer(block, inputs):
    state = read_snapshot(block, inputs, 'company_report_writer')
    path = block.root + '/prepared-batch.json'
    prepared = block.freeze_checkpoint(path, lambda: prepare_batch(block, state))
    projection = block.read_checkpoint(prepared, expected_path=path)
    state, artifact = projection['state'], projection['artifact']
    result = {'run_id': block.run_id, 'blueprint_id': BLUEPRINT_ID, 'status': 'completed', 'final_artifact': artifact}
    values = {'final_artifact.json': artifact, 'action_ledger.json': state['action_ledger'],
              'artifact_quality.json': artifact['artifact_quality'], 'run_health.json': projection['health']}
    state['run_result'] = block.store.commit('result.json', result, kind='run_result').to_dict()
    writes = [ArtifactWrite(name, name, (json.dumps(value, sort_keys=True, ensure_ascii=False) + '\n').encode(),
        kind='json', authoritative=True) for name, value in values.items()]
    writes.append(ArtifactWrite('trace', 'llm_rag_trace.jsonl', block.store.read_bytes(projection['trace'])))
    publication = merge_publications(block, state['published_files'], freeze_file_publication(block, lambda: writes, name='batch'))
    deliver_files(block, publication)
    def prepare_sources():
        inventory = index_output_artifacts(block, artifact['output_files'])
        files = [ArtifactWrite(item['path'], item['path'], block.store.path(item['path']).read_bytes())
            for item in inventory if item['kind'] in {'output_source_markdown', 'output_source_catalog'}]
        # Input inventory already contains converted company sources; de-duplicate
        # logical names before selecting the latest source catalog revision.
        files = list({write.path: write for write in files}.values())
        return files
    publication = merge_publications(block, publication,
        freeze_file_publication(block, prepare_sources, name='batch-sources'))
    state.update(stage='batch_index_writer', published_files=publication, batch_projection=prepared.to_dict())
    final = block.freeze_checkpoint(checkpoint_path('batch_index_writer'), lambda: state)
    return {'status': 'completed', 'state': final.to_dict(), 'published_files': publication,
        'run_id': block.run_id, 'blueprint_id': BLUEPRINT_ID, 'company_count': len(artifact['company_reports']),
        'processed_company_count': artifact['research_summary']['processed_company_count'],
        'skipped_company_count': artifact['research_summary']['skipped_company_count'],
        'final_artifact': publication['files']['final_artifact.json'],
        'artifact_quality': publication['files']['artifact_quality.json'], 'run_health': publication['files']['run_health.json']}
