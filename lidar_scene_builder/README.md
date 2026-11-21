# LiDAR scene builder

Convert a registered SLIM LiDAR point cloud to a portable OpenUSD scene with
the NVIDIA Omniverse NuRec 26.10 exporter. Open the run’s web preview to rotate,
zoom, or inspect the scene from above.

## Try the sample

In OtterDesk, hire **LiDAR scene builder** from the local blueprint catalog,
choose the sample, and start the co-worker. The bundled PLY shows a synthetic
street corner with two building façades, a raised sidewalk and posts.
It contains only synthetic geometry.

You can also run the same blueprint using `mn` from the catalog checkout.

```sh
mn blueprint run ./lidar_scene_builder --follow-seconds 0
```

To replace the sample, choose a registered point cloud in Configure or pass
`--set inputs.payload.scan_file=/absolute/path/to/scan.ply`. Use PLY 1.0
with scalar `x`, `y`, and `z` vertex properties, Z up and units in metres.
The input accepts ASCII or binary PLY with up to 1 million points and
256 MiB. Export the registered map from your mapping tool as PLY first if it
stores the points in another format.

## Run and review

The co-worker runs on Linux x86-64 under Docker with the NVIDIA Container
Toolkit, driver R580 or later, and one supported CUDA-capable NVIDIA GPU with
at least 48 GiB of GPU memory. Worker preparation pulls the pinned NuRec image
from NGC and installs the Ubuntu Python environment for MirrorNeuron.
Use a connected node that meets these requirements when the desktop uses
macOS or Windows.

Each run saves these files under `~/Downloads/lidar-scene-builder/run_<timestamp>/`
when output export is enabled:

| File | Use |
| --- | --- |
| `scene.usdc` | Open in Omniverse or another OpenUSD viewer. The Z-up, metre-scale stage contains every registered point. |
| `scan_result.json` | Verify the source SHA-256, output digest, point count and bounds. |
| `web/index.html` | Open locally or through the co-worker’s **LiDAR scene preview**. It uses the saved USD point positions and colors and shows up to 20,000 points. |

This workflow exports geometry using NuRec’s Gaussian USD writer. It keeps
source 8-bit vertex RGB when available and uses elevation colors for uncolored
scans. The output represents registered geometry. A photorealistic
reconstruction with NuRec training requires sensor sequences, calibration,
and poses. The browser preview and conversion use the selected MirrorNeuron
node’s local data boundary.

[NVIDIA NuRec documentation](https://docs.nvidia.com/nurec/) ·
[SLIM research project](https://github.com/HKUST-Aerial-Robotics/SLIM)
