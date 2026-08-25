#!/usr/bin/env python3
"""Serve browser video and publish a display-friendly depth image."""

from __future__ import annotations

import signal
import subprocess
import threading

import numpy as np
import rclpy
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import Image


DEPTH_INPUT_TOPIC = "/camera/depth/image_rect_raw"
DEPTH_DISPLAY_TOPIC = "/camera/depth/image_visualized"
MIN_DEPTH_METERS = 0.2
MAX_DEPTH_METERS = 8.0


def _depth_array(message: Image) -> np.ndarray | None:
    """Return the active depth pixels in meters for supported ROS encodings."""
    byte_order = ">" if message.is_bigendian else "<"
    if message.encoding == "32FC1":
        dtype = np.dtype(f"{byte_order}f4")
        values_per_row = message.step // dtype.itemsize
        scale = 1.0
    elif message.encoding in {"16UC1", "mono16"}:
        dtype = np.dtype(f"{byte_order}u2")
        values_per_row = message.step // dtype.itemsize
        scale = 0.001
    else:
        return None

    expected_values = message.height * values_per_row
    depth = np.frombuffer(message.data, dtype=dtype, count=expected_values)
    return depth.reshape(message.height, values_per_row)[:, : message.width].astype(np.float32) * scale


def _colorize_depth(depth_meters: np.ndarray) -> np.ndarray:
    """Map near-to-far valid depth to a red-green-blue distance gradient."""
    valid = np.isfinite(depth_meters) & (depth_meters > 0.0)
    normalized = np.zeros(depth_meters.shape, dtype=np.float32)
    normalized[valid] = (
        np.clip(depth_meters[valid], MIN_DEPTH_METERS, MAX_DEPTH_METERS) - MIN_DEPTH_METERS
    ) / (MAX_DEPTH_METERS - MIN_DEPTH_METERS)

    red = 255.0 * (1.0 - normalized)
    green = 255.0 * (1.0 - np.abs(2.0 * normalized - 1.0))
    blue = 255.0 * normalized
    rgb = np.stack((red, green, blue), axis=-1).astype(np.uint8)
    rgb[~valid] = 0
    return rgb


class DepthVisualizer(Node):
    """Convert metric depth frames to RGB frames understood by web_video_server."""

    def __init__(self) -> None:
        super().__init__("warehouse_depth_visualizer")
        sensor_qos = QoSProfile(
            depth=2,
            reliability=ReliabilityPolicy.BEST_EFFORT,
            durability=DurabilityPolicy.VOLATILE,
        )
        display_qos = QoSProfile(
            depth=2,
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.VOLATILE,
        )
        self._publisher = self.create_publisher(Image, DEPTH_DISPLAY_TOPIC, display_qos)
        self.create_subscription(Image, DEPTH_INPUT_TOPIC, self._on_depth, sensor_qos)
        self._unsupported_encoding: str | None = None
        self.get_logger().info(
            f"Depth visualization ready: {DEPTH_INPUT_TOPIC} -> {DEPTH_DISPLAY_TOPIC}"
        )

    def _on_depth(self, message: Image) -> None:
        depth = _depth_array(message)
        if depth is None:
            if message.encoding != self._unsupported_encoding:
                self._unsupported_encoding = message.encoding
                self.get_logger().error(f"Unsupported depth encoding: {message.encoding}")
            return

        rgb = _colorize_depth(depth)
        output = Image()
        output.header = message.header
        output.height = message.height
        output.width = message.width
        output.encoding = "rgb8"
        output.is_bigendian = 0
        output.step = message.width * 3
        output.data = rgb.tobytes()
        self._publisher.publish(output)


def _video_server_command() -> list[str]:
    return [
        "ros2",
        "run",
        "web_video_server",
        "web_video_server",
        "--ros-args",
        "-p",
        "address:=0.0.0.0",
        "-p",
        "port:=8080",
        "-p",
        "server_threads:=4",
        "-p",
        "ros_threads:=2",
        "-p",
        "default_stream_type:=mjpeg",
    ]


def main() -> None:
    stop_requested = threading.Event()

    def request_stop(_signal_number, _frame) -> None:
        stop_requested.set()

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)
    rclpy.init()
    node = DepthVisualizer()
    video_server = subprocess.Popen(_video_server_command())
    return_code = 0
    try:
        while rclpy.ok() and not stop_requested.is_set():
            rclpy.spin_once(node, timeout_sec=0.1)
            return_code = video_server.poll()
            if return_code is not None:
                raise RuntimeError(f"web_video_server exited with status {return_code}")
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
        if video_server.poll() is None:
            video_server.terminate()
            try:
                video_server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                video_server.kill()
                video_server.wait(timeout=2)


if __name__ == "__main__":
    main()
