"""Existing optional Slack destination adapter shared by both alert lanes."""

import os
import json
import urllib.request
from typing import Any

def post_slack(
    text: str,
    *,
    enabled: bool | None = None,
) -> tuple[str, dict[str, Any]]:
    if enabled is None:
        enabled = os.environ.get(
            "SLACK_ALERT_ENABLED", "false"
        ).strip().lower() in {"1", "true", "yes", "on"}
    token = os.environ.get("MN_SLACK_BOT_TOKEN") or os.environ.get("SLACK_BOT_TOKEN")
    channel = os.environ.get("MN_SLACK_DEFAULT_CHANNEL") or os.environ.get("SLACK_DEFAULT_CHANNEL")
    if not enabled:
        return "skipped", {"reason": "slack_disabled", "channel": channel}
    if not token:
        return "skipped", {"reason": "missing_slack_bot_token", "channel": channel}
    if not channel:
        return "skipped", {"reason": "missing_slack_channel", "channel": channel}

    api_url = os.environ.get("MN_SLACK_API_BASE_URL") or os.environ.get("SLACK_API_BASE_URL") or "https://slack.com/api/chat.postMessage"
    payload = {"channel": channel, "text": text}
    request = urllib.request.Request(
        api_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        body = json.loads(response.read().decode("utf-8"))
    if body.get("ok") is True:
        return "sent", {"channel": channel, "ts": body.get("ts")}
    return "error", {"channel": channel, "error": body.get("error", "unknown_slack_error")}


def alert_text(camera_id: str, detection: dict[str, Any], frame_seq: int, source_uri: str) -> str:
    prefix = os.environ.get("SLACK_MESSAGE_PREFIX", "Video detection alert")
    detections = detection.get("detections") or []
    detection_lines = []
    for index, item in enumerate(detections[:8], start=1):
        detection_lines.append(
            f"{index}. {item.get('color', 'unknown')} {item.get('label', 'observed item')} - "
            f"{item.get('position') or 'position unclear'}; {item.get('activity') or 'activity unclear'}"
        )
    detection_text = "\n".join(detection_lines) if detection_lines else "No per-detection details reported."
    description = detection.get("detection_report") or detection["summary"]
    activity = detection.get("activity_description") or "Activity not clearly visible."
    return (
        f"{prefix}: {detection.get('detection_count', 0)} configured target(s) observed on {camera_id}\n"
        f"Confidence: {detection['confidence']:.2f} | Risk: {detection['risk_level']} | Frame: {frame_seq}\n"
        f"{description}\n"
        f"Activity: {activity}\n"
        f"Detection details:\n{detection_text}\n"
        f"Source: {source_uri}"
    )
