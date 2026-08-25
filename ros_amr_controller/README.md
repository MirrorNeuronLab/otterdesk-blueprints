# ROS AMR Controller

This long-lived service runs the ROS 2 Jazzy TurtleBot warehouse simulation as
an isolated Docker Compose project on the selected CUDA/NVIDIA runtime node.
The blueprint source includes the complete Compose context at
`payloads/docker_compose/turtlebot-maze`; it does not require a prebuilt image
or a checkout at `/home/homer/Sandbox`.

The control plane stages the large source tree through shared storage, then
Spark's native SDK builds and starts a project named for the service run. This
is separate from MirrorNeuron's own runtime Compose file and from
DockerWorker's generated `docker-compose.workers.yml`.

Run from the control PC:

```bash
mn blueprint validate /Users/homer/Projects/otterdesk-blueprints/ros_amr_controller
mn blueprint run /Users/homer/Projects/otterdesk-blueprints/ros_amr_controller --web-ui --detached
```

The service uses the exclusive Compose project name
`mn-compose-ros-amr-controller` on the selected runtime node. A new launch
clears that previous project before starting, preventing stale services from
holding the dashboard, video, rosbridge, or MCP ports.

The selected Spark node hosts the dashboard on `8088`, the bounded MCP endpoint
on `8090`, video on `8080`, and rosbridge on `9090`. With `--web-ui`, open the
local MirrorNeuron URL printed by the CLI (`/jobs/<job_id>/ui`): it proxies the
dashboard, video streams, and rosbridge through the local Web UI service rather
than navigating the browser directly to Spark. Startup requires all seven
declared Compose services plus the dashboard, MCP health endpoint, video TCP
port, and rosbridge TCP port.

Pausing or stopping the service runs Compose `down --remove-orphans --volumes`
only for this service project. Resuming recreates that same owned project from
the staged, digest-verified source. Other Docker projects and runtime services
on Spark are not touched.

For manual headless Compose development, run from the bundled source:

```bash
cd /Users/homer/Projects/otterdesk-blueprints/ros_amr_controller/payloads/docker_compose/turtlebot-maze
docker compose --env-file mirrorneuron/warehouse.env up --build demo-world-warehouse
```

The desktop catalog reads this folder through the root `index.json`. To use
this local checkout in desktop development, set `MN_BLUEPRINT_SOURCE=local`
and `MN_BLUEPRINT_LOCAL=/Users/homer/Projects/otterdesk-blueprints`.

The published robot controls remain intentionally narrow: inspect status,
navigate only to zones A/B/C, cancel, or make a short watchdog-limited manual
adjustment. Arbitrary ROS topics, shell commands, poses, and unbounded velocity
commands are not exposed.
