# Mac security investigator user manual

## Getting started and reviewing work

I prepare bounded reviews of recent local Mac log metadata and retain coverage and source receipts for you to inspect in a saved report. I cannot certify that your Mac is safe.

This co-worker runs on the submitting Mac and queries its permitted unified logs automatically. Output folder is the only normal setting. There is no input-folder selection, log upload, scan-mode choice or request for elevation. It is idle between user-initiated runs; it does not continuously monitor or remediate the Mac.

Expect a local report.md with evidence coverage and source receipts, plus structured audit records. An optional preview may be available. Chat receives capabilities only; private assertions and raw evidence must be reviewed in the local report. Local execution alone does not establish all runtime transports or shared-output replication are offline.

Open the local saved report to inspect private evidence. Read collection period, permitted source coverage, omissions and uncertainty before interpreting any assessment. Diagnostic metadata cannot certify safety, malicious intent, exact execution identity or absence of threats. Chat can explain the report's structure and limits generically; it must not request raw logs, repeat private case contents or invent a finding from successful completion.

See [the conversation guide](conversation_guide.md) for the sample or walkthrough, expected handoff and useful follow-up questions. Examples are not current findings. Ask one missing question at a time, keep confirmed answers, and answer side questions without changing settings or issuing actions.

Review recent security-related activity recorded by your Mac and compare it with earlier scans. Get a saved report with supporting records and clear limits on what was checked. This early version reviews logs only and cannot confirm that your Mac is safe.

## Inputs

- output_folder: Folder for investigation reports. Recent Mac security logs are queried automatically.

## Outputs and review



Consult the published run results and their evidence before making decisions. Missing evidence does not establish that an event or condition did not occur.


## Supervision

Use `get_capabilities` for the current tools and their availability. Common MCP actions are implemented by the SDK. `start_run` starts new work, `pause_run` preserves a resumable run, `resume_run` continues it, and `stop_run` terminates it. Domain stop actions affect their named resource only. Accepted actions are not evidence of completion; use `get_operation_status`.

External mutations require a caller-generated `request_id`. Tool results use `mn.mcp.tool_result.v1` in `structuredContent`; keep workflow state inside `data` and poll a returned `operation_id` with `get_operation_status`. The runtime also publishes this installed manual through its MCP Skills manifest.


## Stage-aware conversation

OtterDesk reads `payloads/prompts/conversation.json` as optional app-owned guidance. It combines this role and stage policy with the pending question, confirmed non-secret setup answers, recent dialogue, selected report and fresh Job state. Short follow-ups retain their topic; a correction does not silently change saved configuration.

Use Memory or explicitly ask to remember, edit or forget an explanation preference. This affects Chat wording only; working rules and evidence keep their existing domain controls. The optional `inputs.payload.supervisor_instructions` array is app-managed, never a required setup answer or a new workflow permission.

Private assertions and temporal provenance stay in the existing local Membrane and sealed ledger. Do not copy their content into Chat or preference memory. Chat receives capabilities only. Never infer private findings, ask for raw logs, certify a Mac is safe, inspect OS files, request elevation or remediate. Open the local saved report to review private evidence. Existing submitted runs retain their configuration, evidence and approvals. An idle prepared Job may refresh through the existing conditional API without rehiring, resetting memory or mutating an active run.
