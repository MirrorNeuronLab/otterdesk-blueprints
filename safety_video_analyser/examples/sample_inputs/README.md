# Safety Video Demo Inputs

This folder contains a tiny generated demo video for launch validation and local product demos.

Replace `worksite_safety_walkthrough.mp4` with real site footage before using the blueprint for an operational review. The workflow treats files in this folder as internal evidence, stages them by BlobRef, writes `video_analysis.json`, and then writes the human-review report artifacts listed in the manifest output contract.

The demo clip is intentionally short and low detail so it can live in the blueprint repository without adding a large media payload.
