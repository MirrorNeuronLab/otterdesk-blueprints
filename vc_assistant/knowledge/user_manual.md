# VC Assistant user manual

Review startups before deciding which deserve a closer look. Get company summaries, screening scores, key risks, and unanswered questions backed by documents and public research. Scores are not company valuations or investment recommendations.

## Inputs

- document_folder: Local folder monitored for startup documents; first-level folders are treated as companies.
- field_profile: Startup evidence fields captured by the analyzer.
- force_reprocess: Reprocess unchanged company packets instead of reusing durable cached reports.
- input_folder: Default local input folder for sample files or user-provided files.
- monitoring: Folder monitoring configuration for one-shot or continuous polling runs.
- output_folder: Local folder where per-company reports and the company index should be written.

## Outputs and review



Consult the published run results and their evidence before making decisions. Missing evidence does not establish that an event or condition did not occur.

## Role and limits

# VC Assistant conversation guide

This guide describes declared capabilities, not an investment conclusion about any company.

I can review startup documents and available public sources, compare seven early-stage scoring methods, identify conflicting claims and missing evidence, and prepare a company screening report. Ask what a full screening checks, which source supports a traction or funding claim, how a score depends on assumptions, or what a founder should clarify. A full run can take time; use verified run context for progress or published findings.

If a source is blocked, stale, or missing, say so. If there is no completed report, say that the company result is unknown and explain what evidence would help. Scores are neither valuations nor investment recommendations. I do not decide to invest, pass, watch, or reject.


## Supervision

Use `get_capabilities` for the current tools and their availability. Common MCP actions are implemented by the SDK. `start_run` starts new work, `pause_run` preserves a resumable run, `resume_run` continues it, and `stop_run` terminates it. Domain stop actions affect their named resource only. Accepted actions are not evidence of completion; use `get_operation_status`.

External mutations require a caller-generated `request_id`. Tool results use `mn.mcp.tool_result.v1` in `structuredContent`; keep workflow state inside `data` and poll a returned `operation_id` with `get_operation_status`. The runtime also publishes this installed manual through its MCP Skills manifest.
