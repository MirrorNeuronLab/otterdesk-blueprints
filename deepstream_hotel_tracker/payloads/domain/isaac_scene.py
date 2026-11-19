"""Render synchronized live camera frames from The Atrium using Isaac Sim."""

import json
import os
import sys
import time
import traceback
from pathlib import Path

from .layout import CAMERAS, FPS, RESOLUTION
from .robot import NO_ROBOT, ROBOT_SAMPLE, RobotCamera, patrol_xy
from .traffic import MAX_GUESTS, Lobby


class GuestRig:
    """Drive one USD skeleton independently of the other guests."""

    def __init__(self, stage, number, walk):
        from pxr import Usd, UsdGeom, UsdSkel

        prim = stage.GetPrimAtPath(f"/World/Guests/Guest{number:02d}")
        self.visibility = UsdGeom.Imageable(prim).GetVisibilityAttr()
        self.translation = prim.GetAttribute("xformOp:translate")
        self.rotation = prim.GetAttribute("xformOp:rotateZ")
        self.time_codes_per_second = stage.GetTimeCodesPerSecond()
        skeleton = next((node for node in Usd.PrimRange(prim) if node.IsA(UsdSkel.Skeleton)), None)
        if skeleton is None:
            raise RuntimeError(f"The Atrium guest {number} has no USD skeleton.")
        animation = UsdSkel.Animation.Define(stage, f"/World/Animations/Guest{number:02d}Pose")
        animation.CreateJointsAttr(walk.GetJointsAttr().Get())
        animation.CreateScalesAttr(walk.GetScalesAttr().Get(0))
        self.motion = (
            (animation.CreateTranslationsAttr(), walk.GetTranslationsAttr()),
            (animation.CreateRotationsAttr(), walk.GetRotationsAttr()),
        )
        self.sample = None
        self.set_pose(0.0)
        UsdSkel.BindingAPI.Apply(skeleton).CreateAnimationSourceRel().SetTargets([animation.GetPath()])

    def set_pose(self, walk_seconds):
        sample = walk_seconds * self.time_codes_per_second
        if sample == self.sample:
            return
        # Frame zero has both feet planted. Keep only the current joint pose
        # in the session layer as the simulation continues.
        for live, source in self.motion:
            live.Set(source.Get(sample))
        self.sample = sample

    def update(self, guest):
        from pxr import Gf

        self.translation.Set(Gf.Vec3d(guest.x, guest.y, 0))
        self.rotation.Set(guest.heading)
        self.set_pose(guest.walk_time if guest.walking else 0.0)


def capture(app, stage_path, calibration_path, output):
    import numpy as np
    import omni.replicator.core as rep
    import omni.timeline
    import omni.usd
    from pxr import Gf, UsdGeom, UsdSkel

    context = omni.usd.get_context()
    if not context.open_stage(str(stage_path)):
        raise RuntimeError(f"Could not open the OpenUSD Atrium stage at {stage_path}")
    stage = context.get_stage()
    if UsdGeom.GetStageMetersPerUnit(stage) != 1 or UsdGeom.GetStageUpAxis(stage) != UsdGeom.Tokens.z:
        raise RuntimeError("The Atrium stage must use meters and Z up.")
    stage.SetEditTarget(stage.GetSessionLayer())
    app.reset_render_settings()
    width, height = RESOLUTION

    rep.orchestrator.set_capture_on_play(False)
    timeline = omni.timeline.get_timeline_interface()
    timeline.set_auto_update(False)
    timeline.play()
    timeline.commit()
    app.update()
    timeline.pause()
    timeline.set_current_time(0.0)

    cameras = [UsdGeom.Camera.Get(stage, path) for path in CAMERAS]
    models = [camera_calibration(camera) for camera in cameras]
    robot_position = stage.GetPrimAtPath("/World/AgiBot").GetAttribute("xformOp:translate")
    robot_camera = RobotCamera(models)
    walk = UsdSkel.Animation.Get(stage, "/World/Animations/Walk")
    actors = [GuestRig(stage, number, walk) for number in range(1, MAX_GUESTS + 1)]

    products, annotators = [], []
    try:
        for path in CAMERAS:
            product = rep.create.render_product(path, RESOLUTION)
            annotator = rep.AnnotatorRegistry.get_annotator("rgb")
            annotator.attach(product)
            products.append(product)
            annotators.append(annotator)
        # Give Kit time to initialize the render graphs and compile materials.
        for _ in range(48):
            app.update()
        for _ in range(4):
            rep.orchestrator.step(rt_subframes=2, delta_time=0.0, pause_timeline=True)

        temporary = calibration_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(models, allow_nan=False))
        temporary.replace(calibration_path)
        print(f"Isaac Sim ready with {len(cameras)} calibrated Atrium cameras at {width}x{height}.", flush=True)
        lobby = Lobby()
        atlas = np.empty((height * 2, width * 2, 3), dtype=np.uint8)
        live_slots = set()
        tick = 1 / FPS
        last = time.monotonic() - tick
        next_robot_sample = 0.0
        while True:
            now = time.monotonic()
            # Limit step size so guests remain visible on both sides of a door
            # even when a render frame takes longer than the target interval.
            dt = min(2 * tick, now - last)
            guests = lobby.advance(dt)
            robot_position.Set(Gf.Vec3d(*patrol_xy(lobby.elapsed), 0))
            current_slots = {guest.slot for guest in guests}
            for slot in live_slots - current_slots:
                actors[slot].visibility.Set(UsdGeom.Tokens.invisible)
            for guest in guests:
                actor = actors[guest.slot]
                actor.update(guest)
                if guest.slot not in live_slots:
                    actor.visibility.Set(UsdGeom.Tokens.inherited)
            live_slots = current_slots
            rep.orchestrator.step(rt_subframes=1, delta_time=0.0, pause_timeline=True)

            for index, annotator in enumerate(annotators):
                rgb = np.asarray(annotator.get_data())
                if rgb.ndim != 3 or rgb.shape[:2] != (height, width) or rgb.shape[2] not in (3, 4):
                    raise RuntimeError(f"Isaac Sim returned an empty RGB frame for {CAMERAS[index]}.")
                top, left = (index // 2) * height, (index % 2) * width
                atlas[top:top + height, left:left + width] = rgb[:, :, :3]
            robot = NO_ROBOT
            if now >= next_robot_sample:
                robot = robot_camera.observe(atlas)
                next_robot_sample = now + .3
            output.write(ROBOT_SAMPLE.pack(*robot))
            output.write(atlas.data)
            output.flush()
            last = now
            time.sleep(max(0, tick - (time.monotonic() - now)))
    finally:
        for product, annotator in zip(products, annotators):
            annotator.detach(product)
            product.destroy()


def camera_calibration(camera):
    """Project USD world coordinates into this render product's image pixels."""
    import numpy as np
    from pxr import Usd, UsdGeom

    if not camera or camera.GetProjectionAttr().Get() != UsdGeom.Tokens.perspective:
        raise ValueError("The Atrium needs a perspective USD camera for every tracked stream.")
    width, height = RESOLUTION
    focal = camera.GetFocalLengthAttr().Get()
    horizontal, vertical = camera.GetHorizontalApertureAttr().Get(), camera.GetVerticalApertureAttr().Get()
    center_x = width / 2 - width * camera.GetHorizontalApertureOffsetAttr().Get() / horizontal
    center_y = height / 2 + height * camera.GetVerticalApertureOffsetAttr().Get() / vertical
    intrinsic = np.array([[width * focal / horizontal, 0, center_x],
                          [0, height * focal / vertical, center_y], [0, 0, 1]])
    # USD uses -Z forward, +Y up and row vectors. DeepStream expects
    # OpenCV's +Z forward, +Y down and a row-major 3x4 projection matrix.
    pose = UsdGeom.Xformable(camera).ComputeLocalToWorldTransform(Usd.TimeCode.Default())
    world_to_cv = np.diag([1, -1, -1, 1]) @ np.asarray(pose.GetInverse()).T
    return {
        "projectionMatrix_3x4_w2p": (intrinsic @ world_to_cv[:3]).ravel().tolist(),
        "worldUnitsPerMeter": 1.0,
        "modelInfo": [{"classID": 1, "height": 1.7, "radius": 0.3}],
    }


def main(stage, calibration, frame_fd):
    from isaacsim import SimulationApp

    width, height = RESOLUTION
    app = SimulationApp({
        "headless": True, "renderer": "RealTimePathTracing", "width": width, "height": height,
        "disable_viewport_updates": True,
        "extra_args": ["--allow-root"],
    })
    status = 0
    try:
        with os.fdopen(int(frame_fd), "wb") as output:
            capture(app, Path(stage), Path(calibration), output)
    except BrokenPipeError:
        # The supervising worker closed the raw-video pipe during shutdown.
        pass
    except Exception:
        traceback.print_exc()
        status = 1
    finally:
        app.close(exit_code=status)
    return status


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
