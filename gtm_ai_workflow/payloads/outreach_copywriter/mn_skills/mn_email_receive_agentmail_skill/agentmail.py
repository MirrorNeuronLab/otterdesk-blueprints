from __future__ import annotations

from dataclasses import dataclass
import json
import os
import urllib.parse
import urllib.request
from typing import Any, Callable


UrlOpen = Callable[..., Any]


@dataclass(frozen=True)
class AgentMailReceiveConfig:
    api_key: str
    inbox_id: str
    api_base_url: str = "https://api.agentmail.to"
    timeout_seconds: int = 30

    @classmethod
    def from_env(cls) -> "AgentMailReceiveConfig":
        return cls(
            api_key=os.environ.get("AGENTMAIL_API_KEY", "").strip(),
            inbox_id=os.environ.get("AGENTMAIL_INBOX", "").strip(),
            api_base_url=os.environ.get("AGENTMAIL_API_BASE_URL", "https://api.agentmail.to").rstrip("/"),
        )


@dataclass(frozen=True)
class AgentMailMessage:
    message_id: str
    from_email: str
    subject: str
    text: str = ""
    extracted_text: str = ""


def _inbox_path(config: AgentMailReceiveConfig) -> str:
    return urllib.parse.quote(config.inbox_id, safe="")


def _message_path(message_id: str) -> str:
    return urllib.parse.quote(message_id, safe="")


def _request(
    method: str,
    path: str,
    config: AgentMailReceiveConfig,
    *,
    body: dict[str, Any] | None = None,
    query: dict[str, Any] | None = None,
    urlopen: UrlOpen = urllib.request.urlopen,
) -> dict[str, Any]:
    if not config.api_key or not config.inbox_id:
        return {}
    url = config.api_base_url.rstrip("/") + path
    if query:
        url += "?" + urllib.parse.urlencode(query, doseq=True)
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"Bearer {config.api_key}",
            "Content-Type": "application/json; charset=utf-8",
        },
        method=method,
    )
    with urlopen(request, timeout=config.timeout_seconds) as response:
        raw = response.read().decode("utf-8")
        return json.loads(raw) if raw else {}


def normalize_message(payload: dict[str, Any]) -> AgentMailMessage:
    return AgentMailMessage(
        message_id=str(payload.get("message_id") or payload.get("id") or ""),
        from_email=str(payload.get("from") or payload.get("from_") or ""),
        subject=str(payload.get("subject") or ""),
        text=str(payload.get("text") or ""),
        extracted_text=str(payload.get("extracted_text") or ""),
    )


def list_unread_messages(
    config: AgentMailReceiveConfig | None = None,
    *,
    urlopen: UrlOpen = urllib.request.urlopen,
) -> list[AgentMailMessage]:
    config = config or AgentMailReceiveConfig.from_env()
    if not config.api_key or not config.inbox_id:
        return []
    payload = _request(
        "GET",
        f"/v0/inboxes/{_inbox_path(config)}/messages",
        config,
        query={"labels": ["unread"]},
        urlopen=urlopen,
    )
    messages = payload.get("messages") or payload.get("data") or []
    return [normalize_message(message) for message in messages]


def get_message(
    message_id: str,
    config: AgentMailReceiveConfig | None = None,
    *,
    urlopen: UrlOpen = urllib.request.urlopen,
) -> AgentMailMessage:
    config = config or AgentMailReceiveConfig.from_env()
    payload = _request(
        "GET",
        f"/v0/inboxes/{_inbox_path(config)}/messages/{_message_path(message_id)}",
        config,
        urlopen=urlopen,
    )
    return normalize_message(payload)


def mark_read(
    message_id: str,
    config: AgentMailReceiveConfig | None = None,
    *,
    urlopen: UrlOpen = urllib.request.urlopen,
) -> dict[str, Any]:
    config = config or AgentMailReceiveConfig.from_env()
    return _request(
        "PATCH",
        f"/v0/inboxes/{_inbox_path(config)}/messages/{_message_path(message_id)}",
        config,
        body={"add_labels": ["read"], "remove_labels": ["unread"]},
        urlopen=urlopen,
    )


def send_reply(
    to_email: str,
    subject: str,
    text: str,
    config: AgentMailReceiveConfig | None = None,
    *,
    urlopen: UrlOpen = urllib.request.urlopen,
) -> dict[str, Any]:
    config = config or AgentMailReceiveConfig.from_env()
    return _request(
        "POST",
        f"/v0/inboxes/{_inbox_path(config)}/messages/send",
        config,
        body={"to": to_email, "subject": subject, "text": text},
        urlopen=urlopen,
    )
