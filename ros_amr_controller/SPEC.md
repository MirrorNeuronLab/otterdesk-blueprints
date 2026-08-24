# Specification

- The executable authority is `type: service` with one root
  `MirrorNeuron.Runner.DockerCompose` worker.
- The full TurtleBot Compose source is a blueprint payload at
  `payloads/docker_compose/turtlebot-maze`; large contexts are staged through
  shared storage with a verified digest before Spark builds them.
- Placement is capability based: one NVIDIA CUDA GPU and native capability
  `docker_compose_prepare_v1` are required, with no node name embedded in the
  scheduling constraints.
- The native host owns an isolated, per-service Docker Compose project. It does
  not use or modify the MirrorNeuron runtime Compose environment or DockerWorker
  generated worker Compose file.
- The root project starts the warehouse simulation, video server/UI, rosbridge,
  control relay, navigation gateway, and bounded MCP service. Readiness requires
  all services running plus dashboard, MCP, video, and rosbridge checks.
- GUI mounts are opt-in. Spark runs with the headless settings in
  `mirrorneuron/warehouse.env`; local GUI development can provide explicit
  `TURTLEBOT_X11_SOCKET` and `TURTLEBOT_XAUTHORITY` values.
- The Web UI is the existing TurtleBot dashboard on port 8088. The MCP service
  advertises Streamable HTTP at `/mcp` on port 8090.
- The MCP allowlist is exact: `get_robot_status`, `navigate_to_zone`,
  `cancel_navigation`, and `adjust_robot`. Navigation accepts only zones A/B/C,
  and manual adjustments are short pulses routed through a dead-man relay.
- Pause, cancel, retry failure, and stop clean up only the owned Compose project;
  resume starts it again from the same staged source and project identity.
- Stable job data, definition identity, and schedules remain independent from
  run-scoped service history.
