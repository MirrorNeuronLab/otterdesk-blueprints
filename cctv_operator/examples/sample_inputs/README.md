# CCTV Operator sample inputs

`cctv_policy.json` illustrates the optional recorded-demo source, visual targets,
and conservative review policy. It does not select the default live input.
`steer_monitoring.json` is an example payload for the dashboard's
`steer_monitoring` live input; the idempotency key is supplied separately by
the blueprint-owned UI service.

The default input is the live retail RTSP stream in `config/default.json`.
Run it without a local video file:

```bash
mn blueprint run ./cctv_operator --web-ui
```

The stream must be reachable from the NVIDIA worker. No host-side FFmpeg,
FFprobe, MediaMTX process or helper container is needed. Use OtterDesk's secure
source field to configure another approved RTSP/RTMP stream.

For recorded playback, explicitly set `video_source.profile=bundled_demo`,
`video_source.uri=rtsp://127.0.0.1:8554/cctv-demo` and `video_source.demo_file`
to an approved MP4 on the submitting computer. The SDK stages that file; the
stream-generation tools in `payloads/docker_worker/demo/` run in the NVIDIA worker.
