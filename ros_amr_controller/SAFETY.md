# Conversational control safety

This blueprint is simulation-only. It does not authorize physical robot
control.

The Job response agent can call only tools and enum arguments declared under
`response_service.agent`. It resolves the exact passing MCP service registered
to the active ROS service Run and verifies the published tool names and input
schemas before every control turn. The model cannot provide an endpoint, tool
name, coordinate, speed, or duration. Invalid model output, an unavailable
model, an offline Run, ambiguous motion, or a schema mismatch causes no motion.

One initial turn uses one strict JSON model completion and permits at most one
effect. Exact stop/cancel language may take the deterministic cancellation
path. A UI “Stop response” action stops only local polling; it does not cancel
robot motion. The operator must explicitly ask the robot to stop.

Navigation is grounded in correlated ROS state. Acceptance is not reported as
arrival. The agent reports success only when the gateway publishes a completed
operation for the returned UUID. Missing terminal state becomes an explicit
timeout after 180 seconds.

Learning is opt-in through explicit remember, learn, correction, or forget
language. Secrets, credentials, internal paths, oversized content, and changes
that broaden control are rejected. Zone aliases can target only Zone A, Zone B,
or Zone C. A control constraint can only disable a tool that is already in the
manifest. Structured SQLite history is authoritative; RAG is advisory and may
temporarily lag without weakening the control boundary.
