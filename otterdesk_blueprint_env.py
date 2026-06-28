from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Iterable


ENV_ALIASES = {
    "dev": "development",
    "develop": "development",
    "development": "development",
    "local": "development",
    "prod": "production",
    "production": "production",
}


def load_blueprint_env(start: str | Path | None = None) -> dict[str, str]:
    """Load repo-level .env files without overriding real environment values."""

    root = find_repo_root(start)
    if root is None:
        return {"loaded": "", "env": normalized_env(os.environ.get("MN_ENV"))}

    protected = set(os.environ)
    loaded: list[str] = []
    base_env = root / ".env"
    if load_env_file(base_env, protected=protected):
        loaded.append(str(base_env))

    env_name = normalized_env(os.environ.get("MN_ENV"))
    env_file = root / f".env.{env_name}"
    if load_env_file(env_file, protected=protected):
        loaded.append(str(env_file))

    if env_name == "development":
        local_env = root / ".env.local"
        if load_env_file(local_env, protected=protected):
            loaded.append(str(local_env))

    os.environ.setdefault("MN_ENV", env_name)
    return {"loaded": os.pathsep.join(loaded), "env": env_name}


def local_development_enabled() -> bool:
    return normalized_env(os.environ.get("MN_ENV")) == "development"


def normalized_env(value: str | None) -> str:
    return ENV_ALIASES.get(str(value or "").strip().lower(), "production")


def find_repo_root(start: str | Path | None = None) -> Path | None:
    candidates: Iterable[Path]
    if start is None:
        candidates = [Path.cwd()]
    else:
        path = Path(start).expanduser()
        candidates = [path if path.is_dir() else path.parent]
    for candidate in candidates:
        for parent in (candidate, *candidate.parents):
            if (parent / "otterdesk_blueprint_env.py").exists() and (parent / "AGENTS.md").exists():
                return parent
    return None


def load_env_file(path: Path, *, protected: set[str]) -> bool:
    if not path.is_file():
        return False
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        parsed = parse_env_line(raw_line)
        if parsed is None:
            continue
        key, value = parsed
        if key not in protected:
            os.environ[key] = value
    return True


def parse_env_line(line: str) -> tuple[str, str] | None:
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return None
    if stripped.startswith("export "):
        stripped = stripped[len("export "):].lstrip()
    if "=" not in stripped:
        return None
    key, value = stripped.split("=", 1)
    key = key.strip()
    if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", key):
        return None
    return key, unquote_env_value(value.strip())


def unquote_env_value(value: str) -> str:
    quoted = len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1]
    if "#" in value and not quoted:
        value = value.split("#", 1)[0].rstrip()
    return value
