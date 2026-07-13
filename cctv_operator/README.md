# CCTV Operator

`Blueprint ID:` `cctv_operator`

`Category:` `Security`

`Runtime:` `NVIDIA-only service`

CCTV Operator replaces the former folder-oriented `safety_video_analyser` and stream-oriented `video_watch_assistant` blueprints. Give it either a local folder of recordings or one approved RTSP/RTMP stream. It samples frames with CUDA-enabled FFmpeg, performs the same review-oriented visual analysis, and writes cumulative JSON and Markdown reports.

## Source modes

- `folder`: stages a selected local folder and processes every supported `.mp4`, `.mov`, `.mkv`, `.avi`, `.webm`, `.m4v`, `.ts`, and `.mts` file in sorted order.
- `stream`: samples one reachable `rtsp://`, `rtsps://`, `rtmp://`, or `rtmps://` URI.

The default is folder mode with `examples/sample_inputs`. Set `video_source.mode`, `video_source.folder_path`, or `video_source.uri` during init review. Visual targets, alert policy, and output folder remain configurable.

## Runtime requirements

The manifest declares a hard NVIDIA CUDA requirement with one GPU and at least 49,152 MB of GPU or unified IGP memory. Eligibility, including DGX Spark unified-memory accounting, is enforced by `mn-python-sdk`; the blueprint does not duplicate that detection logic. There is no CPU or Mac-only execution path.

Frame preparation runs directly on the SDK-selected NVIDIA node through `MirrorNeuron.Runner.HostLocal`. The worker requires an FFmpeg build exposing CUDA acceleration; NVIDIA node and memory eligibility remain SDK-owned. The default Gemma 4 E2B vision model and 20-second sampling interval avoid inference backlog on one DGX Spark while remaining configurable. This keeps deployment lightweight and avoids a separate media container.

## Web UI

The blueprint uses the shared blueprint-support Gradio dashboard. The runtime injects that HostLocal dashboard service outside the blueprint communication graph, so no blueprint-specific Docker Compose service or MediaMTX bridge is required. The dashboard reads live run-store events and the generated reports; browser video preview is optional and separate from analysis.

## Run and inspect

From the catalog:

```bash
mn blueprint run cctv_operator --web-ui
```

From this folder:

```bash
mn blueprint run --folder . --web-ui
```

Inspect recent state:

```bash
mn blueprint monitor --follow
```

Primary run artifacts under `~/.mn/runs/<run_id>/` are:

- `events.jsonl`
- `cctv_report.json`
- `cctv_report.md`
- `final_artifact.json`
- `web_ui.json`

The output is decision support. A human must confirm any safety, security, access, or disciplinary response against the original recording or live stream.

## Repository validation

```bash
.venv/bin/python -m pytest -q
```

See [SPEC.md](SPEC.md) for the complete design contract.
