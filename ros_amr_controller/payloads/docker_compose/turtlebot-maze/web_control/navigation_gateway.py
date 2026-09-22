#!/usr/bin/env python3
"""Translate fixed dashboard zone requests into monitored Nav2 goals."""

from __future__ import annotations

import json
import math
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

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
        self._operation_publisher = self.create_publisher(
            String, "/warehouse/navigation_operation", status_qos
        )
        self._initial_pose_publisher = self.create_publisher(PoseWithCovarianceStamped, "/initialpose", 10)
        self.create_subscription(String, "/web_navigation_command", self._on_command, browser_qos)
        self.create_subscription(Odometry, "/odom", self._on_odometry, 10)
        self._navigation_client = ActionClient(self, NavigateToPose, "/navigate_to_pose")
        self._pending_route: str | None = None
        self._pending_operation_id: str | None = None
        self._active_route: str | None = None
        self._active_operation_id: str | None = None
        self._superseded_operations: set[str] = set()
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

    def _publish_operation(
        self,
        operation_id: str | None,
        state: str,
        *,
        zone: str | None = None,
        progress: str | None = None,
        reason: str | None = None,
    ) -> None:
        if not operation_id:
            return
        payload = {
            "operation_id": operation_id,
            "state": state,
            "updated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        }
        if zone:
            payload["zone"] = zone
        if progress:
            payload["progress"] = progress
        if reason:
            payload["reason"] = reason
        self._operation_publisher.publish(
            String(data=json.dumps(payload, sort_keys=True, separators=(",", ":")))
        )

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
            self._publish_operation(
                self._pending_operation_id, "running", zone=route, progress="waiting_for_odometry"
            )
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
        self._publish_operation(
            self._pending_operation_id, "running", zone=route, progress="localizing"
        )
        return True

    def _on_command(self, message: String) -> None:
        raw_command = message.data.strip()
        operation_id: str | None = None
        try:
            correlated = json.loads(raw_command)
        except json.JSONDecodeError:
            correlated = None
        if isinstance(correlated, dict) and correlated.get("kind") == "navigate":
            command = str(correlated.get("zone") or "").strip().lower()
            try:
                operation_id = str(uuid.UUID(str(correlated.get("operation_id") or "")))
            except (ValueError, TypeError, AttributeError):
                self.get_logger().warning("Ignoring correlated navigation request with invalid operation id")
                return
        else:
            command = raw_command.lower()
        if command == "cancel":
            if self._pending_operation_id:
                self._publish_operation(
                    self._pending_operation_id,
                    "cancelled",
                    zone=self._pending_route,
                    progress="cancelled_before_start",
                )
            self._pending_route = None
            self._pending_operation_id = None
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
        if self._pending_operation_id and self._pending_operation_id != operation_id:
            self._publish_operation(
                self._pending_operation_id,
                "superseded",
                zone=self._pending_route,
                progress="superseded",
            )
            self._superseded_operations.add(self._pending_operation_id)
        if self._active_operation_id and self._active_operation_id != operation_id:
            self._publish_operation(
                self._active_operation_id,
                "superseded",
                zone=self._active_route,
                progress="superseded",
            )
            self._superseded_operations.add(self._active_operation_id)
        self._pending_route = command
        self._pending_operation_id = operation_id
        self._publish_operation(operation_id, "accepted", zone=command, progress="accepted")
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
        operation_id = self._pending_operation_id
        self._pending_route = None
        self._pending_operation_id = None
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
        self._publish_operation(operation_id, "running", zone=route, progress="routing")
        future = self._navigation_client.send_goal_async(goal)
        future.add_done_callback(
            lambda response, route_name=route, correlated_id=operation_id: self._on_goal_response(
                response, route_name, correlated_id
            )
        )

    def _on_goal_response(self, future, route: str, operation_id: str | None) -> None:
        self._goal_request_in_flight = False
        try:
            goal_handle = future.result()
        except Exception as error:  # rclpy action transport error
            self.get_logger().error(f"Could not request route to {route}: {error}")
            self._publish_status(f"failed:{route}")
            if operation_id not in self._superseded_operations:
                self._publish_operation(
                    operation_id, "failed", zone=route, reason="goal_request_failed"
                )
            self._send_pending_route()
            return
        if not goal_handle.accepted:
            self.get_logger().warning(f"Nav2 rejected route to {route}")
            self._publish_status(f"failed:{route}")
            if operation_id not in self._superseded_operations:
                self._publish_operation(
                    operation_id, "failed", zone=route, reason="goal_rejected"
                )
            self._send_pending_route()
            return

        self._goal_handle = goal_handle
        self._active_route = route
        self._active_operation_id = operation_id
        result_future = goal_handle.get_result_async()
        result_future.add_done_callback(
            lambda result, route_name=route, correlated_id=operation_id: self._on_goal_result(
                result, route_name, correlated_id
            )
        )
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
        active_operation_id = self._active_operation_id
        future = self._goal_handle.cancel_goal_async()
        future.add_done_callback(
            lambda response, route_name=active_route, correlated_id=active_operation_id: self._on_cancel_response(
                response, route_name, correlated_id
            )
        )

    def _on_cancel_response(self, future, route: str | None, operation_id: str | None) -> None:
        self._cancel_in_flight = False
        try:
            accepted = bool(future.result().goals_canceling)
        except Exception as error:  # rclpy action transport error
            self.get_logger().error(f"Could not cancel route to {route}: {error}")
            accepted = False
        if accepted:
            self._publish_status(f"cancelled:{route}" if route else "cancelled")
            if operation_id not in self._superseded_operations:
                self._publish_operation(
                    operation_id, "cancelled", zone=route, progress="cancelled"
                )
            self._goal_handle = None
            self._active_route = None
            self._active_operation_id = None
            self._send_pending_route()
        else:
            self.get_logger().warning(f"Nav2 did not confirm cancellation of route to {route}")

    def _on_goal_result(self, future, route: str, operation_id: str | None) -> None:
        try:
            status = future.result().status
        except Exception as error:  # rclpy action transport error
            self.get_logger().error(f"Route to {route} ended with an error: {error}")
            status = GoalStatus.STATUS_ABORTED

        if self._active_route != route or self._active_operation_id != operation_id:
            return
        self._goal_handle = None
        self._active_route = None
        self._active_operation_id = None
        self._cancel_in_flight = False
        if status == GoalStatus.STATUS_SUCCEEDED:
            self._publish_status(f"arrived:{route}")
            if operation_id not in self._superseded_operations:
                self._publish_operation(
                    operation_id, "completed", zone=route, progress="arrived"
                )
        elif status == GoalStatus.STATUS_CANCELED:
            self._publish_status(f"cancelled:{route}")
            if operation_id not in self._superseded_operations:
                self._publish_operation(
                    operation_id, "cancelled", zone=route, progress="cancelled"
                )
        else:
            self._publish_status(f"failed:{route}")
            if operation_id not in self._superseded_operations:
                self._publish_operation(
                    operation_id, "failed", zone=route, reason="navigation_failed"
                )
        if operation_id:
            self._superseded_operations.discard(operation_id)
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
