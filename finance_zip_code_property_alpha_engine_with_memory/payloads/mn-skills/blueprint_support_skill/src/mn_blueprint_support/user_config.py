from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .constants import DEFAULT_RUNS_ROOT, DEFAULT_USER_CONFIG_PATH, LEGACY_USER_CONFIG_PATH, STANDARD_VERSION
from .utils import deep_merge, read_json_file, utc_now_iso


@dataclass
class UserConfigStore:
    path: Path | None = None

    @property
    def resolved_path(self) -> Path:
        return user_config_path(self.path)

    def exists(self) -> bool:
        return self.resolved_path.exists() or self.read_path.exists()

    def load(self) -> dict[str, Any]:
        if not self.exists():
            return {}
        return read_json_file(self.read_path)

    def save(self, config: dict[str, Any]) -> dict[str, Any]:
        self.resolved_path.parent.mkdir(parents=True, exist_ok=True)
        self.resolved_path.write_text(json.dumps(config, indent=2, sort_keys=True) + "\n")
        return config

    def update(self, updates: dict[str, Any]) -> dict[str, Any]:
        return self.save(deep_merge(self.load(), updates))

    @property
    def read_path(self) -> Path:
        resolved = self.resolved_path
        if resolved.exists() or self.path or os.getenv("MN_CONFIG_PATH"):
            return resolved
        legacy = LEGACY_USER_CONFIG_PATH.expanduser()
        return legacy if legacy.exists() else resolved


def user_config_path(path: str | Path | None = None) -> Path:
    configured = path or os.getenv("MN_CONFIG_PATH") or DEFAULT_USER_CONFIG_PATH
    return Path(configured).expanduser()


def default_user_config() -> dict[str, Any]:
    return {
        "standard_version": STANDARD_VERSION,
        "created_at": utc_now_iso(),
        "llm": {
            "mode": "ollama",
            "model": "ollama/nemotron3:33b",
            "api_base": "http://192.168.4.173:11434",
        },
        "outputs": {
            "run_root": str(DEFAULT_RUNS_ROOT),
            "write_run_store": True,
        },
        "logging": {
            "level": "INFO",
        },
    }


def load_user_config(path: str | Path | None = None) -> dict[str, Any]:
    return UserConfigStore(path).load()


def save_user_config(config: dict[str, Any], path: str | Path | None = None) -> dict[str, Any]:
    return UserConfigStore(path).save(config)


def interactive_first_run_setup(
    path: str | Path | None = None,
    *,
    force: bool = False,
    non_interactive: bool = False,
    input_fn: Callable[[str], str] | None = None,
    output_fn: Callable[[str], None] | None = None,
    defaults: dict[str, Any] | None = None,
) -> dict[str, Any]:
    store = UserConfigStore(path)
    if store.exists() and not force:
        existing = store.load()
        existing.setdefault("setup", {})["created"] = False
        existing["setup"]["path"] = str(store.resolved_path)
        if store.read_path != store.resolved_path:
            existing["setup"]["migrated_from"] = str(store.read_path)
            return store.save(existing)
        return existing

    config = deep_merge(default_user_config(), defaults or {})
    config["setup"] = {"created": True, "path": str(store.resolved_path)}
    input_fn = input_fn or input
    output_fn = output_fn or print

    if not non_interactive:
        output_fn("MirrorNeuron first-run setup")
        config["llm"]["api_base"] = prompt_with_default(input_fn, "Ollama API base", config["llm"]["api_base"])
        config["llm"]["model"] = prompt_with_default(input_fn, "Ollama model", config["llm"]["model"])
        config["outputs"]["run_root"] = prompt_with_default(input_fn, "Run store root", config["outputs"]["run_root"])

    return store.save(config)


def prompt_with_default(input_fn: Callable[[str], str], label: str, default: str) -> str:
    response = input_fn(f"{label} [{default}]: ").strip()
    return response or default


_prompt_with_default = prompt_with_default
