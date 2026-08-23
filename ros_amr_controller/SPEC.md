# Specification

- The executable authority is `type: service`.
- Exactly one root DockerWorker runs the complete ROS 2 warehouse service.
- Placement is capability based: one NVIDIA CUDA GPU is required and no node
  name is embedded in the scheduling constraints.
- The DockerWorker requests explicit host networking because ROSbridge, MJPEG,
  and the dashboard are operator-facing services on declared ports.
- The Blueprint Web UI is the existing TurtleBot dashboard, served by the
  worker and tagged `web_ui` in the service declaration.
- A second runtime service tagged `mcp`, `robot-control`, and
  `ros-amr-controller` advertises Streamable HTTP MCP at `/mcp` on port 8090.
- The MCP allowlist is exact: `get_robot_status`, `navigate_to_zone`,
  `cancel_navigation`, and `adjust_robot`. Navigation accepts only the named
  zones A/B/C, and manual adjustments are short pulses routed through a
  dead-man relay.
- The desktop resolves both browser and MCP endpoints from passing services in
  the same run. It never trusts an arbitrary endpoint supplied by conversation
  text or model output.
- Pause terminates the attached service command and its child processes;
  resume restarts them in the existing run and prepared container.
- Stable job data, definition identity, and schedules remain independent from
  run-scoped service history.
