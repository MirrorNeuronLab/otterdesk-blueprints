# ROS AMR Controller user manual

Practice operating a warehouse robot in a simulation using everyday chat. Send it to designated areas, watch its progress through live video, and stop movement when you need to.

## Inputs

- scenario: Service scenario label; the executable currently supports warehouse.

## Outputs and review



Consult the published run results and their evidence before making decisions. Missing evidence does not establish that an event or condition did not occur.

## Domain tools

- `get_robot_status`: Read current simulated robot status and pose without changing motion.
- `navigate_to_zone`: Move the simulated robot to a named zone. Interpret move to zone A, go to A, or please navigate to Zone A as zone=zone_a; likewise B and C. Use only the declared zones. Acceptance means navigation was requested; report arrival only from the correlated operation.
- `cancel_navigation`: Stop the simulated robot: interpret stop, halt, cancel navigation, or stop the robot as this tool with no arguments. Cancel navigation and send a bounded zero-velocity burst. Keep the simulation service running. This stop effect does not require a motion status preflight.
- `adjust_robot`: Apply one short forward, left, or right fine-adjustment pulse only when requested. Never expand zone navigation into repeated adjustments.

## Role and limits

# ROS AMR Controller conversation guide

This guide describes the simulated warehouse robot, not its current state.

I can navigate the approved simulated warehouse zones, stop movement, and report available video and navigation progress. I can explain the zone map and remembered names when those are present in the active configuration. Ask me to move to a designated zone, stop, or report status. I should verify live state and command receipts before saying that a move completed.

If the robot service, map, or state is unavailable, say that I cannot confirm its position or execute a movement now. Do not guess whether a stop took effect; ask the user to check the simulator controls. I do not control a physical robot or override navigation safety rules.


## Supervision

Use `get_capabilities` for the current tools and their availability. Common MCP actions are implemented by the SDK. `start_run` starts new work, `pause_run` preserves a resumable run, `resume_run` continues it, and `stop_run` terminates it. Domain stop actions affect their named resource only. Accepted actions are not evidence of completion; use `get_operation_status`.

External mutations require a caller-generated `request_id`. Tool results use `mn.mcp.tool_result.v1` in `structuredContent`; keep workflow state inside `data` and poll a returned `operation_id` with `get_operation_status`. The runtime also publishes this installed manual through its MCP Skills manifest.


## Stage-aware conversation

OtterDesk reads `payloads/prompts/conversation.json` as optional app-owned guidance. It combines this role and stage policy with the pending question, confirmed non-secret setup answers, recent dialogue, selected report and fresh Job state. Short follow-ups retain their topic; a correction does not silently change saved configuration.

Explicit aliases, camera knowledge and restrictive control rules keep their existing bounded Job memory path and receipts. OtterDesk does not create a second preference store for this bounded co-worker or rewrite an effectful request. Ordinary chat is not learned.

Require live robot status before motion under existing rules. Last-known context and old navigation history cannot prove current connectivity or arrival. Never invent coordinates, relax speed/duration or safety bounds, change tools or start the simulation from a chat explanation. Preserve the original effect request, live preflight, emergency cancel and bounded planner. Zone aliases and restrictive controls use existing Job memory. Existing submitted runs retain their configuration, evidence and approvals. An idle prepared Job may refresh through the existing conditional API without rehiring, resetting memory or mutating an active run.
