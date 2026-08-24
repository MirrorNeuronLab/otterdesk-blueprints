#!/usr/bin/env python3
"""Translate fixed dashboard zone requests into monitored Nav2 goals."""

from __future__ import annotations

import math
import time
from dataclasses import dataclass

import rclpy
from action_msgs.msg import GoalStatus
from geometry_msgs.msg import PoseStamped, PoseWithCovarianceStamped
from nav2_msgs.action import NavigateToPose
from nav_msgs.msg import Odometry
from rclpy.action import ActionClient
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from std_msgs.msg import String


@dataclass(frozen=True)
class Destination:
    x: float
    y: float
    yaw: float


DESTINATIONS = {
    # These points are in known free space and were verified against the live
    # Nav2 planner in the AWS RoboMaker Small Warehouse map.
    "zone_a": Destination(0.0, -3.0, 0.0),
    "zone_b": Destination(3.0, -3.0, 0.0),
    "zone_c": Destination(6.0, -3.0, 0.0),
}


class WarehouseNavigationGateway(Node):
    """Accept a named zone or cancel request from the LAN dashboard."""

    def __init__(self) -> None:
        super().__init__("warehouse_navigation_gateway")
        browser_qos = QoSProfile(
            depth=10,
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
        )
        status_qos = QoSProfile(
            depth=1,
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
        )
        self._status_publisher = self.create_publisher(String, "/warehouse/navigation_status", status_qos)
        self._initial_pose_publisher = self.create_publisher(PoseWithCovarianceStamped, "/initialpose", 10)
        self.create_subscription(String, "/web_navigation_command", self._on_command, browser_qos)
        self.create_subscription(Odometry, "/odom", self._on_odometry, 10)
        self._navigation_client = ActionClient(self, NavigateToPose, "/navigate_to_pose")
        self._pending_route: str | None = None
        self._active_route: str | None = None
        self._goal_handle = None
        self._goal_request_in_flight = False
        self._cancel_in_flight = False
        self._cancel_after_accept = False
        self._navigation_available = False
        self._latest_odom: Odometry | None = None
        self._route_start_not_before = 0.0
        self.create_timer(0.5, self._check_navigation_server)
        self._publish_status("waiting")
        self.get_logger().info("Navigation gateway ready: fixed warehouse zones -> /navigate_to_pose")

    def _publish_status(self, status: str) -> None:
        self._status_publisher.publish(String(data=status))

    def _check_navigation_server(self) -> None:
        available = self._navigation_client.server_is_ready()
        if available and not self._navigation_available:
            self._navigation_available = True
            self._publish_status("ready")
            self.get_logger().info("Nav2 NavigateToPose action is ready")
        elif not available and self._navigation_available:
            self._navigation_available = False
            self._publish_status("waiting")
        self._send_pending_route()

    def _on_odometry(self, message: Odometry) -> None:
        self._latest_odom = message

    def _synchronize_localization(self, route: str) -> bool:
        """Set AMCL's map pose from exact Gazebo odometry before navigating."""
        if self._latest_odom is None:
            self._publish_status(f"localizing:{route}")
            return False
        initial_pose = PoseWithCovarianceStamped()
        initial_pose.header.stamp = self.get_clock().now().to_msg()
        initial_pose.header.frame_id = "map"
        initial_pose.pose.pose = self._latest_odom.pose.pose
        initial_pose.pose.covariance[0] = 0.05
        initial_pose.pose.covariance[7] = 0.05
        initial_pose.pose.covariance[35] = 0.02
        self._initial_pose_publisher.publish(initial_pose)
        self._route_start_not_before = time.monotonic() + 1.0
        self._publish_status(f"localizing:{route}")
        return True

    def _on_command(self, message: String) -> None:
        command = message.data.strip().lower()
        if command == "cancel":
            self._pending_route = None
            if self._goal_handle is not None:
                self._cancel_active_goal()
            elif self._goal_request_in_flight:
                self._cancel_after_accept = True
                self._publish_status("cancelling")
            else:
                self._publish_status("cancelled")
            return
        if command not in DESTINATIONS:
            self.get_logger().warning(f"Ignoring unknown dashboard navigation request: {command}")
            self._publish_status("unknown")
            return

        self.get_logger().info(f"Dashboard requested route to {command}")
        self._pending_route = command
        self._synchronize_localization(command)
        if self._goal_handle is not None:
            self._publish_status(f"rerouting:{command}")
            self._cancel_active_goal()
        elif self._goal_request_in_flight:
            self._publish_status(f"rerouting:{command}")
        elif not self._navigation_client.server_is_ready():
            self._publish_status("waiting")
        else:
            self._send_pending_route()

    def _send_pending_route(self) -> None:
        if not self._pending_route or self._goal_request_in_flight or self._goal_handle is not None:
            return
        if not self._navigation_client.server_is_ready():
            self._publish_status("waiting")
            return
        if self._latest_odom is None:
            self._publish_status(f"localizing:{self._pending_route}")
            return
        if not self._route_start_not_before:
            self._synchronize_localization(self._pending_route)
            return
        if time.monotonic() < self._route_start_not_before:
            return

        route = self._pending_route
        self._pending_route = None
        destination = DESTINATIONS[route]
        goal = NavigateToPose.Goal()
        goal.pose = PoseStamped()
        goal.pose.header.frame_id = "map"
        goal.pose.pose.position.x = destination.x
        goal.pose.pose.position.y = destination.y
        goal.pose.pose.orientation.z = math.sin(destination.yaw / 2.0)
        goal.pose.pose.orientation.w = math.cos(destination.yaw / 2.0)

        self._goal_request_in_flight = True
        self._publish_status(f"routing:{route}")
        future = self._navigation_client.send_goal_async(goal)
        future.add_done_callback(lambda response, route_name=route: self._on_goal_response(response, route_name))

    def _on_goal_response(self, future, route: str) -> None:
        self._goal_request_in_flight = False
        try:
            goal_handle = future.result()
        except Exception as error:  # rclpy action transport error
            self.get_logger().error(f"Could not request route to {route}: {error}")
            self._publish_status(f"failed:{route}")
            self._send_pending_route()
            return
        if not goal_handle.accepted:
            self.get_logger().warning(f"Nav2 rejected route to {route}")
            self._publish_status(f"failed:{route}")
            self._send_pending_route()
            return

        self._goal_handle = goal_handle
        self._active_route = route
        result_future = goal_handle.get_result_async()
        result_future.add_done_callback(lambda result, route_name=route: self._on_goal_result(result, route_name))
        if self._cancel_after_accept:
            self._cancel_after_accept = False
            self._cancel_active_goal()
        elif self._pending_route:
            self._cancel_active_goal()

    def _cancel_active_goal(self) -> None:
        if self._goal_handle is None or self._cancel_in_flight:
            return
        self._cancel_in_flight = True
        self._publish_status("cancelling")
        active_route = self._active_route
        future = self._goal_handle.cancel_goal_async()
        future.add_done_callback(lambda response, route_name=active_route: self._on_cancel_response(response, route_name))

    def _on_cancel_response(self, future, route: str | None) -> None:
        self._cancel_in_flight = False
        try:
            accepted = bool(future.result().goals_canceling)
        except Exception as error:  # rclpy action transport error
            self.get_logger().error(f"Could not cancel route to {route}: {error}")
            accepted = False
        if accepted:
            self._publish_status(f"cancelled:{route}" if route else "cancelled")
            self._goal_handle = None
            self._active_route = None
            self._send_pending_route()
        else:
            self.get_logger().warning(f"Nav2 did not confirm cancellation of route to {route}")

    def _on_goal_result(self, future, route: str) -> None:
        try:
            status = future.result().status
        except Exception as error:  # rclpy action transport error
            self.get_logger().error(f"Route to {route} ended with an error: {error}")
            status = GoalStatus.STATUS_ABORTED

        if self._active_route != route:
            return
        self._goal_handle = None
        self._active_route = None
        self._cancel_in_flight = False
        if status == GoalStatus.STATUS_SUCCEEDED:
            self._publish_status(f"arrived:{route}")
        elif status == GoalStatus.STATUS_CANCELED:
            self._publish_status(f"cancelled:{route}")
        else:
            self._publish_status(f"failed:{route}")
        self._send_pending_route()


def main() -> None:
    rclpy.init()
    node = WarehouseNavigationGateway()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
