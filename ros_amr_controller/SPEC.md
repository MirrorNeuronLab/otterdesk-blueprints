# Specification

- The executable authority is `type: service` with one root
  `MirrorNeuron.Runner.DockerCompose` worker.
- The full TurtleBot Compose source is a blueprint payload at
  `payloads/docker_compose/turtlebot-maze`; large contexts are staged through
  shared storage with a verified digest before Spark builds them.
- Placement is capability based: one NVIDIA CUDA GPU and native capability
  `docker_compose_prepare_v1` are required, with no node name embedded in the
  scheduling constraints.
- The native host owns one exclusive Docker Compose project for this service.
  Starting a new service run first tears down the previous project, including
  its orphans and volumes, then starts the new project. It does not use or
  modify the MirrorNeuron runtime Compose environment or DockerWorker
  generated worker Compose file.
- The root project starts the warehouse simulation, video server/UI, rosbridge,
  control relay, navigation gateway, and bounded MCP service. Readiness requires
  all services running plus dashboard, MCP, video, and rosbridge checks.
- GUI mounts are opt-in. Spark runs with the headless settings in
  `mirrorneuron/warehouse.env`; local GUI development can provide explicit
  `TURTLEBOT_X11_SOCKET` and `TURTLEBOT_XAUTHORITY` values.
- The Web UI is the existing TurtleBot dashboard on port 8088. When it is
  opened through MirrorNeuron, its video stream (8080) and rosbridge (9090)
  use the authenticated local job UI proxy instead of exposing the Spark host
  to the browser. The MCP service advertises Streamable HTTP at `/mcp` on port
  8090 and is not part of that UI proxy allowlist.
- The response-agent declaration is the single control contract. User tools
  are exactly `get_robot_status`, `navigate_to_zone`, `cancel_navigation`, and
  `adjust_robot`; the internal operation tool is exactly
  `get_navigation_operation`. Navigation accepts only zones A/B/C, and manual
  adjustments are short pulses routed through a dead-man relay.
- The bounded response agent is Job-scoped and starts with the stable response
  service. It is not a DAG node and does not start, resume, or replace the
  run-scoped Compose service. Effects require one passing MCP service whose
  name, path, tags, registry, and argument schemas match the manifest exactly.
- Each initial agent turn uses one strict JSON completion from the resolved
  `default` model. Invalid output or model failure causes no motion. One turn
  can produce at most one control effect or one explicit memory mutation.
- `navigate_to_zone` returns an operation UUID. The navigation gateway accepts
  both correlated JSON commands and the dashboard's existing string commands;
  correlated progress is published separately without breaking dashboard
  status. `get_job_turn` polls the observed operation at one-second intervals
  for no more than 180 seconds.
- Job knowledge and RAG resources are durable across ROS Run restarts. Explicit
  memory supports only Zone A/B/C aliases, capability notes, and constraints
  that disable existing controls. It cannot add coordinates, tools, speed,
  duration, or relaxed safety.
- A direct human prohibition such as “Do not enter Zone C” is an explicit,
  argument-scoped control constraint. It blocks only navigation to Zone C,
  returns the applied rule identity with the command receipt, and links to the
  authoritative Job file at `knowledge/learned/active.md`.
- Robot tools return bounded confirmation metadata. The Job response preserves
  command state, target, validated arguments, applied rules, and learned-memory
  receipts so clients do not infer control or safety outcomes from prose.
- Pause, cancel, retry failure, and stop clean up only the owned Compose project;
  resume starts it again from the same staged source and project identity.
- Stable job data, definition identity, and schedules remain independent from
  run-scoped service history.
