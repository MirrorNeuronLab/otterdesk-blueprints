# LiDAR scene builder specification

## Goal

Export a registered SLIM LiDAR map as inspectable OpenUSD, including a small
synthetic sample for the normal input path. The co-worker runs once per
supervisor request and publishes a run-scoped scene, receipt and web preview.

## Input and processing

Accept one registered PLY 1.0 with 1 to 1 million finite points, at most
256 MiB. Assume right-handed, Z-up metre coordinates. Keep every position
and preserve the registered world offset using a double-precision USD
translation and local float coordinates. Keep 8-bit vertex RGB when present.
Assign display color by elevation for uncolored scans.

MirrorNeuron stages the input and admits a Docker worker on Linux x86-64
with at least one CUDA-capable NVIDIA GPU and 49,152 MiB of GPU memory on one
device. The pinned NuRec 26.10 runtime prepares point attributes with CUDA.
NuRec’s `GaussianGeomPointsWriter` writes the standard `UsdGeom.Points`
representation. Output contains no external material references and does
not require a trained checkpoint.

## Acceptance

- Reject empty, incomplete, non-finite, oversized and unsupported point clouds.
- Reopen the saved scene and verify its point count and Z-up stage.
- Publish `scene.usdc` and a receipt with source and output digests before
  publishing the UI. Keep the scene available if the UI fails.
- Build the web projection from the saved OpenUSD scene. The page displays up
  to 20,000 points, reports the sample and full counts, runs offline, and has
  pointer and keyboard orbit controls.
- Run the same workflow for the bundled sample and for a supplied PLY.

The package handles conversion of an already registered point cloud.
SLIM mapping itself, sensor registration, surfaces inferred from gaps, and
neural training from a calibrated NCore recording are outside this workflow.
