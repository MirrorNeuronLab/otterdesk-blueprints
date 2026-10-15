# Architecture Advisor user manual

Understand how your software is organized, where changes may cause problems, and what to improve first. Get a report with supporting examples, an interactive overview, and suggested tasks for your development team.

## Inputs

- repository_url: Public HTTPS GitHub repository-root URL. Mutually exclusive with input_folder.
- input_folder: Local source folder, staged by the platform. Mutually exclusive with repository_url.
- goal: Architecture investigation objective.
- graph_export: Optional version-1 or version-2 evidence graph export citing captured code; supplies unsupported structural layers or explicit runtime evidence.
- output_folder: Destination for reports and audit files.
- review_file: Optional bounded JSON review export from the architecture dashboard. Does not authorize source edits.

## Outputs and review



Consult the published run results and their evidence before making decisions. Missing evidence does not establish that an event or condition did not occur.


## Supervision

Use `get_capabilities` for the current tools and their availability. Common MCP actions are implemented by the SDK. `start_run` starts new work, `pause_run` preserves a resumable run, `resume_run` continues it, and `stop_run` terminates it. Domain stop actions affect their named resource only. Accepted actions are not evidence of completion; use `get_operation_status`.

External mutations require a caller-generated `request_id`. Tool results use `mn.mcp.tool_result.v1` in `structuredContent`; keep workflow state inside `data` and poll a returned `operation_id` with `get_operation_status`. The runtime also publishes this installed manual through its MCP Skills manifest.
