#!/usr/bin/env python3
"""Bounded Streamable HTTP MCP control surface for the warehouse TurtleBot."""

from __future__ import annotations

import argparse
import logging
import os
import threading
import time
from typing import Literal, TypedDict

from mcp.server import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from starlette.requests import Request
from starlette.responses import JSONResponse


LOGGER = logging.getLogger("ros_amr_controller.mcp")
Zone = Literal["zone_a", "zone_b", "zone_c"]
Direction = Literal["forward", "left", "right"]


class RobotStatus(TypedDict):
    connected: bool
    navigation_status: str
    pose: dict[str, float] | None


class CommandReceipt(TypedDict):
    accepted: bool
    command: str
    message: str


class RosControlBridge:
    """Own the ROS publishers/subscribers used by the intentionally small tool set."""

    def __init__(self) -> None:
        import rclpy
        from geometry_msgs.msg import TwistStamped
        from nav_msgs.msg import Odometry
        from rclpy.duration import Duration
        from rclpy.node import Node
        from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
        from std_msgs.msg import String

        rclpy.init()
        self._rclpy = rclpy
        self._twist_type = TwistStamped
        self._string_type = String
        self._node = Node("warehouse_amr_mcp_control")
        self._state_lock = threading.Lock()
        self._command_lock = threading.Lock()
        self._navigation_status = "waiting"
        self._pose: dict[str, float] | None = None

        browser_qos = QoSProfile(
            depth=10,
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
            lifespan=Duration(seconds=1),
        )
        status_qos = QoSProfile(
            depth=1,
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
        )
        self._navigation_publisher = self._node.create_publisher(
            String, "/web_navigation_command", browser_qos
        )
        self._velocity_publisher = self._node.create_publisher(
            TwistStamped, "/web_cmd_vel", browser_qos
        )
        self._node.create_subscription(
            String, "/warehouse/navigation_status", self._on_navigation_status, status_qos
        )
        self._node.create_subscription(Odometry, "/odom", self._on_odometry, 10)
        self._spin_thread = threading.Thread(target=rclpy.spin, args=(self._node,), daemon=True)
        self._spin_thread.start()

    def _on_navigation_status(self, message) -> None:
        with self._state_lock:
            self._navigation_status = str(message.data or "unknown")

    def _on_odometry(self, message) -> None:
        position = message.pose.pose.position
        orientation = message.pose.pose.orientation
        with self._state_lock:
            self._pose = {
                "x": round(float(position.x), 3),
                "y": round(float(position.y), 3),
                "orientation_z": round(float(orientation.z), 4),
                "orientation_w": round(float(orientation.w), 4),
            }

    def status(self) -> RobotStatus:
        with self._state_lock:
            return {
                "connected": self._spin_thread.is_alive(),
                "navigation_status": self._navigation_status,
                "pose": dict(self._pose) if self._pose else None,
            }

    def _publish_navigation(self, command: str) -> None:
        message = self._string_type(data=command)
        for _ in range(3):
            self._navigation_publisher.publish(message)
            time.sleep(0.1)

    def navigate(self, zone: Zone) -> CommandReceipt:
        with self._command_lock:
            self._publish_navigation(zone)
        return {
            "accepted": True,
            "command": f"navigate:{zone}",
            "message": f"Requested autonomous navigation to {zone.replace('_', ' ').title()}.",
        }

    def cancel(self) -> CommandReceipt:
        with self._command_lock:
            self._publish_navigation("cancel")
            self._publish_stop_burst()
        return {
            "accepted": True,
            "command": "cancel_navigation",
            "message": "Requested cancellation and sent a bounded stop burst.",
        }

    def _twist(self, linear: float = 0.0, angular: float = 0.0):
        message = self._twist_type()
        message.header.stamp = self._node.get_clock().now().to_msg()
        message.header.frame_id = "base_link"
        message.twist.linear.x = linear
        message.twist.angular.z = angular
        return message

    def _publish_stop_burst(self) -> None:
        for _ in range(6):
            self._velocity_publisher.publish(self._twist())
            time.sleep(0.1)

    def adjust(self, direction: Direction) -> CommandReceipt:
        velocities = {
            "forward": (0.10, 0.0),
            "left": (0.0, 0.40),
            "right": (0.0, -0.40),
        }
        linear, angular = velocities[direction]
        with self._command_lock:
            self._publish_navigation("cancel")
            deadline = time.monotonic() + 0.5
            while time.monotonic() < deadline:
                self._velocity_publisher.publish(self._twist(linear, angular))
                time.sleep(0.1)
            self._publish_stop_burst()
        return {
            "accepted": True,
            "command": f"adjust:{direction}",
            "message": f"Completed one watchdog-limited {direction} adjustment pulse.",
        }

    def close(self) -> None:
        self._node.destroy_node()
        if self._rclpy.ok():
            self._rclpy.shutdown()
        self._spin_thread.join(timeout=2)


mcp = MCPServer(
    "ROS AMR Controller",
    instructions=(
        "Control only the simulated warehouse TurtleBot. Prefer named-zone navigation. "
        "Use adjust_robot only for one short fine-adjustment pulse, and use cancel_navigation "
        "whenever the operator asks the robot to stop."
    ),
)
_control: RosControlBridge | None = None


def control() -> RosControlBridge:
    if _control is None:
        raise RuntimeError("ROS control is not ready")
    return _control


@mcp.tool()
def get_robot_status() -> RobotStatus:
    """Read the current Nav2 status and latest simulated robot pose without changing motion."""

    return control().status()


@mcp.tool()
def navigate_to_zone(zone: Zone) -> CommandReceipt:
    """Navigate the simulated robot to one allowlisted warehouse zone: zone_a, zone_b, or zone_c."""

    return control().navigate(zone)


@mcp.tool()
def cancel_navigation() -> CommandReceipt:
    """Cancel autonomous navigation and issue a bounded zero-velocity stop burst."""

    return control().cancel()


@mcp.tool()
def adjust_robot(direction: Direction) -> CommandReceipt:
    """Apply one 0.5 second watchdog-limited forward, left, or right adjustment pulse."""

    return control().adjust(direction)


@mcp.custom_route("/health", methods=["GET"])
async def health(_request: Request) -> JSONResponse:
    status = control().status()
    return JSONResponse({"status": "ok" if status["connected"] else "degraded"})


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Serve bounded TurtleBot MCP tools over Streamable HTTP.")
    parser.add_argument("--host", default=os.environ.get("MN_ROBOT_MCP_HOST", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("MN_ROBOT_MCP_PORT", "8090")))
    parser.add_argument(
        "--advertise-host",
        default=os.environ.get("MN_ROBOT_MCP_ADVERTISE_HOST", "10.0.4.26"),
    )
    return parser.parse_args()


def main() -> None:
    global _control
    args = parse_args()
    logging.basicConfig(level=logging.INFO)
    _control = RosControlBridge()
    allowed_hosts = [
        f"{args.advertise_host}:{args.port}",
        f"127.0.0.1:{args.port}",
        f"localhost:{args.port}",
    ]
    security = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=allowed_hosts,
        allowed_origins=[],
    )
    LOGGER.info("Serving bounded robot MCP tools at http://%s:%s/mcp", args.host, args.port)
    try:
        mcp.run(
            transport="streamable-http",
            host=args.host,
            port=args.port,
            streamable_http_path="/mcp",
            stateless_http=True,
            json_response=True,
            transport_security=security,
        )
    finally:
        _control.close()
        _control = None


if __name__ == "__main__":
    main()
