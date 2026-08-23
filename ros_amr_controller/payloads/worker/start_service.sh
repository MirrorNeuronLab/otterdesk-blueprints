#!/usr/bin/env bash
set -Eeo pipefail

source /opt/ros/jazzy/setup.bash
source /turtlebot_ws/install/setup.bash
source /overlay_ws/install/setup.bash
set -u

export RMW_IMPLEMENTATION="${RMW_IMPLEMENTATION:-rmw_cyclonedds_cpp}"
export TURTLEBOT_MODEL="${TURTLEBOT_MODEL:-3}"
export GZ_SIM_RESOURCE_PATH="${GZ_SIM_RESOURCE_PATH:-/overlay_ws/install/tb_worlds/share/tb_worlds/worlds:/overlay_ws/install/tb_worlds/share/tb_worlds/models}"
export __EGL_VENDOR_LIBRARY_FILENAMES="${__EGL_VENDOR_LIBRARY_FILENAMES:-/usr/share/glvnd/egl_vendor.d/10_nvidia.json}"
export EGL_PLATFORM="${EGL_PLATFORM:-surfaceless}"
service_root="$(pwd -P)"

declare -A component_pids=()
service_stopping=0
service_lock="/tmp/mn-turtlebot-warehouse-service.lock"
lock_owned=0

cleanup() {
  if [[ "$service_stopping" == "1" ]]; then
    return
  fi
  service_stopping=1
  trap - EXIT INT TERM HUP PIPE
  for pid in "${component_pids[@]:-}"; do
    kill -TERM "$pid" 2>/dev/null || true
  done
  sleep 2
  for pid in "${component_pids[@]:-}"; do
    kill -KILL "$pid" 2>/dev/null || true
    wait "$pid" 2>/dev/null || true
  done
  if [[ "$lock_owned" == "1" ]]; then
    rm -f "${service_lock}/owner.pid"
    rmdir "$service_lock" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM HUP PIPE

if ! command -v nvidia-smi >/dev/null 2>&1; then
  echo "NVIDIA runtime did not expose nvidia-smi" >&2
  exit 69
fi
nvidia-smi -L

while ! mkdir "$service_lock" 2>/dev/null; do
  if curl -fsS http://127.0.0.1:8088/ >/dev/null 2>&1; then
    printf '__MN_EVENT__%s\n' '{"type":"turtlebot_service_heartbeat","payload":{"category":"service","message":"Joined the existing TurtleBot warehouse service"}}'
    sleep 5
  else
    owner_pid="$(cat "${service_lock}/owner.pid" 2>/dev/null || true)"
    if [[ "$owner_pid" =~ ^[0-9]+$ ]] && kill -0 "$owner_pid" 2>/dev/null && \
      tr '\0' ' ' <"/proc/${owner_pid}/cmdline" 2>/dev/null | grep -q 'start_service.sh'; then
      sleep 1
    elif [[ ! -s "${service_lock}/owner.pid" ]]; then
      # The lock owner writes its PID immediately after mkdir. Give that tiny
      # hand-off window time to finish before treating the lock as stale.
      sleep 1
    else
      rm -f "${service_lock}/owner.pid"
      rmdir "$service_lock" 2>/dev/null || true
      sleep 1
    fi
  fi
done
lock_owned=1
printf '%s\n' "$$" >"${service_lock}/owner.pid"

python3 - <<'PY'
import socket
import time

ports = (8080, 8088, 8090, 9090)
deadline = time.monotonic() + 30
while True:
    unavailable = []
    for port in ports:
        sock = socket.socket()
        try:
            sock.bind(("0.0.0.0", port))
        except OSError as error:
            unavailable.append(f"{port}: {error}")
        finally:
            sock.close()
    if not unavailable:
        break
    if time.monotonic() >= deadline:
        raise SystemExit(f"required service ports are unavailable: {', '.join(unavailable)}")
    time.sleep(1)
PY

start_component() {
  local name="$1"
  shift
  "$@" >"/tmp/turtlebot-${name}.log" 2>&1 &
  component_pids["$name"]=$!
}

start_component dashboard python3 -m http.server 8088 --bind 0.0.0.0 --directory "${service_root}/web_ui"
start_component video ros2 run web_video_server web_video_server --ros-args \
  -p address:=0.0.0.0 \
  -p port:=8080 \
  -p server_threads:=4 \
  -p ros_threads:=2 \
  -p default_stream_type:=mjpeg
start_component rosbridge ros2 launch rosbridge_server rosbridge_websocket_launch.xml
start_component control python3 "${service_root}/web_control/cmd_vel_relay.py"
start_component navigation python3 "${service_root}/web_control/navigation_gateway.py"
start_component mcp python3 "${service_root}/mcp/robot_control_server.py" \
  --host 0.0.0.0 \
  --port 8090 \
  --advertise-host "${MN_ROBOT_MCP_ADVERTISE_HOST:-10.0.4.26}"
start_component world ros2 launch tb_worlds tb_demo_world.launch.py \
  world_name:=warehouse_world.sdf.xacro \
  map:=/overlay_ws/install/tb_worlds/share/tb_worlds/maps/warehouse_world_map.yaml \
  rviz_config_file:=/overlay_ws/install/tb_worlds/share/tb_worlds/rviz/nav2_turtlebot_view.rviz \
  headless:=True \
  use_rviz:=False

for _attempt in $(seq 1 60); do
  if curl -fsS http://127.0.0.1:8088/ >/dev/null; then
    break
  fi
  sleep 1
done
curl -fsS http://127.0.0.1:8088/ >/dev/null

for _attempt in $(seq 1 60); do
  if curl -fsS http://127.0.0.1:8090/health >/dev/null; then
    break
  fi
  sleep 1
done
curl -fsS http://127.0.0.1:8090/health >/dev/null

printf '__MN_EVENT__%s\n' '{"type":"turtlebot_service_ready","payload":{"category":"service","message":"TurtleBot warehouse dashboard and bounded MCP controls are ready","url":"http://10.0.4.26:8088","mcp_url":"http://10.0.4.26:8090/mcp"}}'
printf '__MN_EVENT__%s\n' '{"type":"agent_beacon","payload":{"category":"liveness","agent_id":"warehouse_service","message":"TurtleBot warehouse service is healthy"}}'

while true; do
  if [[ ! -d "$service_root" ]]; then
    echo "MirrorNeuron removed the service lease; shutting down"
    exit 0
  fi
  for name in "${!component_pids[@]}"; do
    pid="${component_pids[$name]}"
    if ! kill -0 "$pid" 2>/dev/null; then
      echo "TurtleBot component exited: $name" >&2
      tail -n 80 "/tmp/turtlebot-${name}.log" >&2 || true
      exit 70
    fi
  done
  printf '__MN_EVENT__%s\n' '{"type":"turtlebot_service_heartbeat","payload":{"category":"service","message":"TurtleBot warehouse service is healthy"}}'
  printf '__MN_EVENT__%s\n' '{"type":"agent_beacon","payload":{"category":"liveness","agent_id":"warehouse_service","message":"TurtleBot warehouse service is healthy"}}'
  sleep 5
done
