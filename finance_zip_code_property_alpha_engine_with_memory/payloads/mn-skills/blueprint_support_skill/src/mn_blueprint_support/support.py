from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from .constants import DEFAULT_BLUEPRINT_LOG_PATH


TRUE_VALUES = {"1", "true", "yes", "on", "quick", "quick_test", "test", "mock"}
LOGGER = logging.getLogger("mn.blueprint_support")


def _configure_logger() -> logging.Logger:
    LOGGER.setLevel(os.getenv("MN_LOG_LEVEL", "INFO").upper())
    LOGGER.propagate = False
    if LOGGER.handlers:
        return LOGGER

    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s [%(name)s] %(message)s"
    )
    log_path = Path(
        os.getenv(
            "MN_BLUEPRINT_LOG_PATH",
            str(DEFAULT_BLUEPRINT_LOG_PATH),
        )
    ).expanduser()
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        handler: logging.Handler = RotatingFileHandler(
            log_path,
            maxBytes=int(os.getenv("MN_LOG_MAX_BYTES", "1048576")),
            backupCount=int(os.getenv("MN_LOG_BACKUP_COUNT", "5")),
        )
    except OSError:
        handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(formatter)
    LOGGER.addHandler(handler)
    return LOGGER


logger = _configure_logger()


def quick_test_enabled(*values: Any) -> bool:
    candidates = [
        os.environ.get("MN_BLUEPRINT_QUICK_TEST", ""),
        os.environ.get("SYNAPTIC_QUICK_TEST_MODE", ""),
        *[str(value) for value in values if value is not None],
    ]
    return any(str(value).strip().lower() in TRUE_VALUES for value in candidates)


def log_status(
    blueprint: str,
    message: str,
    *,
    phase: str = "run",
    level: str = "info",
    details: dict[str, Any] | None = None,
) -> None:
    payload = {
        "ts": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "level": level,
        "blueprint": blueprint,
        "phase": phase,
        "message": message,
    }
    if details:
        payload["details"] = details
    logger.log(getattr(logging, level.upper(), logging.INFO), message, extra={"payload": payload})
    print(json.dumps(payload, sort_keys=True), file=sys.stderr)


def progress(label: str, current: int, total: int, *, width: int = 24) -> str:
    total = max(int(total), 1)
    current = min(max(int(current), 0), total)
    filled = round(width * current / total)
    bar = "#" * filled + "-" * (width - filled)
    percent = round(100 * current / total)
    return f"[{bar}] {percent:3d}% {label}"


def apply_quick_test(args: Any, overrides: dict[str, Any]) -> bool:
    enabled = bool(getattr(args, "quick_test", False)) or quick_test_enabled()
    if not enabled:
        return False
    for name, value in overrides.items():
        if hasattr(args, name):
            setattr(args, name, value)
    return True


def add_common_manifest_metadata(
    manifest: dict[str, Any],
    *,
    blueprint_id: str,
    quick_test: bool = False,
    quick_test_description: str | None = None,
) -> dict[str, Any]:
    metadata = dict(manifest.get("metadata") or {})
    metadata.update(
        {
            "blueprint_id": blueprint_id,
            "status_logging": {
                "format": "jsonl",
                "stream": "stderr",
                "env": "MN_BLUEPRINT_LOG_LEVEL",
            },
            "quick_test": {
                "enabled": bool(quick_test),
                "env": "MN_BLUEPRINT_QUICK_TEST=1",
                "description": quick_test_description
                or "Uses smaller deterministic inputs and local mock providers where external resources are optional.",
            },
            "output_contract": {
                "stdout": "single JSON object or bundle path",
                "events": "typed event objects with payload",
                "status": "sent to stderr as JSON lines",
            },
        }
    )
    manifest["metadata"] = metadata
    return manifest


def write_manifest(path: Path, manifest: dict[str, Any], *, blueprint_id: str, quick_test: bool) -> None:
    add_common_manifest_metadata(
        manifest,
        blueprint_id=blueprint_id,
        quick_test=quick_test,
    )
    path.write_text(json.dumps(manifest, indent=2) + "\n")
    log_status(
        blueprint_id,
        "manifest written",
        phase="generate",
        details={"path": str(path), "quick_test": quick_test},
    )


def emit_result(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))
