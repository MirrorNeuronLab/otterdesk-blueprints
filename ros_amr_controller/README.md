# ROS AMR Controller

This blueprint runs the ROS 2 Jazzy TurtleBot warehouse demo as a long-lived
MirrorNeuron `type: service` job. The local PC remains the control plane. Its
CUDA and NVIDIA device declaration causes normal runtime placement to select
the federated Spark node, where the DockerWorker executes.

The worker uses Spark's `turtlebot_behavior:overlay` image built from
`/home/homer/Sandbox/turtlebot-maze`. The blueprint packages the live dashboard
and its two safe ROS control gateways. It does not pin the runtime node by name;
the hard NVIDIA CUDA requirement selects the joined GPU node.

Run from the control PC:

```bash
mn blueprint validate /Users/homer/Projects/otterdesk-blueprints/ros_amr_controller
mn blueprint run /Users/homer/Projects/otterdesk-blueprints/ros_amr_controller --web-ui --detached
```

The dashboard is advertised at `http://10.0.4.26:8088`. The MCP endpoint is
`http://10.0.4.26:8090/mcp`. Ports 8080, 8088, 8090, and 9090 are declared
runtime resources and must be free on the selected NVIDIA node.

The desktop catalog reads this folder through the root `index.json`. For local
desktop development, point the catalog at this checkout:

```bash
MN_BLUEPRINT_SOURCE=local \
MN_BLUEPRINT_LOCAL=/Users/homer/Projects/otterdesk-blueprints \
npm run dev
```

The desktop only attaches the MCP endpoint for an explicit robot-control
request. The published tools are deliberately small: inspect status, navigate
to one of the named zones A/B/C, cancel navigation, or issue a short
forward/left/right adjustment. Arbitrary ROS topics, shell commands, poses, and
unbounded velocity commands are not exposed.

Pause and resume retain the same service run identity:

```bash
mn run pause <run-id>
mn run resume <run-id>
```

An ordinary second start is rejected. Use the separately confirmed service
replacement flow only when the existing run and its run-scoped history should
be permanently removed.
