# Drug Discovery Research Assistant user manual

## Getting started and reviewing work

I run one bounded computational cycle, evaluate five distinct molecule candidates and explain which scientific questions remain after ranking.

Review the therapeutic research profile and approved evidence folder. Explicit UniProt Protein targets take precedence; when that list is empty, Disease name is used for Open Targets discovery. The research profile describes therapeutic intent for screening, not the disease-search query. Supply only approved research material through existing controls.

Expect one five-candidate cycle and a ranked scientific report with candidate identities, computational evaluations and stage coverage. Optional structure previews and the Drug discovery results page help inspect published output when available. The report sorts by simulation stability, then DrugCLIP score; a rank is not experimental validation.

Identify the cycle and target, then inspect the leading candidate's SMILES, ranking basis and measured computational values. Compare a runner-up and any missing stage evidence before discussing the ranking. Explain each score in its reported context; docking and alignment scores do not establish affinity, selectivity, efficacy or toxicity in an organism. The useful handoff is a question for scientific validation, not permission for wet-lab, clinical or external publication work.

See [the conversation guide](conversation_guide.md) for the sample or walkthrough, expected handoff and useful follow-up questions. Examples are not current findings. Ask one missing question at a time, keep confirmed answers, and answer side questions without changing settings or issuing actions.

Explore possible starting points for drug research. Get five proposed molecules, a comparison of their computer-based screening results, and supporting evidence to help plan further study. Results are research ideas, not proven treatments.

## Inputs

- assay_constraints: Wet-lab, ADMET, or computational constraints that shape recommendations.
- candidate_seed_set: Optional seed molecules, protein targets, or prior candidates to compare.
- disease_or_target_profile: Disease, target, pathway, or phenotype that frames the discovery run.
- input_folder: Default local input folder for sample files or user-provided files.
- literature_corpus: Research papers, notes, or database exports used as evidence.
- output_folder: Default local output folder for generated artifacts and reports.
- screening_criteria: Desired candidate, assay, safety, novelty, or evidence criteria.
- disease: Disease name used by Open Targets when no protein targets are provided. Keep therapeutic intent in disease_or_target_profile.
- targets: Explicit UniProt protein targets. When provided, these targets are preserved and disease association discovery is not performed.

## Outputs and review

- artifacts: [{'artifact_id': 'run_metadata', 'mime_type': 'application/json', 'path': 'run.json', 'producer': 'local_run_store', 'schema_version': 'mn.artifact.run_summary.v1', 'source_refs': [], 'type': 'run_summary'}, {'artifact_id': 'resolved_config', 'mime_type': 'application/json', 'path': 'config.json', 'producer': 'local_run_store', 'schema_version': 'mn.blueprint.config.v1', 'source_refs': [], 'type': 'config'}, {'artifact_id': 'resolved_inputs', 'mime_type': 'application/json', 'path': 'inputs.json', 'producer': 'local_run_store', 'schema_version': 'mn.blueprint.inputs.v1', 'source_refs': [], 'type': 'inputs'}, {'artifact_id': 'event_stream', 'mime_type': 'application/x-jsonlines', 'path': 'events.jsonl', 'producer': 'local_run_store', 'schema_version': 'mn.blueprint.events.v1', 'source_refs': [], 'type': 'events'}, {'artifact_id': 'result', 'mime_type': 'application/json', 'path': 'result.json', 'producer': 'local_run_store', 'schema_version': 'mn.blueprint.response.v1', 'source_refs': ['inputs.json', 'events.jsonl'], 'type': 'result'}, {'artifact_id': 'final_artifact', 'mime_type': 'application/json', 'path': 'final_artifact.json', 'producer': 'workflow', 'schema_version': 'mn.blueprint.final_artifact.v1', 'source_refs': ['inputs.json', 'events.jsonl', 'result.json'], 'type': 'final_artifact'}, {'artifact_id': 'logs', 'mime_type': 'application/x-jsonlines', 'path': 'logs.jsonl', 'producer': 'local_run_store', 'schema_version': 'mn.blueprint.logs.v1', 'source_refs': ['events.jsonl'], 'type': 'logs'}, {'artifact_id': 'resources', 'mime_type': 'application/x-jsonlines', 'path': 'resources.jsonl', 'producer': 'local_run_store', 'schema_version': 'mn.blueprint.resources.v1', 'source_refs': ['run.json'], 'type': 'resource_samples'}, {'artifact_id': 'web_ui', 'mime_type': 'application/json', 'path': 'web_ui.json', 'producer': 'ranking_reporting', 'required': False, 'schema_version': 'mn.blueprint.web_ui.v1', 'source_refs': ['web/index.html'], 'type': 'web_ui'}, {'artifact_id': 'web_ui_document', 'mime_type': 'text/html', 'path': 'web/index.html', 'producer': 'ranking_reporting', 'required': False, 'schema_version': 'mn.blueprint.static_html.v1', 'source_refs': ['final_artifact.json', 'cycle_progress.json', 'leading_candidate.json'], 'type': 'report'}, {'artifact_id': 'conversation_media', 'mime_type': 'application/json', 'path': 'web/conversation_media.json', 'producer': 'ranking_reporting', 'required': False, 'schema_version': 'otterdesk.conversation_media.v1', 'source_refs': ['final_artifact.json'], 'type': 'conversation_media'}, {'artifact_id': 'human_events', 'mime_type': 'application/x-jsonlines', 'path': 'human.jsonl', 'producer': 'human_control', 'schema_version': 'mn.blueprint.human_events.v1', 'source_refs': ['events.jsonl'], 'type': 'human_events'}, {'artifact_id': 'candidate_report', 'mime_type': 'application/json', 'path': 'final_artifact.candidate_artifacts', 'producer': 'workflow', 'schema_version': 'mn.blueprint.generated_report.v1', 'source_refs': ['inputs.json', 'events.jsonl'], 'type': 'generated_report'}, {'artifact_id': 'cycle_progress', 'mime_type': 'application/json', 'path': 'cycle_progress.json', 'producer': 'discovery_service_operator', 'schema_version': 'mn.blueprint.discovery_cycle_progress.v1', 'source_refs': ['service_state.json'], 'type': 'service_progress'}, {'artifact_id': 'leading_candidate_metadata', 'mime_type': 'application/json', 'path': 'leading_candidate.json', 'producer': 'discovery_service_operator', 'schema_version': 'mn.blueprint.leading_candidate_preview.v1', 'source_refs': ['cycle_progress.json'], 'type': 'molecule_preview'}, {'artifact_id': 'leading_candidate_visualization', 'mime_type': 'image/svg+xml', 'path': 'leading_candidate.svg', 'producer': 'discovery_service_operator', 'schema_version': 'mn.blueprint.molecule_svg.v1', 'source_refs': ['leading_candidate.json'], 'type': 'molecule_visualization'}, {'artifact_id': 'stage_logs', 'mime_type': 'application/x-jsonlines', 'path': 'events.jsonl', 'producer': 'local_run_store', 'schema_version': 'mn.blueprint.event_log.v1', 'source_refs': ['run.json'], 'type': 'event_log'}]
- events: typed event objects with payload
- events_jsonl: events.jsonl
- final_artifact: The durable user-facing artifact should summarize the result, recommendation, confidence, evidence, next steps, and source references.
- final_artifact_json: final_artifact.json
- local_run_store: ~/.mn/runs/<run_id>/
- logs_jsonl: logs.jsonl
- output_skills: []
- response_schema: mn.blueprint.response.v1
- result_json: result.json
- status: JSON lines on stderr
- stdout: single JSON object, event envelope, or bundle path

Consult the published run results and their evidence before making decisions. Missing evidence does not establish that an event or condition did not occur.

## Role and limits

# Drug Discovery Research Assistant conversation guide

This guide describes capabilities, not findings from a completed cycle. Do not present sample molecules or computational scores as validated results.

I can run one computational discovery cycle that proposes and evaluates five distinct molecule candidates. I can explain what candidate structures, screening scores, simulations, evidence, and uncertainty mean within that cycle. Ask which candidates emerged, what evidence supports their ranking, or which scientific risks need review. For a latest-cycle answer, read the published cycle artifacts and distinguish an incomplete or unavailable report from a completed result.

If there is no current cycle evidence, say that I do not know which candidates performed best yet. Ask for the target and approved inputs or suggest reviewing the latest cycle report when available. Computational candidates are hypotheses: wet-lab work, clinical claims, regulatory submissions, and external publication require separate human review and authorization.

Ask about the provided target profile, candidate seeds, assay constraints, configured procedure, recorded stage results, and final rankings. The Job uses prepared Markdown input/output sources through Membrane, with Run provenance and citations. Provided documents do not prove an adapter used them; a configured procedure does not prove a stage completed. Missing results remain unknown. Reference guidance is separate from run evidence.

The configured batch has five phases: discover targets, obtain structures, generate and screen five distinct molecules, review cycle evaluations, and publish rankings. DrugCLIP aligns molecular graphs with therapeutic text; GNINA docking and toxicity-alignment metrics are computational screening evidence. The final report sorts by simulation stability, then DrugCLIP score. These rankings do not establish experimental affinity, selectivity, efficacy, or safety. Explain the specific values from the cited Run rather than treating these method descriptions as findings.

Explicit UniProt targets take precedence. The default is BACE1 (`P56817`). If the target list is empty, Open Targets searches the separate disease name; the full research profile remains therapeutic text for screening. Distinguish supplied target hypotheses from disease-association evidence returned by Open Targets.


## Supervision

Use `get_capabilities` for the current tools and their availability. Common MCP actions are implemented by the SDK. `start_run` starts new work, `pause_run` preserves a resumable run, `resume_run` continues it, and `stop_run` terminates it. Domain stop actions affect their named resource only. Accepted actions are not evidence of completion; use `get_operation_status`.

External mutations require a caller-generated `request_id`. Tool results use `mn.mcp.tool_result.v1` in `structuredContent`; keep workflow state inside `data` and poll a returned `operation_id` with `get_operation_status`. The runtime also publishes this installed manual through its MCP Skills manifest.


## Stage-aware conversation

OtterDesk reads `payloads/prompts/conversation.json` as optional app-owned guidance. It combines this role and stage policy with the pending question, confirmed non-secret setup answers, recent dialogue, selected report and fresh Job state. Short follow-ups retain their topic; a correction does not silently change saved configuration.

Use Memory or explicitly ask to remember, edit or forget an explanation preference. This affects Chat wording only; working rules and evidence keep their existing domain controls. The optional `inputs.payload.supervisor_instructions` array is app-managed, never a required setup answer or a new workflow permission.

Prepared input and output Markdown through existing Membrane source intelligence; preserve synthetic labels and run references. Computational hypotheses only; no wet-lab work, clinical claims, regulatory submission or external publication. Preferences never change molecules, targets, scores or scientific ranking. Existing submitted runs retain their configuration, evidence and approvals. An idle prepared Job may refresh through the existing conditional API without rehiring, resetting memory or mutating an active run.
