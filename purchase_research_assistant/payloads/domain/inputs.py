"""Purchase-input normalization, path resolution, and local document intake."""

from __future__ import annotations

import copy
import inspect
import os
from pathlib import Path
from typing import Any, Callable

from .common import DEFAULT_OUTPUT_FOLDER, PURCHASE_TYPES, SUPPORTED_SUFFIXES, TEXT_SUFFIXES, _sha256

try:
    from mn_llm_ocr_skill import extract_document
except Exception:  # pragma: no cover - optional runtime skill
    extract_document = None


def normalize_inputs(inputs: dict[str, Any] | None) -> dict[str, Any]:
    payload = copy.deepcopy(inputs or {})
    purchase_type = str(payload.get("purchase_type") or payload.get("category") or "custom").strip().lower()
    aliases = {"vehicle": "car", "automobile": "car", "flight": "airline_ticket", "ticket": "airline_ticket", "rental": "rental_property"}
    payload["purchase_type"] = aliases.get(purchase_type, purchase_type if purchase_type in PURCHASE_TYPES else "custom")
    payload["item_description"] = str(payload.get("item_description") or payload.get("query") or "").strip()
    payload["budget"] = payload.get("budget", payload.get("price_ceiling"))
    payload["location"] = str(payload.get("location") or "").strip()
    payload["route"] = str(payload.get("route") or "").strip()
    payload["travel_dates"] = payload.get("travel_dates") or payload.get("dates") or ""
    payload["priorities"] = _as_list(payload.get("priorities"))
    payload["constraints"] = payload.get("constraints") if isinstance(payload.get("constraints"), dict) else {}
    payload["input_folder"] = str(payload.get("input_folder") or "").strip()
    payload["output_folder"] = str(payload.get("output_folder") or DEFAULT_OUTPUT_FOLDER).strip()
    payload["research_mode"] = str(payload.get("research_mode") or "local_rag_and_public_web")
    return payload


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value)]


def resolve_input_folder(config: dict[str, Any], inputs: dict[str, Any], root: Path) -> Path | None:
    value = inputs.get("input_folder") or (config.get("inputs") or {}).get("payload", {}).get("input_folder")
    if not value:
        return None
    path = expand_runtime_path(value)
    if not path.is_absolute():
        path = root / path
    return path


def _looks_like_sandbox_home(path: Path) -> bool:
    raw = str(path)
    return raw in {"/root", "/tmp", "/var/root"} or raw.startswith(
        ("/root/", "/tmp/", "/private/tmp/", "/var/root/", "/var/folders/", "/private/var/folders/")
    )


def _home_from_mirror_neuron_path(value: str | Path | None) -> Path | None:
    if not value:
        return None
    path = Path(value).expanduser()
    parts = path.parts
    if ".mn" not in parts:
        return None
    marker_index = parts.index(".mn")
    if marker_index <= 0:
        return None
    home = Path(*parts[:marker_index])
    return home if str(home) and not _looks_like_sandbox_home(home) else None


def _home_from_macos_users_dir() -> Path | None:
    users_dir = Path("/Users")
    if not users_dir.exists():
        return None
    names = [os.environ.get("SUDO_USER"), os.environ.get("LOGNAME"), os.environ.get("USER")]
    for name in names:
        if not name or name in {"root", "daemon", "nobody"}:
            continue
        candidate = users_dir / name
        if candidate.exists() and not _looks_like_sandbox_home(candidate):
            return candidate
    candidates = [
        path
        for path in users_dir.iterdir()
        if path.is_dir()
        and path.name not in {"Shared", "Guest", "Deleted Users"}
        and not path.name.startswith(".")
        and ((path / "Downloads").exists() or (path / ".mn").exists())
    ]
    if len(candidates) == 1 and not _looks_like_sandbox_home(candidates[0]):
        return candidates[0]
    return None


def runtime_user_home() -> Path:
    for env_name in ("MN_OUTPUT_HOME", "MN_USER_HOME", "OTTERDESK_USER_HOME"):
        value = os.environ.get(env_name)
        if value:
            return Path(value).expanduser()
    for env_name in ("MN_RUN_DIR", "MN_RUNS_ROOT", "MN_HOME", "OTTERDESK_RUN_DIR", "OTTERDESK_RUNS_ROOT"):
        home = _home_from_mirror_neuron_path(os.environ.get(env_name))
        if home:
            return home
    expanded = Path("~").expanduser()
    if not _looks_like_sandbox_home(expanded):
        return expanded
    try:
        import pwd

        account_home = Path(pwd.getpwuid(os.getuid()).pw_dir)
        if account_home and not _looks_like_sandbox_home(account_home):
            return account_home
    except Exception:
        pass
    macos_home = _home_from_macos_users_dir()
    if macos_home:
        return macos_home
    return expanded


def expand_runtime_path(value: str | Path) -> Path:
    raw = str(value)
    if raw == "~":
        return runtime_user_home()
    if raw.startswith("~/") or raw.startswith("~\\"):
        return runtime_user_home() / raw[2:]
    return Path(raw).expanduser()


def load_input_documents(folder: Path | None, config: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if folder is None or not folder.exists():
        return [], [] if folder is None else [{"status": "missing", "path": str(folder), "warning": "input_folder does not exist"}]
    records: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    for path in sorted(item for item in folder.rglob("*") if item.is_file() and item.suffix.lower() in SUPPORTED_SUFFIXES):
        suffix = path.suffix.lower()
        try:
            if suffix in TEXT_SUFFIXES:
                text = path.read_text(encoding="utf-8", errors="replace")
                method = "direct_text"
            elif extract_document is not None:
                text = _call_optional(extract_document, path=str(path), file_path=str(path), config=config) or ""
                method = "ocr_skill" if text else "ocr_empty"
            else:
                text = ""
                method = "ocr_unavailable"
            record = {
                "path": str(path),
                "name": path.name,
                "suffix": suffix,
                "bytes": path.stat().st_size,
                "sha256": _sha256(path.read_bytes()),
                "extraction_method": method,
                "status": "extracted" if text else "review_required",
                "text": text[:20000],
                "source_ref": f"local:{path.name}",
            }
            records.append(record)
            if not text:
                warnings.append({"path": str(path), "status": "review_required", "message": f"No usable text extracted from {path.name}."})
        except Exception as exc:  # Keep one bad document from hiding the rest.
            warnings.append({"path": str(path), "status": "failed", "message": str(exc)})
    return records, warnings


def _call_optional(function: Callable[..., Any], **kwargs: Any) -> Any:
    try:
        signature = inspect.signature(function)
        accepted = {name: value for name, value in kwargs.items() if name in signature.parameters}
        return function(**accepted)
    except (TypeError, ValueError):
        return function(next(iter(kwargs.values())))


__all__ = ['normalize_inputs', '_as_list', 'resolve_input_folder', '_looks_like_sandbox_home', '_home_from_mirror_neuron_path', '_home_from_macos_users_dir', 'runtime_user_home', 'expand_runtime_path', 'load_input_documents', '_call_optional']
