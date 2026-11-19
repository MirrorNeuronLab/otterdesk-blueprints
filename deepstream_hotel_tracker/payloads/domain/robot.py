"""Move the simulated AgiBot and observe its tag in the rendered camera frames."""

import math
from struct import Struct

from .layout import RESOLUTION, inside_room


ROBOT_SAMPLE = Struct("!ffb")
NO_ROBOT = (0.0, 0.0, -1)
TAG_ID = 27
# The robot travels omnidirectionally with the tag facing the overview camera.
# Match the authored tag placement and base rotation in agibot.usda.
TAG_HEIGHT = 1.06
TAG_OFFSET = (
    .325 * math.cos(math.radians(-40)),
    .325 * math.sin(math.radians(-40)),
)


def patrol_xy(seconds):
    angle = math.tau * seconds / 31
    return 4.25 + 1.10 * math.cos(angle), -1.25 + 2.35 * math.sin(angle)


class RobotCamera:
    def __init__(self, camera_models):
        import cv2
        import numpy as np

        self.cv = cv2
        self.np = np
        dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
        params = cv2.aruco.DetectorParameters()
        params.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
        params.minMarkerPerimeterRate = .018
        self.detector = cv2.aruco.ArucoDetector(dictionary, params)
        self.inverse_projections = []
        for model in camera_models:
            matrix = np.array(model["projectionMatrix_3x4_w2p"]).reshape(3, 4)
            plane = matrix[:, [0, 1, 3]]
            plane[:, 2] += TAG_HEIGHT * matrix[:, 2]
            self.inverse_projections.append(np.linalg.inv(plane))

    def observe(self, atlas):
        """Localize the robot only when a camera decodes its optical tag."""
        width, height = RESOLUTION
        best_area = 0
        best = NO_ROBOT
        for camera, inverse in enumerate(self.inverse_projections):
            top, left = (camera // 2) * height, (camera % 2) * width
            frame = atlas[top:top + height, left:left + width]
            gray = self.cv.cvtColor(frame, self.cv.COLOR_RGB2GRAY)
            corners, ids, _ = self.detector.detectMarkers(gray)
            if ids is None:
                continue
            for marker, tag in zip(corners, ids.ravel()):
                if tag != TAG_ID:
                    continue
                area = self.cv.contourArea(marker)
                if area <= best_area:
                    continue
                # The diagonals intersect at the center of the tag even when
                # the camera views it at an angle.
                points = self.np.column_stack((marker[0], self.np.ones(4)))
                cross = self.np.cross
                center = cross(cross(points[0], points[2]), cross(points[1], points[3]))
                x, y, scale = inverse @ center
                if abs(scale) < 1e-8:
                    continue
                robot_x, robot_y = x / scale - TAG_OFFSET[0], y / scale - TAG_OFFSET[1]
                if inside_room(robot_x, robot_y):
                    best = robot_x, robot_y, camera
                    best_area = area
        return best
