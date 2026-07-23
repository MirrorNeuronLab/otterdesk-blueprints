# CCTV Operator sample inputs

`sample.mp4` is a deterministic media-processing fixture for unit tests; the
runtime does not accept it as a source. `cctv_policy.json` mirrors the default
visual targets and conservative review policy.
`steer_monitoring.json` is an example payload for the dashboard's
`steer_monitoring` live input; the idempotency key is supplied separately by
the blueprint-owned UI service.

Set an approved RTSP/RTMP URI during init review. This sample directory does
not start, map, or substitute a local stream.
