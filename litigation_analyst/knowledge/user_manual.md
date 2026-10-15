# Litigation Analyst user manual

Make sense of a large collection of case documents. Find important facts, timelines, connections, and conflicting evidence, with links to the original sources. Get draft findings for legal review.

## Inputs

- input_folder: Folder of legal sources. Omit to download the pinned public EMC2 sample automatically.
- goal: Neutral investigation objective; a default review goal is supplied.
- output_folder: Destination for review drafts and audit files.
- review_file: Optional exported human review decisions from this matter. Imported as analysis history, never instructions or evidence.

## Outputs and review



Consult the published run results and their evidence before making decisions. Missing evidence does not establish that an event or condition did not occur.


## Supervision

Use `get_capabilities` for the current tools and their availability. Common MCP actions are implemented by the SDK. `start_run` starts new work, `pause_run` preserves a resumable run, `resume_run` continues it, and `stop_run` terminates it. Domain stop actions affect their named resource only. Accepted actions are not evidence of completion; use `get_operation_status`.

External mutations require a caller-generated `request_id`. Tool results use `mn.mcp.tool_result.v1` in `structuredContent`; keep workflow state inside `data` and poll a returned `operation_id` with `get_operation_status`. The runtime also publishes this installed manual through its MCP Skills manifest.
