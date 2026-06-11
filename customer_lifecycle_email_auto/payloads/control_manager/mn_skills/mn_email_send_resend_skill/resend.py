from __future__ import annotations

from dataclasses import dataclass
import json
import os
import urllib.error
import urllib.request
from typing import Any, Callable


UrlOpen = Callable[..., Any]


@dataclass(frozen=True)
class ResendSendConfig:
    api_key: str
    from_email: str
    api_base_url: str = "https://api.resend.com"
    timeout_seconds: int = 30

    @classmethod
    def from_env(cls) -> "ResendSendConfig":
        return cls(
            api_key=os.environ.get("RESEND_API_KEY", "").strip(),
            from_email=os.environ.get("RESEND_FROM_EMAIL", "").strip(),
            api_base_url=os.environ.get("RESEND_API_BASE_URL", "https://api.resend.com").rstrip("/"),
        )


def dry_run_email(request: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "sent",
        "provider_id": "dry_run",
        "http_status": 200,
        "dry_run": True,
    }


def _recipients(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [item.strip() for item in value.split(",") if item.strip()]
    return []


def send_resend_email(
    request: dict[str, Any],
    config: ResendSendConfig | None = None,
    *,
    urlopen: UrlOpen = urllib.request.urlopen,
) -> dict[str, Any]:
    config = config or ResendSendConfig.from_env()
    if not config.api_key or not config.from_email:
        return {"status": "skipped", "reason": "missing_resend_credentials"}

    body = json.dumps(
        {
            "from": config.from_email,
            "to": _recipients(request.get("to", [])),
            "subject": request.get("subject", ""),
            "text": request.get("text", ""),
            "html": request.get("html", None),
            "headers": request.get("headers", {}),
        }
    ).encode("utf-8")
    http_request = urllib.request.Request(
        f"{config.api_base_url}/emails",
        data=body,
        headers={
            "Authorization": f"Bearer {config.api_key}",
            "Content-Type": "application/json; charset=utf-8",
            "Accept": "application/json",
            "User-Agent": "mn-email-send-resend-skill/0.1.0",
        },
        method="POST",
    )

    try:
        with urlopen(http_request, timeout=config.timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return {
            "status": "sent",
            "provider_id": payload.get("id"),
            "http_status": response.status,
        }
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        return {"status": "failed", "http_status": exc.code, "error": raw}
    except urllib.error.URLError as exc:
        return {"status": "failed", "error": str(exc)}
