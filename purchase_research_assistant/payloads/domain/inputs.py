"""Purchase-input normalization, path resolution, and local document intake."""

from __future__ import annotations

import copy
import ipaddress
import inspect
import os
import re
import urllib.parse
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


_REQUEST_FIELD_ALIASES = {
    "what i want to buy": "item_description",
    "purchase goal": "item_description",
    "item description": "item_description",
    "item or trip": "item_description",
    "purchase type": "purchase_type",
    "category": "purchase_type",
    "budget": "budget",
    "price ceiling": "budget",
    "location": "location",
    "route": "route",
    "travel dates": "travel_dates",
    "purchase timing": "travel_dates",
}
_PRIORITY_SECTION_NAMES = {"priorities", "preferences", "ranking priorities"}
_CONSTRAINT_SECTION_NAMES = {"constraints", "hard constraints", "must haves", "must-have requirements"}
_RESEARCH_SECTION_NAMES = {
    "research",
    "research links",
    "research leads",
    "research already started but incomplete",
    "unfinished research",
}
_CONSTRAINT_KEY_ALIASES = {
    "property type": "property_type",
    "minimum bedrooms": "min_bedrooms",
    "min bedrooms": "min_bedrooms",
    "bedrooms minimum": "min_bedrooms",
    "zip": "zip_code",
    "zip code": "zip_code",
    "postal code": "zip_code",
}
_EMPTY_VALUES = {"", "none", "not set", "not specified", "unknown", "n/a", "null"}
_SENSITIVE_URL_QUERY_KEYS = {
    "access_token",
    "api_key",
    "apikey",
    "auth",
    "authorization",
    "key",
    "password",
    "secret",
    "signature",
    "sig",
    "token",
}


def resolve_request_from_documents(
    inputs: dict[str, Any],
    documents: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Treat a plain-text purchase request as the primary request contract."""
    normalized = normalize_inputs(inputs)
    request_document = _select_request_document(documents)
    parsed = (
        parse_plain_text_purchase_request(str(request_document.get("text") or ""))
        if request_document is not None
        else {}
    )
    links = extract_public_research_links(documents)
    if parsed:
        request_values = {
            key: value
            for key, value in parsed.items()
            if key
            in {
                "purchase_type",
                "item_description",
                "budget",
                "location",
                "route",
                "travel_dates",
                "priorities",
                "constraints",
            }
        }
        normalized = normalize_inputs({**normalized, **request_values})
    return normalized, {
        "source_ref": request_document.get("source_ref") if request_document else None,
        "source_name": request_document.get("name") if request_document else None,
        "parsed_fields": sorted(parsed),
        "research_links": links,
    }


def parse_plain_text_purchase_request(text: str) -> dict[str, Any]:
    """Parse the small labeled plain-text contract while retaining prose for the LLM."""
    parsed: dict[str, Any] = {}
    priorities: list[str] = []
    constraints: dict[str, Any] = {}
    active_section = ""
    pending_field = ""
    prose_lines: list[str] = []

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        cleaned = line.lstrip("-*• ").strip()
        label_match = re.match(r"^([^:]{1,80}):\s*(.*)$", cleaned)
        if label_match:
            label = _normalize_label(label_match.group(1))
            value = label_match.group(2).strip()
            field = _REQUEST_FIELD_ALIASES.get(label)
            if field:
                if value:
                    parsed[field] = _parse_request_field(field, value)
                    pending_field = ""
                else:
                    pending_field = field
                active_section = ""
                continue
            if label in _PRIORITY_SECTION_NAMES:
                active_section = "priorities"
                pending_field = ""
                if value:
                    priorities.extend(_as_list(value))
                continue
            if label in _CONSTRAINT_SECTION_NAMES:
                active_section = "constraints"
                pending_field = ""
                if value:
                    _add_constraint(constraints, value)
                continue
            if label in _RESEARCH_SECTION_NAMES:
                active_section = "research"
                pending_field = ""
                continue
            if active_section == "constraints" and value and line != cleaned:
                _add_constraint(constraints, f"{label_match.group(1)}: {value}")
                continue
            active_section = ""
            pending_field = ""
            continue

        if pending_field:
            parsed[pending_field] = _parse_request_field(pending_field, cleaned)
            pending_field = ""
            continue
        if active_section == "priorities" and line != cleaned:
            priorities.append(cleaned)
            continue
        if active_section == "constraints" and line != cleaned:
            _add_constraint(constraints, cleaned)
            continue
        if not line.startswith("#") and not re.search(r"https?://", line, flags=re.I):
            prose_lines.append(cleaned)

    if priorities:
        parsed["priorities"] = list(dict.fromkeys(priorities))
    if constraints:
        parsed["constraints"] = constraints
    if not str(parsed.get("item_description") or "").strip() and prose_lines:
        parsed["item_description"] = prose_lines[0][:1000]
    if parsed.get("item_description") and not parsed.get("purchase_type"):
        parsed["purchase_type"] = _infer_purchase_type(str(parsed["item_description"]))
    return parsed


def extract_public_research_links(documents: list[dict[str, Any]]) -> list[str]:
    links: list[str] = []
    for document in documents:
        text = str(document.get("text") or "")
        for raw_url in re.findall(r"https?://[^\s<>{}\\\"']+", text, flags=re.I):
            url = _public_research_url(raw_url.rstrip(".,;:!?)\\]"))
            if url:
                links.append(url)
    return list(dict.fromkeys(links))


def _select_request_document(documents: list[dict[str, Any]]) -> dict[str, Any] | None:
    text_documents = [
        document
        for document in documents
        if str(document.get("suffix") or "").lower() in {".txt", ".md"}
        and str(document.get("name") or "").lower() != "readme.md"
        and str(document.get("text") or "").strip()
    ]
    for document in text_documents:
        name = str(document.get("name") or "").lower()
        if name in {"purchase_request.txt", "purchase_request.md"}:
            return document
    labeled = [
        document
        for document in text_documents
        if re.search(
            r"(?im)^\s*(what i want to buy|purchase goal|item description|purchase type)\s*:",
            str(document.get("text") or ""),
        )
    ]
    if labeled:
        return labeled[0]
    return text_documents[0] if len(text_documents) == 1 else None


def _parse_request_field(field: str, value: str) -> Any:
    if field == "budget":
        if value.strip().lower() in _EMPTY_VALUES:
            return None
        numeric = re.sub(r"[^0-9.-]", "", value)
        try:
            return float(numeric)
        except ValueError:
            return value.strip()
    if field == "purchase_type":
        return value.strip().lower().replace(" ", "_")
    return value.strip()


def _add_constraint(constraints: dict[str, Any], value: str) -> None:
    match = re.match(r"^([^:=]{1,80})\s*[:=]\s*(.+)$", value.strip())
    if not match:
        key = f"must_have_{len(constraints) + 1}"
        constraints[key] = value.strip()
        return
    raw_key, raw_value = match.groups()
    normalized_key = _normalize_label(raw_key)
    key = _CONSTRAINT_KEY_ALIASES.get(normalized_key, normalized_key.replace(" ", "_"))
    constraints[key] = (
        raw_value.strip()
        if key == "zip_code"
        else _coerce_scalar(raw_value.strip())
    )


def _coerce_scalar(value: str) -> Any:
    lowered = value.lower()
    if lowered in _EMPTY_VALUES:
        return None
    if lowered in {"true", "yes"}:
        return True
    if lowered in {"false", "no"}:
        return False
    if re.fullmatch(r"-?\d+", value):
        return int(value)
    if re.fullmatch(r"-?\d+\.\d+", value):
        return float(value)
    return value


def _normalize_label(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def _infer_purchase_type(description: str) -> str:
    lowered = description.lower()
    if any(term in lowered for term in ("flight", "airline", "airfare", "plane ticket")):
        return "airline_ticket"
    if any(term in lowered for term in ("rental property", "rent an apartment", "lease a home")):
        return "rental_property"
    if any(term in lowered for term in ("house", "home", "condo", "property", "real estate")):
        return "property"
    if any(term in lowered for term in ("car", "vehicle", "truck", "suv", "automobile")):
        return "car"
    return "custom"


def _public_research_url(value: str) -> str:
    try:
        parsed = urllib.parse.urlsplit(value)
        host = (parsed.hostname or "").lower()
        if parsed.scheme.lower() not in {"http", "https"} or not host:
            return ""
        if parsed.username or parsed.password or host == "localhost" or host.endswith(".local"):
            return ""
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            address = None
        if address and (
            address.is_private
            or address.is_loopback
            or address.is_link_local
            or address.is_multicast
            or address.is_reserved
        ):
            return ""
        query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
        if any(key.lower() in _SENSITIVE_URL_QUERY_KEYS for key, _value in query):
            return ""
        return urllib.parse.urlunsplit(
            (parsed.scheme.lower(), parsed.netloc, parsed.path or "/", parsed.query, "")
        )[:2048]
    except (TypeError, ValueError):
        return ""


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


__all__ = [
    "extract_public_research_links",
    "expand_runtime_path",
    "load_input_documents",
    "normalize_inputs",
    "parse_plain_text_purchase_request",
    "resolve_input_folder",
    "resolve_request_from_documents",
    "runtime_user_home",
]
