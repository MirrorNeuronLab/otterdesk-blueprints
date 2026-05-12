from __future__ import annotations

from pathlib import Path
from typing import Any

from .config import config_summary, validate_config
from .utils import read_json_file


def validate_blueprint_directory(path: str | Path) -> dict[str, Any]:
    blueprint_dir = Path(path)
    manifest_path = blueprint_dir / "manifest.json"
    config_path = blueprint_dir / "config" / "default.json"
    checks = {
        "path": str(blueprint_dir),
        "exists": blueprint_dir.exists(),
        "manifest_exists": manifest_path.exists(),
        "config_exists": config_path.exists(),
        "readme_exists": (blueprint_dir / "README.md").exists(),
        "payloads_exists": (blueprint_dir / "payloads").exists(),
        "issues": [],
    }
    if config_path.exists():
        config = read_json_file(config_path)
        checks["config_summary"] = config_summary(config)
        checks["issues"] = validate_config(config, blueprint_id=blueprint_dir.name)
    return checks
