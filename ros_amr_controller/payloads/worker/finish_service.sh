#!/usr/bin/env bash
set -euo pipefail

printf '%s\n' '__MN_EVENT__{"type":"service_stopped","payload":{"service":"turtlebot-warehouse","message":"Warehouse navigation service stopped","owner_blueprint":"ros_amr_controller","activity_kind":"result"}}'
printf '%s\n' '{"status":"stopped","service":"turtlebot-warehouse"}'
