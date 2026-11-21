# LiDAR scene builder

Choose the included synthetic street corner or upload one registered PLY
point cloud with Z up and coordinates in metres. Start a run on a Linux
x86-64 MirrorNeuron node with a supported NVIDIA CUDA GPU and at least
48 GiB of GPU memory.

Open **LiDAR scene preview** after conversion. Drag or use the arrow keys
to rotate, use the scroll wheel or zoom buttons to magnify, and choose
**Top view** for the overhead view. Choose **Reset view** to return to the
starting angle.

Open `scene.usdc` in an OpenUSD viewer for the complete scan. Use
`scan_result.json` to check source and output digests, count and bounds.
The web preview is a bounded view of the saved scene.

The co-worker uses the NVIDIA NuRec OpenUSD exporter with registered geometry.
The scan must already be registered. Photorealistic NuRec training requires
calibrated sensor recordings and poses.

[Conversation guide](conversation_guide.md)
