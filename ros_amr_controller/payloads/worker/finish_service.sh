#!/usr/bin/env bash
set -euo pipefail

printf '%s\n' '__MN_EVENT__{"type":"service_stopped","service":"turtlebot-warehouse"}'
printf '%s\n' '{"status":"stopped","service":"turtlebot-warehouse"}'
