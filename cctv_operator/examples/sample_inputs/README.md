# CCTV Operator sample inputs

`cctv_policy.json` mirrors the default bundled-demo source, visual targets, and
conservative review policy.
`steer_monitoring.json` is an example payload for the dashboard's
`steer_monitoring` live input; the idempotency key is supplied separately by
the blueprint-owned UI service.

The deterministic MP4 fixture and stream-generation tools live in
`payloads/docker_worker/demo/`. They are built into the shared NVIDIA worker,
not accepted as file input. Run the no-config demo directly with:

```bash
mn blueprint run ./cctv_operator --web-ui
```

No host-side FFmpeg, FFprobe, MediaMTX process, helper container, or external
CCTV URL is needed. Set `video_source.profile=external` only when intentionally
switching to a real approved RTSP/RTMP source.
