from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterator, TypeVar
import hashlib
import os
import re
import tempfile
import time

try:
    import fcntl
except ImportError:  # pragma: no cover - non-Unix fallback
    fcntl = None


T = TypeVar("T")


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        return default


def normalize_rate_limit_key(key: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(key or "external").strip())
    normalized = normalized.strip("._-") or "external"
    digest = hashlib.sha1(str(key).encode("utf-8")).hexdigest()[:10]
    return f"{normalized[:80]}_{digest}"


@dataclass(frozen=True)
class ExternalRateLimitConfig:
    key: str
    min_interval_seconds: float
    state_dir: Path
    disabled: bool = False

    @classmethod
    def from_env(
        cls,
        key: str,
        *,
        min_interval_seconds: float | None = None,
    ) -> "ExternalRateLimitConfig":
        normalized_key = normalize_rate_limit_key(key)
        env_key = re.sub(r"[^A-Za-z0-9]+", "_", str(key).upper()).strip("_")
        specific = os.environ.get(f"MN_EXTERNAL_RATE_LIMIT_{env_key}_SECONDS")
        fallback = os.environ.get("MN_EXTERNAL_RATE_LIMIT_DEFAULT_SECONDS")
        interval = (
            min_interval_seconds
            if min_interval_seconds is not None
            else _float_env("MN_EXTERNAL_RATE_LIMIT_DEFAULT_SECONDS", 0.5)
        )
        if fallback is not None:
            interval = _float_env("MN_EXTERNAL_RATE_LIMIT_DEFAULT_SECONDS", interval)
        if specific is not None:
            interval = _float_env(f"MN_EXTERNAL_RATE_LIMIT_{env_key}_SECONDS", interval)
        return cls(
            key=normalized_key,
            min_interval_seconds=max(float(interval), 0.0),
            state_dir=Path(
                os.environ.get(
                    "MN_EXTERNAL_RATE_LIMIT_STATE_DIR",
                    str(Path(tempfile.gettempdir()) / "mn_external_rate_limits"),
                )
            ),
            disabled=_truthy(os.environ.get("MN_EXTERNAL_RATE_LIMIT_DISABLED")),
        )


@contextmanager
def _locked_file(path: Path) -> Iterator[Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+", encoding="utf-8") as handle:
        if fcntl is not None:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield handle
        finally:
            if fcntl is not None:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def throttle(
    key: str,
    *,
    min_interval_seconds: float | None = None,
    sleep: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    """Wait until the rate-limit key is eligible for another external call."""

    config = ExternalRateLimitConfig.from_env(
        key,
        min_interval_seconds=min_interval_seconds,
    )
    if config.disabled or config.min_interval_seconds <= 0:
        return {"status": "disabled", "key": config.key, "slept_seconds": 0.0}

    state_path = config.state_dir / f"{config.key}.state"
    lock_path = config.state_dir / f"{config.key}.lock"
    with _locked_file(lock_path):
        now = monotonic()
        last_call = 0.0
        try:
            raw_last_call = state_path.read_text(encoding="utf-8").strip()
            if raw_last_call:
                last_call = float(raw_last_call)
        except (OSError, ValueError):
            last_call = 0.0

        elapsed = now - last_call
        wait_seconds = max(config.min_interval_seconds - elapsed, 0.0)
        if wait_seconds > 0:
            sleep(wait_seconds)
            now = monotonic()

        state_path.write_text(f"{now:.9f}", encoding="utf-8")

    return {
        "status": "ok",
        "key": config.key,
        "slept_seconds": wait_seconds,
        "min_interval_seconds": config.min_interval_seconds,
    }


def call_with_rate_limit(
    key: str,
    func: Callable[..., T],
    *args: Any,
    rate_limit_min_interval_seconds: float | None = None,
    **kwargs: Any,
) -> T:
    throttle(key, min_interval_seconds=rate_limit_min_interval_seconds)
    return func(*args, **kwargs)


def rate_limited(
    key: str,
    *,
    min_interval_seconds: float | None = None,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        def wrapper(*args: Any, **kwargs: Any) -> T:
            return call_with_rate_limit(
                key,
                func,
                *args,
                rate_limit_min_interval_seconds=min_interval_seconds,
                **kwargs,
            )

        return wrapper

    return decorator


def wrap_urlopen(
    key: str,
    urlopen: Callable[..., T],
    *,
    min_interval_seconds: float | None = None,
) -> Callable[..., T]:
    def wrapper(*args: Any, **kwargs: Any) -> T:
        return call_with_rate_limit(
            key,
            urlopen,
            *args,
            rate_limit_min_interval_seconds=min_interval_seconds,
            **kwargs,
        )

    return wrapper
