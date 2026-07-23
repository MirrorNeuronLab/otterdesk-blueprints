"""Validated runtime configuration, path, OCR, and context preparation."""

from __future__ import annotations

from typing import Any

from mn_sdk.blueprint_support import create_blueprint_run_context

from .common import *

def _script_blueprint_root() -> Path:
    script_path = Path(__file__).resolve()
    if len(script_path.parents) > 3 and script_path.parents[2].name == "payloads":
        return script_path.parents[3]
    if len(script_path.parents) > 2:
        return script_path.parents[2]
    return script_path.parent

def default_config_path() -> Path:
    configured_path = os.environ.get("MN_BLUEPRINT_CONFIG_PATH")
    if configured_path:
        candidate = Path(configured_path).expanduser()
        if candidate.exists():
            return candidate

    bundle_dir = os.environ.get("MN_BLUEPRINT_BUNDLE_DIR")
    if bundle_dir:
        candidate = Path(bundle_dir).expanduser() / "config" / "default.json"
        if candidate.exists():
            return candidate

    script_path = Path(__file__).resolve()
    for parent in script_path.parents:
        candidate = parent / "config" / "default.json"
        if candidate.exists():
            return candidate
    return _script_blueprint_root() / "config" / "default.json"

def blueprint_dir() -> Path:
    return default_config_path().parents[1]

def load_resolved_config(config: dict[str, Any] | None = None, config_json: str | None = None) -> dict[str, Any]:
    resolved_default_path = default_config_path()
    if not resolved_default_path.exists():
        embedded_config = config_json or os.environ.get("MN_BLUEPRINT_CONFIG_JSON")
        if embedded_config:
            decoded = json.loads(embedded_config)
            if isinstance(decoded, dict):
                return deep_merge(decoded, config or {})
    return load_shared_resolved_config(
        resolved_default_path,
        overlay=config,
        config_json=config_json,
    )

def runtime_message_payload() -> dict[str, Any]:
    for env_name in ("MN_WORKFLOW_INPUT_JSON", "MN_INPUT_JSON", "MN_MESSAGE_JSON"):
        raw = os.environ.get(env_name)
        if not raw:
            continue
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            continue
        payload = find_payload(value)
        if payload:
            return payload
    return {}

def find_payload(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        interesting = {"document_folder", "input_folder", "output_folder", "field_profile", "matter_profile", "review_policy"}
        if interesting & set(value):
            return copy.deepcopy(value)
        for key in ("kwargs", "payload", "input", "body", "data", "message", "content"):
            found = find_payload(value.get(key))
            if found:
                return found
        for nested in value.values():
            found = find_payload(nested)
            if found:
                return found
    elif isinstance(value, list):
        for nested in value:
            found = find_payload(nested)
            if found:
                return found
    elif isinstance(value, str) and value.strip().startswith(("{", "[")):
        try:
            return find_payload(json.loads(value))
        except json.JSONDecodeError:
            return {}
    return {}

def resolve_inputs(config: dict[str, Any], inputs: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = copy.deepcopy(((config.get("inputs") or {}).get("payload") or {}))
    payload = deep_merge(payload, runtime_message_payload())
    payload = deep_merge(payload, inputs or {})
    if "document_folder" not in payload and payload.get("input_folder"):
        payload["document_folder"] = payload["input_folder"]
    if "input_folder" not in payload and payload.get("document_folder"):
        payload["input_folder"] = payload["document_folder"]
    return payload

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
    names = [
        os.environ.get("SUDO_USER"),
        os.environ.get("LOGNAME"),
        os.environ.get("USER"),
    ]
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

def resolve_output_folder(
    payload: dict[str, Any],
    resolved_config: dict[str, Any],
    inputs: dict[str, Any] | None = None,
) -> Path:
    runtime_output_folder = os.environ.get("MN_JOB_OUTPUT_DIR")
    if runtime_output_folder:
        return expand_runtime_path(runtime_output_folder)
    explicit_output_folder = (inputs or {}).get("output_folder")
    if explicit_output_folder:
        return expand_runtime_path(explicit_output_folder)
    outputs_config = resolved_config.get("outputs") if isinstance(resolved_config.get("outputs"), dict) else {}
    configured_output_folder = outputs_config.get("output_folder") or outputs_config.get("folder_path")
    configured_target = payload.get("output_folder") or configured_output_folder
    if configured_target:
        return expand_runtime_path(configured_target)
    return expand_runtime_path(f"outputs/{BLUEPRINT_ID}")

def resolve_run_dir(output_folder: Path, run_id: str, runs_root: str | Path | None = None) -> Path:
    if not runs_root:
        env_run_dir = os.environ.get("MN_RUN_DIR")
        if env_run_dir:
            return expand_runtime_path(env_run_dir)
    resolved_runs_root = runs_root or os.environ.get("MN_RUNS_ROOT")
    if resolved_runs_root:
        return expand_runtime_path(resolved_runs_root) / run_id
    return output_folder / "runs" / run_id

def expand_path(raw: Any, *, root: Path | None = None) -> Path:
    value = str(raw or "").strip() or "."
    path = expand_runtime_path(value)
    if not path.is_absolute() and root is not None:
        if path.parts and path.parts[0] == root.name:
            path = root.parent / path
        else:
            path = root / path
    return path.resolve()

def fake_llm_requested(config: dict[str, Any], payload: dict[str, Any] | None = None) -> bool:
    if not payload or not payload.get("quick_test"):
        return fake_llm_mode_enabled(config)
    merged = copy.deepcopy(config)
    merged.setdefault("execution", {})["quick_test"] = True
    return fake_llm_mode_enabled(merged)

def _ocr_skill_config(config: dict[str, Any]) -> dict[str, Any]:
    input_skills = config.get("input_skills") if isinstance(config.get("input_skills"), dict) else {}
    return {"input_skills": input_skills}

def build_ocr_runtime(ctx: dict[str, Any]) -> tuple[Any | None, dict[str, Any]]:
    section = (ctx["config"].get("input_skills") or {}).get("llm_ocr")
    section = section if isinstance(section, dict) else {}
    install_policy = str(section.get("install_policy") or "on_first_required_document")
    status: dict[str, Any] = {
        "enabled": section.get("enabled", True) is not False,
        "skill_available": extract_document is not None and docker_ocr_client_factory_from_config is not None,
        "configured": False,
        "status": "not_needed",
        "install_policy": install_policy,
        "trigger": f"PDF/image with less than {OCR_MIN_TEXT_CHARS} embedded characters",
        "source_model": "lightonai/LightOnOCR-2-1B",
        "warnings": [],
    }
    if not status["enabled"]:
        status["status"] = "disabled"
        status["warnings"].append("llm_ocr_disabled_in_config")
        return None, status
    if fake_llm_requested(ctx["config"], ctx.get("payload")):
        status["status"] = "disabled_for_fake_or_quick_test"
        status["warnings"].append("llm_ocr_skipped_for_explicit_fake_or_quick_test")
        return None, status
    if not status["skill_available"]:
        status["status"] = "skill_unavailable"
        status["warnings"].append("mirrorneuron_llm_ocr_skill_unavailable")
        return None, status
    try:
        factory = docker_ocr_client_factory_from_config(_ocr_skill_config(ctx["config"]))
        if factory is None:
            status["status"] = "disabled_by_skill_config"
            status["warnings"].append("llm_ocr_factory_disabled")
            return None, status
        client = factory()
        model_config = getattr(client, "config", None)
        status.update(
            {
                "configured": True,
                "status": "ready_for_runtime_managed_first_use" if install_policy == "runtime" else "ready_for_lazy_first_use",
                "runtime_model": getattr(model_config, "model", None),
                "backend": getattr(model_config, "backend", None),
                "expected_accelerator": getattr(model_config, "expected_accelerator", None),
            }
        )
        return client, status
    except Exception as exc:  # pragma: no cover - depends on local OCR runtime
        status["status"] = "configuration_failed"
        status["warnings"].append(f"llm_ocr_configuration_failed:{exc}")
        return None, status


def runtime_context_for_step(
    *,
    inputs: dict[str, Any] | None = None,
    config: dict[str, Any] | None = None,
    runs_root: str | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    context = create_blueprint_run_context(
        runtime_file=__file__,
        blueprint_id=BLUEPRINT_ID,
        inputs=inputs,
        config=config,
        runs_root=runs_root,
        run_id=run_id,
    )
    return context.to_mapping()


__all__ = ["append_event", "build_ocr_runtime", "expand_path", "expand_runtime_path", "runtime_context_for_step"]
