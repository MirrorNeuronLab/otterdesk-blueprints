"""Validated camera and NVIDIA streaming settings; credentials stay private."""

import hashlib
from urllib.parse import urlsplit, urlunsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator


DEFAULT_PROMPT = (
    "Describe the visible scene and actions in 1–2 concise sentences. "
    "Focus on people, vehicles, movement, and changes. "
    "Only describe what is clearly visible; say when something is uncertain."
)


class CameraSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    uri: str = Field(min_length=8, max_length=2048, repr=False, exclude=True)
    name: str = Field(default="Camera", min_length=1, max_length=120)
    prompt: str = Field(default=DEFAULT_PROMPT, min_length=1, max_length=4000)
    chunk_duration: int = Field(default=4, ge=2, le=30)
    frames_per_chunk: int = Field(default=8, ge=2, le=16)
    max_tokens: int = Field(default=192, ge=64, le=512)
    caption_timeout_seconds: int = Field(default=120, ge=30, le=600)

    @field_validator("uri")
    @classmethod
    def camera_address(cls, value):
        value = value.strip()
        if any(ord(char) < 32 or ord(char) == 127 for char in value):
            raise ValueError("Camera addresses cannot contain control characters.")
        try:
            parts = urlsplit(value)
            if parts.scheme not in {"rtsp", "rtsps"} or not parts.hostname or parts.fragment:
                raise ValueError()
            parts.port
        except ValueError:
            raise ValueError("Enter a valid rtsp:// or rtsps:// camera address.") from None
        return value

    @field_validator("prompt", "name")
    @classmethod
    def visible_text(cls, value):
        if not value.strip() or "\x00" in value:
            raise ValueError("Enter nonempty text without null characters.")
        return value.strip()

    @property
    def source_id(self):
        parts = urlsplit(self.uri)
        # A query can select a different camera. Hash it without ever publishing
        # the locator; credential rotation in userinfo keeps the same identity.
        locator = urlunsplit((parts.scheme, parts.netloc.rsplit("@", 1)[-1], parts.path, parts.query, ""))
        return hashlib.sha256(locator.encode()).hexdigest()


def camera_settings(config):
    source = config.get("video_source") or {}
    analysis = config.get("analysis") or {}
    try:
        return CameraSettings(
            uri=source.get("uri", ""), name=source.get("name", "Camera"),
            prompt=(config.get("inputs", {}).get("payload", {}).get("monitoring_goal") or DEFAULT_PROMPT),
            **analysis,
        )
    except ValueError:
        # Pydantic errors contain their input. Never propagate a camera credential.
        raise ValueError("Couldn't configure camera analysis. Check the secure stream URL and analysis settings.") from None


def service_url(value):
    try:
        parts = urlsplit(value)
        if (parts.scheme not in {"http", "https"} or not parts.hostname or parts.username
                or parts.password or parts.query or parts.fragment or parts.path not in {"", "/"}
                or any(ord(char) < 33 for char in value)):
            raise ValueError()
        parts.port
        return value.rstrip("/")
    except (TypeError, ValueError):
        raise ValueError("Configure an HTTP(S) NVIDIA VLM origin without credentials or a path.") from None
