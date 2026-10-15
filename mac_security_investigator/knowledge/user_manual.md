# Mac security investigator user manual

Review recent security-related activity recorded by your Mac and compare it with earlier scans. Get a saved report with supporting records and clear limits on what was checked. This early version reviews logs only and cannot confirm that your Mac is safe.

## Inputs

- output_folder: Folder for investigation reports. Recent Mac security logs are queried automatically.

## Outputs and review



Consult the published run results and their evidence before making decisions. Missing evidence does not establish that an event or condition did not occur.


## Supervision

Use `get_capabilities` for the current tools and their availability. Common MCP actions are implemented by the SDK. `start_run` starts new work, `pause_run` preserves a resumable run, `resume_run` continues it, and `stop_run` terminates it. Domain stop actions affect their named resource only. Accepted actions are not evidence of completion; use `get_operation_status`.

External mutations require a caller-generated `request_id`. Tool results use `mn.mcp.tool_result.v1` in `structuredContent`; keep workflow state inside `data` and poll a returned `operation_id` with `get_operation_status`. The runtime also publishes this installed manual through its MCP Skills manifest.
