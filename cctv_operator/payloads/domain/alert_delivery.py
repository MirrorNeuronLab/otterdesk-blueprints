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
