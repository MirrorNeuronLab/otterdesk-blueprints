from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def blueprint_library_roots() -> list[Path]:
    roots: list[Path] = []
    env_value = os.environ.get("MN_BLUEPRINT_LIBRARY_PATH", "")
    for raw in env_value.split(os.pathsep):
        if raw.strip():
            roots.append(Path(raw).expanduser())

    cwd = Path.cwd().resolve()
    for parent in (cwd, *cwd.parents):
        roots.extend([parent, parent / "mn-blueprints"])

    module_path = Path(__file__).resolve()
    for parent in module_path.parents:
        roots.extend([parent, parent / "mn-blueprints"])

    roots.append(Path("~/.mn/blueprints").expanduser())

    unique: list[Path] = []
    seen: set[Path] = set()
    for root in roots:
        try:
            resolved = root.resolve()
        except OSError:
            resolved = root
        if resolved in seen or not resolved.exists() or not resolved.is_dir():
            continue
        if not _looks_like_blueprint_root(resolved):
            continue
        seen.add(resolved)
        unique.append(resolved)
    return unique


def load_blueprint_json_files(filename: str) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for root in blueprint_library_roots():
        for path in sorted(root.glob(f"*/{filename}")):
            try:
                payload = _read_json_object(path)
            except (OSError, ValueError, json.JSONDecodeError):
                continue
            blueprint_id = str(payload.get("blueprint_id") or path.parent.name)
            records.setdefault(blueprint_id, payload)
    return records


def load_blueprint_index_products() -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for root in blueprint_library_roots():
        index_path = root / "index.json"
        if not index_path.exists():
            continue
        try:
            entries = json.loads(index_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            blueprint_id = str(entry.get("id") or entry.get("path") or "")
            product = entry.get("product")
            if not blueprint_id or not isinstance(product, dict):
                continue
            profile = dict(product)
            profile.setdefault("blueprint_id", blueprint_id)
            profile.setdefault("title", entry.get("name") or blueprint_id)
            profile.setdefault("one_line", entry.get("description") or "")
            records.setdefault(blueprint_id, profile)
    return records


def load_blueprint_json(blueprint_id: str, filename: str) -> dict[str, Any] | None:
    env_name = f"MN_BLUEPRINT_{filename.removesuffix('.json').upper()}_JSON"
    env_payload = os.environ.get(env_name)
    if env_payload:
        decoded = json.loads(env_payload)
        if not isinstance(decoded, dict):
            raise ValueError(f"{env_name} must decode to a JSON object")
        if not decoded.get("blueprint_id") or decoded.get("blueprint_id") == blueprint_id:
            return decoded

    for root in blueprint_library_roots():
        path = root / blueprint_id / filename
        if path.exists():
            return _read_json_object(path)
    return None


def load_renamed_blueprints() -> dict[str, tuple[str, str]]:
    for root in blueprint_library_roots():
        path = root / "renamed_blueprints.json"
        if path.exists():
            raw = _read_json_object(path)
            return {
                str(old): (str(value[0]), str(value[1]))
                for old, value in raw.items()
                if isinstance(value, (list, tuple)) and len(value) == 2
            }
    return {}


def _read_json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _looks_like_blueprint_root(root: Path) -> bool:
    if (root / "index.json").exists() or (root / "renamed_blueprints.json").exists():
        return True
    try:
        for child in root.iterdir():
            if child.is_dir() and ((child / "manifest.json").exists() or (child / "scenario.json").exists()):
                return True
    except OSError:
        return False
    return False
