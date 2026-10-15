# CT reader user manual

Explore chest or abdominal CT scans for research and learning. Upload a scan in Chat, view its images, and read an experimental report. Research and education only; not for real diagnosis, treatment, or clinical decisions.

## Inputs

- ct_file: De-identified single-channel 3D CT in .nii or .nii.gz format with Hounsfield units.
- region: chest or abdomen; must match the scan.
- prompt: Optional bounded research question.
- output_folder: An additional copy of the experimental report.

## Outputs and review



Consult the published run results and their evidence before making decisions. Missing evidence does not establish that an event or condition did not occur.


## Supervision

Use `get_capabilities` for the current tools and their availability. Common MCP actions are implemented by the SDK. `start_run` starts new work, `pause_run` preserves a resumable run, `resume_run` continues it, and `stop_run` terminates it. Domain stop actions affect their named resource only. Accepted actions are not evidence of completion; use `get_operation_status`.

External mutations require a caller-generated `request_id`. Tool results use `mn.mcp.tool_result.v1` in `structuredContent`; keep workflow state inside `data` and poll a returned `operation_id` with `get_operation_status`. The runtime also publishes this installed manual through its MCP Skills manifest.
