# Architecture Advisor user manual

Understand how your software is organized, where changes may cause problems, and what to improve first. Get a report with supporting examples, an interactive overview, and suggested tasks for your development team.

## Inputs

Choose the **Source code folder** when first setting up the co-worker. The field
starts empty and is the only setup question. The default model and review goal
are already configured. Advanced inputs remain available:

- repository_url: Public HTTPS GitHub repository-root URL. Mutually exclusive with input_folder.
- input_folder: Local source folder, staged by the platform. Mutually exclusive with repository_url.
- goal: Architecture investigation objective.
- graph_export: Optional version-1 or version-2 evidence graph export citing captured code; supplies unsupported structural layers or explicit runtime evidence.
- output_folder: Destination for reports and audit files.
- review_file: Optional bounded JSON review export from the architecture dashboard. Does not authorize source edits.

## Outputs and review

Open the architecture report from the completed run in this conversation to
inspect the web content in its workspace. Reports are also saved as local files.

Open **Component and function evolution map** from the dashboard or report.
Start with the dependency matrix, then switch to the dependency graph, hotspot
treemap, change impact or temporal coupling. Select a file or function to inspect
its relationships and source witnesses. The Code evolution tab plays committed
graph states and plots codebase growth. Compare a baseline to inspect added,
removed and modified definitions and call candidates. Size, churn and graph
connectivity guide inspection; they do not establish defects.

Data is in `data/`, Markdown in `reports/`, and rendering in `web/`. HTTP previews load sibling data automatically. Direct local or desktop static
HTML views use the explicit JSON file picker. Rerun the same Job or use its existing schedule to
retain growth measurements and graphs across reviews. This reflects capture
cadence, not a continuous filesystem watcher.

The focused review uses six selected topics with independent challenges and
summaries. Other catalog topics remain explicitly not analyzed. Missing history,
parser gaps and indirect calls remain unknown. An exhaustive catalog review is
available through `catalog_review.profile=full_catalog` with larger budgets.
The model uses your runtime default. Reports do
not authorize source edits or execute suggested work.

Consult the published run results and their evidence before making decisions. Missing evidence does not establish that an event or condition did not occur.


## Supervision

Use `get_capabilities` for the current tools and their availability. Common MCP actions are implemented by the SDK. `start_run` starts new work, `pause_run` preserves a resumable run, `resume_run` continues it, and `stop_run` terminates it. Domain stop actions affect their named resource only. Accepted actions are not evidence of completion; use `get_operation_status`.

External mutations require a caller-generated `request_id`. Tool results use `mn.mcp.tool_result.v1` in `structuredContent`; keep workflow state inside `data` and poll a returned `operation_id` with `get_operation_status`. The runtime also publishes this installed manual through its MCP Skills manifest.


## Stage-aware conversation

OtterDesk reads `payloads/prompts/conversation.json` as optional app-owned guidance. It combines this role and stage policy with the pending question, confirmed non-secret setup answers, recent dialogue, selected report and fresh Job state. Short follow-ups retain their topic; a correction does not silently change saved configuration.

Use Memory or explicitly ask to remember, edit or forget an explanation preference. This affects Chat wording only; working rules and evidence keep their existing domain controls. The optional `inputs.payload.supervisor_instructions` array is app-managed, never a required setup answer or a new workflow permission.

Use prepared source and report context through existing Membrane retrieval. Distinguish captured code from later repository changes. Review only. Chat cannot change source, run repository code, approve a patch or widen source/model access. Change durable review scope through Configure or the existing review file. Existing submitted runs retain their configuration, evidence and approvals. An idle prepared Job may refresh through the existing conditional API without rehiring, resetting memory or mutating an active run.
