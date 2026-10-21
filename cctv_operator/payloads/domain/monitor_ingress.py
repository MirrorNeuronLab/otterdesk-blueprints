"""Validate a camera start or forward an approved monitoring command."""
from .source_validation import validate_source


def process(block, work):
    payload = work["payload"]
    message_type = payload.get("type") or work.get("event_type") or "cctv_operator_start"
    if message_type == "init":
        message_type = "cctv_operator_start"
    if message_type not in {"cctv_operator_start", "cctv_operator_steer"}:
        raise ValueError("Unsupported CCTV monitoring command")
    body = payload.get("payload") if isinstance(payload.get("payload"), dict) else payload
    state = dict(work["state"])
    if message_type == "cctv_operator_start":
        state.update(stream_session={"status": "ready", "stream_id": str(body.get("stream_id") or "cctv_operator")},
            validation=validate_source(block.config))
    block.check()
    return {"state": state, "outputs": state,
        "emissions": [{"port": "steer" if message_type == "cctv_operator_steer" else "start", "value": body}],
        "events": [{"type": "video_monitor_start", "payload": {"message_type": message_type, "status": "ready"}}]}
