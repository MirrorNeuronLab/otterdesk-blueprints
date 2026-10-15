# GTM executor user manual

Drafts campaigns and replies, then sends only the exact emails and recipients you approve.

## Inputs

- website_url: string
- goal_id: string
- peer_job_id: string
- instruction: string
- output_folder: local_path
- contacts_file: local_path
- inbox_id: string
- newsletter_eligible: boolean
- common_goal: string
- collaboration_group_id: string
- collaboration_peers: array

## Outputs and review



Consult the published run results and their evidence before making decisions. Missing evidence does not establish that an event or condition did not occur.


## Supervision

Use `get_capabilities` for the current tools and their availability. Common MCP actions are implemented by the SDK. `start_run` starts new work, `pause_run` preserves a resumable run, `resume_run` continues it, and `stop_run` terminates it. Domain stop actions affect their named resource only. Accepted actions are not evidence of completion; use `get_operation_status`.

External mutations require a caller-generated `request_id`. Tool results use `mn.mcp.tool_result.v1` in `structuredContent`; keep workflow state inside `data` and poll a returned `operation_id` with `get_operation_status`. The runtime also publishes this installed manual through its MCP Skills manifest.
