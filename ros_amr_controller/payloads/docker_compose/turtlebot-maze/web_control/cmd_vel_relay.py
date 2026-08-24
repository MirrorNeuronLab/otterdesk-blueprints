#!/usr/bin/env python3
"""Safely relay dashboard velocity requests to the simulated TurtleBot."""

from __future__ import annotations

import time

import rclpy
from geometry_msgs.msg import TwistStamped
from rclpy.duration import Duration
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy


class DashboardCommandRelay(Node):
    """Forward fresh dashboard requests without competing with Nav2 when idle."""

    def __init__(self) -> None:
        super().__init__("warehouse_dashboard_command_relay")
        browser_qos = QoSProfile(
            depth=10,
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
            lifespan=Duration(seconds=1),
        )
        robot_qos = QoSProfile(
            depth=10,
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.VOLATILE,
        )
        self._command = TwistStamped()
        self._last_command_time = 0.0
        self._stop_burst_remaining = 0
        self._stopping = False
        self._publisher = self.create_publisher(TwistStamped, "/cmd_vel", robot_qos)
        self.create_subscription(TwistStamped, "/web_cmd_vel", self._receive_command, browser_qos)
        self.create_timer(0.05, self._publish_fresh_command)
        self.get_logger().info("Dashboard relay ready: /web_cmd_vel -> /cmd_vel")

    def _receive_command(self, message: TwistStamped) -> None:
        self._command = message
        self._last_command_time = time.monotonic()
        self._stop_burst_remaining = 4
        self._stopping = False

    def _publish_command(self) -> None:
        self._command.header.stamp = self.get_clock().now().to_msg()
        self._command.header.frame_id = "base_link"
        self._publisher.publish(self._command)

    def _publish_fresh_command(self) -> None:
        if time.monotonic() - self._last_command_time <= 0.35:
            self._publish_command()
            return
        if self._stop_burst_remaining:
            if not self._stopping:
                self.get_logger().warn("Dashboard command watchdog expired; stopping robot")
                self._stopping = True
            self._command = TwistStamped()
            self._publish_command()
            self._stop_burst_remaining -= 1


def main() -> None:
    rclpy.init()
    node = DashboardCommandRelay()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
