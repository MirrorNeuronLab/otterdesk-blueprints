# CCTV Operator sample inputs

`sample.mp4` is a deterministic media-processing fixture for unit tests; the
runtime does not accept it as a source. `cctv_policy.json` mirrors the default
visual targets and conservative review policy.
`steer_monitoring.json` is an example payload for the dashboard's
`steer_monitoring` live input; the idempotency key is supplied separately by
the blueprint-owned UI service.

Set an approved RTSP/RTMP URI during init review. This sample directory does
not automatically start, map, or substitute a local stream. On a test host
with Docker, FFmpeg, FFprobe, and curl installed, publish `sample.mp4` as a
looping RTSP stream and expose MediaMTX's HLS proxy with:

```bash
./cctv_operator/scripts/sample_rtsp.sh start
./cctv_operator/scripts/sample_rtsp.sh status
./cctv_operator/scripts/sample_rtsp.sh stop
```

The start command prints the host-reachable RTSP URI for `video_source.uri`,
the browser-safe HLS URL for `web_ui.preview.url`, and a complete run command.
Set `CCTV_SAMPLE_RTSP_HOST` when the automatically detected host address is not
reachable from either the blueprint's DockerWorker or the operator's browser.
Use `CCTV_SAMPLE_HLS_PORT` to change the default HLS port `8888`.
