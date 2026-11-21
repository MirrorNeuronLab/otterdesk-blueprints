"""Export registered LiDAR geometry with the pinned NVIDIA NuRec runtime."""

import argparse
import base64
import json
import math
import sys
from pathlib import Path

from domain.scan_io import ScanInputError, read_scan

MAX_PREVIEW_POINTS = 20_000
SCAN_PATH = "/World/Scan"


def prepare_geometry(points, colors, *, device):
    import torch

    vertices = torch.as_tensor(points, dtype=torch.float64, device=device)
    low, high = torch.aminmax(vertices, dim=0)
    span = high - low
    center = low + span / 2
    local = (vertices - center).to(torch.float32)
    if not torch.isfinite(local).all() or (span > torch.finfo(torch.float32).max).any():
        raise ScanInputError("Choose a scan with a finite extent in metres.")
    if colors is None:
        height = ((vertices[:, 2] - low[2]) / span[2].clamp(min=1e-6)).to(torch.float32)
        floor = local.new_tensor([0.25, 0.65, 0.90])
        ceiling = local.new_tensor([1.00, 0.73, 0.40])
        colors = torch.lerp(floor, ceiling, height[:, None]).cpu().numpy()
    diameter = (torch.linalg.vector_norm(span) / math.sqrt(len(points))).clamp(0.005, 0.25)
    return local.cpu().numpy(), colors, center.tolist(), float(diameter), [low.tolist(), high.tolist()]


def write_scene(path, positions, colors, center, diameter):
    import numpy as np
    import torch
    from nurec.utils.io.export.gaussian_export_accessor import GaussianAttributes, ModelCapabilities
    from nurec.utils.io.export.gaussian_usd_writer import (
        USD_LOOKS_PATH,
        GaussianUSDSchemaType,
        create_gaussian_writer,
    )
    from pxr import Gf, Usd, UsdGeom, UsdShade, Vt

    stage = Usd.Stage.CreateNew(str(path))
    world = UsdGeom.Xform.Define(stage, "/World")
    stage.SetDefaultPrim(world.GetPrim())
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)
    scan = UsdGeom.Xform.Define(stage, SCAN_PATH)
    scan.AddTranslateOp().Set(Gf.Vec3d(*center))

    count = len(positions)
    rotations = np.zeros((count, 4), dtype=np.float32)
    rotations[:, 0] = 1
    attributes = GaussianAttributes(
        positions=positions,
        rotations=rotations,
        scales=np.full((count, 3), diameter / 2, dtype=np.float32),
        densities=np.ones(count, dtype=np.float32),
        albedo_coefficients=colors,
    )
    capabilities = ModelCapabilities(
        has_spherical_harmonics=True,
        sh_degree=0,
        radiance_sph_O0=True,
        has_rigid_tracks=False,
        has_deformation=False,
        can_deform_positions=False,
        can_deform_rotations=False,
        can_deform_scales=False,
        has_temporal_appearance=False,
    )
    writer = create_gaussian_writer(
        GaussianUSDSchemaType.GEOM_POINTS, stage, capabilities, "lidar", 0,
        content_root_path=SCAN_PATH,
    )
    indices = torch.arange(count)
    prim = writer.create_prim(count)
    writer.write_static_attributes(attributes, indices, do_not_cast_shadows=True, force_sh_0=True)
    writer.write_first_frame_attributes(attributes, indices)

    # Keep the standard Points representation self-contained in OpenUSD viewers.
    UsdShade.MaterialBindingAPI(prim).UnbindAllBindings()
    stage.RemovePrim(USD_LOOKS_PATH)
    cloud = UsdGeom.Points(prim)
    widths = Vt.FloatArray([diameter])
    cloud.SetWidthsInterpolation(UsdGeom.Tokens.constant)
    cloud.GetWidthsAttr().Set(widths)
    radius = diameter / 2
    cloud.GetExtentAttr().Set(Vt.Vec3fArray([
        Gf.Vec3f(*(positions.min(axis=0) - radius).tolist()),
        Gf.Vec3f(*(positions.max(axis=0) + radius).tolist()),
    ]))
    stage.GetRootLayer().Save()
    return str(prim.GetPath())


def read_scene(path):
    import numpy as np
    from pxr import Usd, UsdGeom

    stage = Usd.Stage.Open(str(path))
    cloud = next(
        (UsdGeom.Points(prim) for prim in stage.Traverse() if prim.IsA(UsdGeom.Points)), None
    )
    if cloud is None or UsdGeom.GetStageUpAxis(stage) != UsdGeom.Tokens.z:
        raise ValueError("NuRec did not write the expected Z-up OpenUSD point cloud.")
    points = np.asarray(cloud.GetPointsAttr().Get())
    colors = np.asarray(cloud.GetDisplayColorPrimvar().Get())
    if points.ndim != 2 or len(points) == 0 or points.shape != colors.shape or points.shape[1] != 3:
        raise ValueError("NuRec wrote incomplete point or color data.")
    return points, colors


def select_device(min_memory_mib):
    import torch

    if not torch.version.cuda or not torch.cuda.is_available():
        raise ScanInputError("A CUDA-enabled NVIDIA GPU is required. Select a supported runtime node.")
    for index in range(torch.cuda.device_count()):
        if torch.cuda.get_device_properties(index).total_memory >= min_memory_mib * 1024**2:
            device = torch.device("cuda", index)
            torch.cuda.set_device(device)
            return device
    raise ScanInputError(f"Select a node with {min_memory_mib / 1024:g} GiB of memory on one NVIDIA GPU.")


def export(source: Path, destination: Path, summary: Path, min_memory_mib: int):
    device = select_device(min_memory_mib)
    points, colors, digest = read_scan(source)
    local, colors, center, diameter, bounds = prepare_geometry(points, colors, device=device)
    write_scene(destination, local, colors, center, diameter)
    if len(read_scene(destination)[0]) != len(points):
        raise ValueError("The OpenUSD point count differs from the scan.")
    summary.write_text(
        json.dumps({"point_count": len(points), "bounds_m": bounds, "input_sha256": digest}, allow_nan=False),
        encoding="utf-8",
    )


def project(scene: Path, destination: Path):
    """Project a bounded subset from the saved scene into a browser-friendly encoding."""
    import numpy as np

    points, colors = read_scene(scene)
    count = min(len(points), MAX_PREVIEW_POINTS)
    indices = np.linspace(0, len(points) - 1, count, dtype=np.int64)
    sampled = points[indices].astype("<f4")
    rgb = np.rint(np.clip(colors[indices], 0, 1) * 255).astype(np.uint8)
    payload = {
        "count": count,
        "positions": base64.b64encode(sampled.tobytes()).decode("ascii"),
        "colors": base64.b64encode(rgb.tobytes()).decode("ascii"),
    }
    destination.write_text(json.dumps(payload), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    convert = commands.add_parser("export")
    convert.add_argument("source", type=Path)
    convert.add_argument("scene", type=Path)
    convert.add_argument("summary", type=Path)
    convert.add_argument("--min-memory-mib", required=True, type=int)
    preview = commands.add_parser("project")
    preview.add_argument("scene", type=Path)
    preview.add_argument("projection", type=Path)
    request = parser.parse_args()
    try:
        if request.command == "export":
            export(request.source, request.scene, request.summary, request.min_memory_mib)
        else:
            project(request.scene, request.projection)
    except ScanInputError as error:
        print(str(error), flush=True)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
