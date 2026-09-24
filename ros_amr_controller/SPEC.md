# Specification

- The executable authority is `type: service` with one root
  `MirrorNeuron.Runner.DockerCompose` worker.
- The desktop sample profile launches the bundled `warehouse` scenario from
  the checked-in default configuration; no external input data is required.
- The full TurtleBot Compose source is a blueprint payload at
  `payloads/docker_compose/turtlebot-maze`; large contexts are staged through
  shared storage with a verified digest before Spark builds them.
- Placement is capability based: one NVIDIA CUDA GPU and native capability
  `docker_compose_prepare_v1` are required, with no node name embedded in the
  scheduling constraints. Service addresses and the Web UI handle resolve from
  the selected node's advertised runtime address.
- The native host owns one exclusive Docker Compose project for this service.
  Starting a new service run first tears down the previous project, including
  its orphans and volumes, then starts the new project. It does not use or
  modify the MirrorNeuron runtime Compose environment or DockerWorker
  generated worker Compose file.
- The root project starts the warehouse simulation, video server/UI, rosbridge,
  control relay, navigation gateway, and bounded MCP service. Readiness requires
  all services running plus dashboard, MCP, video, and rosbridge checks. These
  checks target the selected node's advertised address because the native SDK
  evaluates them from its own container network.
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
- Each initial agent turn uses the shared SDK structured planner with the resolved
  `default` model (`openai_compatible`, `api_base: auto`). Invalid output or model failure causes no motion. One turn
  can produce at most one control effect or one explicit memory mutation. RAG
  retrieval is capped at two compact chunks and 1,000 characters so the plan,
  Job context, and bounded answer remain inside the model context window.
- Job/Run status is a timestamped structured context plane, never vector-indexed
  knowledge. Conversation may use a clearly marked last-known-good snapshot for
  up to 30 seconds, but every non-emergency motion calls `get_robot_status`
  live and requires `connected: true` before the motion tool is invoked.
- Typed chat requests are interpreted semantically through declared MCP tool
  descriptions: “move to zone A” selects `navigate_to_zone(zone_a)` and “stop”
  selects `cancel_navigation()`. B/C and polite paraphrases are supported.
- Cancellation has effect `stop`, distinct from `motion`, and skips the live
  motion preflight. It still uses the shared planner and MCP service validation.
  It cancels robot movement while leaving the simulation service running.
- `navigate_to_zone` returns an operation UUID. The navigation gateway accepts
  both correlated JSON commands and the dashboard's existing string commands;
  correlated progress is published separately without breaking dashboard
  status. `get_job_turn` polls the observed operation at one-second intervals
  for no more than 180 seconds.
- Job knowledge and RAG resources are durable across ROS Run restarts. Explicit
  memory supports only Zone A/B/C aliases, capability notes, and constraints
  that disable existing controls. It cannot add coordinates, tools, speed,
  duration, or relaxed safety.
- Durable RAG contains only capabilities, zone semantics, safety rules, and
  human-learned knowledge. Operational pose, Run state, navigation progress,
  and service health remain in the freshness-marked live context plane.
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

## Blueprint package format

This blueprint uses the canonical blueprint/v1 format in both folders and ZIPs.
`manifest.json` contains identity, semantic release version, and document references.
`workflow.json` owns logical topology and policies; `execution.json` owns workers,
resources, and services; `contracts.json` owns input/output and artifact contracts.
Platform descriptors live in `extensions/`, package requirements in
`dependencies.json` when present, and operator defaults in `config/default.json`.
The SDK reads these documents together and compiles the Core execution artifact.
A ZIP contains the same files as the folder. Local overrides and invocation
configuration are resolved by the SDK before launch.
