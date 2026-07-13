# CCTV Operator specification

## Objective

Provide one reviewable video-analysis workflow for both historical recordings and live CCTV sources. The customer should be able to identify what was observed, where and when it appeared, the model confidence, why an alert was sent or suppressed, and which original source a reviewer should inspect.

## Consolidated behavior

The blueprint supersedes two narrower designs:

- The former safety analyser accepted a local video folder and produced an after-the-fact report.
- The former watch assistant sampled an RTSP feed and produced live observations, notices, and a dashboard.

`cctv_operator` preserves both input patterns and uses one event vocabulary, report format, alert policy, conversation context, and web UI.

## Source contract

`video_source.mode` is mandatory and accepts:

- `folder`: stage `video_source.folder_path`, discover supported files recursively, sort them deterministically, and advance through each recording as its duration is exhausted.
- `stream`: validate and sample one RTSP, RTSPS, RTMP, or RTMPS URI from `video_source.uri`.

Folder mode supports MP4, MOV, MKV, AVI, WebM, M4V, TS, and MTS. Stream credentials must be redacted from logs and event payloads. A missing/empty folder, unsupported source mode, invalid URI scheme, unreachable stream, decode failure, or model failure is explicit; there is no automatic switch to a demo source or CPU decoder.

## Runtime graph

`ingress` starts `video_frame_tick_source`. Each tick invokes `visual_detector`, which selects the active recording or stream, extracts one JPEG frame with NVIDIA-accelerated FFmpeg, calls the configured vision-language model, applies confidence/cooldown policy, and emits source-grounded events. `report_writer` merges each result into `cctv_report.json`, renders `cctv_report.md`, and updates `final_artifact.json`.

Folder exhaustion emits `cctv_operator_folder_completed`. Significant detections can emit `human_notice` and optional alert-delivery events. The workflow never performs physical security actions.

## NVIDIA requirement and media path

The manifest hard-requires `nvidia`, `cuda`, one NVIDIA GPU, CUDA API 12.0 or newer, and 49,152 MB or more of GPU/unified IGP memory. `mn-python-sdk` owns cluster resource validation, including DGX Spark unified-memory accounting. The blueprint only declares the requirement and does not implement another hardware probe.

The detector runs HostLocal on the selected NVIDIA node. Its launch script verifies that `nvidia-smi`, FFmpeg, and FFmpeg CUDA acceleration are available. Frame extraction requests CUDA hardware decode, performs scaling with `scale_cuda`, and downloads only the resized frame needed by the vision model. No CPU media fallback or Mac-only path exists.

This direct path is the preferred single-DGX-Spark design: it uses the node's NVIDIA media stack without adding a large DeepStream service image. DeepStream remains a future option for deployments that need batched multi-camera pipelines, tracker plugins, or high camera density.

## Web UI deployment decision

The shared `mirrorneuron-blueprint-support-skill[webui]` Gradio dashboard is used. `mn-python-sdk` injects the dashboard as a HostLocal runtime node for service manifests, so it runs outside Docker Compose and outside the domain communication graph. A blueprint-specific Compose service would duplicate lifecycle and run-store wiring.

The dashboard reads `events.jsonl`, human/log/resource streams, `cctv_report.json`, `cctv_report.md`, `final_artifact.json`, and `web_ui.json`. Browser preview is optional and disabled by default; analysis does not depend on browser republishing or MediaMTX.

## Outputs and review boundary

Every report preserves source mode, source name, recording index, sampled position or stream observation time, detections, confidence, alert records, errors, and completed recording names. The durable outputs are:

- `events.jsonl`
- `cctv_report.json`
- `cctv_report.md`
- `final_artifact.json`
- `web_ui.json`

Evaluation should measure decode reliability, frame-to-observation latency, detection precision/recall, false alerts, missed detections, cooldown correctness, source provenance, and reviewer usefulness. This is decision support, not a certified safety or security system. Human review, privacy/retention policy, camera authorization, incident-response integration, and validation on representative footage remain deployment responsibilities.
