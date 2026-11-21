"""Convert the declared scan and publish verified run artifacts."""

import hashlib
import json
import os
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from time import monotonic

from mn_sdk.blueprint.context import source_manifest
from mn_sdk.blueprint.hooks import report_activity
from mn_sdk.blueprint.inputs import capture_declared_inputs
from mn_sdk.blueprint.outputs import publish_artifact_bundle
from mn_sdk_common.publication import ArtifactWrite

from domain.preview import publish_preview
from domain.scan_io import read_header

SCENE = "scene.usdc"
REPORT = "scan_result.json"
SCHEMA = "otterdesk.lidar_scene.v1"
# Leave time within the block budget for publication and a best-effort preview.
NUREC_TIMEOUTS = {"export": 780, "project": 60}


def run_nurec(block, command, *paths):
    runfiles = Path(os.environ["NUREC_RUNFILES"])
    env = {
        **os.environ,
        "RUNFILES_DIR": str(runfiles),
        "PYTHONPATH": os.pathsep.join((str(runfiles / "_main"), str(Path(__file__).resolve().parents[1]))),
    }
    arguments = [os.environ["NUREC_PYTHON"], "-s", "-m", "domain.nurec_export", command, *map(str, paths)]
    if command == "export":
        gpu = source_manifest(__file__, env=block.environment)["requirements"]["gpu"]
        arguments += ["--min-memory-mib", str(gpu["min_memory_mb"])]
    block.check()
    deadline = monotonic() + NUREC_TIMEOUTS[command]
    with subprocess.Popen(arguments, env=env, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True) as process:
        try:
            while True:
                remaining = deadline - monotonic()
                if remaining <= 0:
                    raise TimeoutError("NuRec took too long to process the scan.")
                try:
                    message, _ = process.communicate(timeout=min(1, remaining))
                    break
                except subprocess.TimeoutExpired:
                    block.check()
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate()
    block.check()
    if process.returncode == 2 and message.strip():
        raise ValueError(message.strip()[:300])
    if process.returncode:
        raise RuntimeError("NuRec couldn't process the scan. Check the PLY export and the NVIDIA runtime.")


def check_scan(block, inputs):
    request = capture_declared_inputs(block, inputs, runtime_file=__file__)
    source = Path(request["scan_file"])
    if source.suffix.lower() != ".ply" or source.is_symlink() or not source.is_file():
        raise ValueError("Choose a registered PLY point cloud.")
    with source.open("rb") as stream:
        return {"scan_file": str(source), "point_count": read_header(stream).count}


def publish_conversion(block, scan, work):
    receipt_path = block.root + "/conversion.json"
    if block.store.path(receipt_path).is_file():
        saved = block.store.read_path(receipt_path)
        artifacts = {entry["id"]: entry["reference"] for entry in saved["artifacts"]}
        scene_bytes = block.store.read_bytes(artifacts["openusd_scene"])
        report_bytes = block.store.read_bytes(artifacts["scan_result"])
    else:
        scene_path = work / SCENE
        summary = work / REPORT
        run_nurec(block, "export", Path(scan["scan_file"]), scene_path, summary)
        details = json.loads(summary.read_text(encoding="utf-8"))
        if details["point_count"] != scan["point_count"]:
            raise ValueError("The staged scan point count changed during conversion.")
        scene_bytes = scene_path.read_bytes()
        report = {
            "schema": SCHEMA,
            **details,
            "scene": {
                "path": SCENE,
                "sha256": hashlib.sha256(scene_bytes).hexdigest(),
                "size_bytes": len(scene_bytes),
            },
        }
        report_bytes = json.dumps(report, allow_nan=False, indent=2).encode("utf-8") + b"\n"
    saved = publish_artifact_bundle(block, [
        ArtifactWrite("openusd_scene", SCENE, scene_bytes, kind="openusd", authoritative=True),
        ArtifactWrite("scan_result", REPORT, report_bytes, kind="json"),
    ], receipt_path=receipt_path)
    return {entry["id"]: entry["reference"] for entry in saved["artifacts"]}, json.loads(report_bytes)


def convert_scan(block, inputs):
    scan = inputs["scan"]

    def activity(message, kind, level="info"):
        report_activity(message, kind=kind, level=level, step_id=block.step_id, run_dir=block.store.run_dir)

    activity("Converting the registered LiDAR scan with NVIDIA NuRec.", "action")
    with TemporaryDirectory(prefix="lidar-scene-") as temporary:
        work = Path(temporary)
        artifacts, report = publish_conversion(block, scan, work)
        count = report["point_count"]
        activity(f"Saved the OpenUSD scene with {count:,} points.", "result")
        try:
            projection = work / "projection.json"
            scene = block.store.path(artifacts["openusd_scene"]["path"])
            run_nurec(block, "project", scene, projection)
            publish_preview(block, report, json.loads(projection.read_text(encoding="utf-8")))
        except Exception:
            block.check()
            activity("The OpenUSD scene was saved. Couldn't publish the web preview.", "diagnostic", "warning")
    return {"scene": artifacts["openusd_scene"], "report": artifacts["scan_result"], "point_count": count}
