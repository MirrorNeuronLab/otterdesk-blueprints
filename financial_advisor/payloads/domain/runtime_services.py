"""Validated configuration, invocation input, and path preparation."""

from .common import *
from .knowledge import load_financial_knowledge
from .review_services import build_llm_client
from .state import load_state, runtime_context_path

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

    for parent in Path(__file__).resolve().parents:
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
        include_env_path=False,
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
    if not isinstance(value, dict):
        return {}
    interesting = {
        "document_folder",
        "input_folder",
        "output_folder",
        "portfolio",
        "tax_year",
        "filing_status",
        "monitoring",
    }
    if interesting & set(value):
        return {key: value[key] for key in value if key in value}
    for key in ("payload", "input", "body", "data", "message", "content"):
        found = find_payload(value.get(key))
        if found:
            return found
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

def expand_path(raw: Any, *, root: Path | None = None) -> Path:
    value = str(raw or "").strip()
    if not value:
        value = "."
    path = Path(value).expanduser()
    if not path.is_absolute() and root is not None:
        path = root / path
    return path.resolve()

def build_context(
    *,
    inputs: dict[str, Any] | None,
    config: dict[str, Any] | None,
    config_json: str | None,
    runs_root: str | Path | None,
    run_id: str | None,
    llm_client: Any | None,
) -> dict[str, Any]:
    resolved_config = load_resolved_config(config, config_json)
    payload = resolve_inputs(resolved_config, inputs)
    root = blueprint_dir()
    document_folder = expand_path(payload.get("document_folder") or payload.get("input_folder"), root=root.parent if str(payload.get("document_folder", "")).startswith(BLUEPRINT_ID) else root)
    if not document_folder.exists():
        document_folder = expand_path(payload.get("document_folder") or payload.get("input_folder"), root=Path.cwd())
    outputs_config = resolved_config.get("outputs") if isinstance(resolved_config.get("outputs"), dict) else {}
    explicit_output_folder = (inputs or {}).get("output_folder")
    runtime_output_folder = os.environ.get("MN_JOB_OUTPUT_DIR")
    configured_output_folder = outputs_config.get("output_folder") or outputs_config.get("folder_path")
    output_folder = expand_path(
        explicit_output_folder
        or runtime_output_folder
        or configured_output_folder
        or payload.get("output_folder")
        or f"~/Downloads/{BLUEPRINT_ID}"
    )
    output_folder.mkdir(parents=True, exist_ok=True)
    run_id_value = run_id or payload.get("run_id") or os.environ.get("MN_RUN_ID") or f"{BLUEPRINT_ID}-{uuid.uuid4().hex[:8]}"
    env_run_dir = os.environ.get("MN_RUN_DIR")
    if not runs_root and env_run_dir:
        run_dir = expand_path(env_run_dir)
        runs_root_path = run_dir.parent
    else:
        runs_root_path = expand_path(runs_root or os.environ.get("MN_RUNS_ROOT") or output_folder / "runs")
        run_dir = runs_root_path / run_id_value
    run_dir.mkdir(parents=True, exist_ok=True)
    persisted = read_json(runtime_context_path(run_dir))
    started_at = utc_now_iso()
    if persisted:
        persisted_payload = persisted.get("payload") if isinstance(persisted.get("payload"), dict) else {}
        payload = deep_merge(payload, persisted_payload)
        document_folder = expand_path(persisted.get("document_folder") or document_folder)
        output_folder = expand_path(persisted.get("output_folder") or output_folder)
        persisted_run_dir = str(persisted.get("run_dir") or "").strip()
        if persisted_run_dir:
            run_dir = expand_path(persisted_run_dir)
            runs_root_path = run_dir.parent
            run_dir.mkdir(parents=True, exist_ok=True)
        started_at = str(persisted.get("started_at") or started_at)
    payload["document_folder"] = str(document_folder)
    payload["input_folder"] = str(document_folder)
    payload["output_folder"] = str(output_folder)
    llm = build_llm_client(resolved_config, payload, llm_client)
    state = load_state(run_dir) or {"workflow": {}, "actor_findings": {}, "model_profiles_used": {}}
    return {
        "blueprint_id": BLUEPRINT_ID,
        "config": resolved_config,
        "payload": payload,
        "blueprint_dir": root,
        "document_folder": document_folder,
        "output_folder": output_folder,
        "runs_root": runs_root_path,
        "run_dir": run_dir,
        "run_id": run_id_value,
        "started_at": started_at,
        "llm": llm,
        "state": state,
        "active_knowledge": load_financial_knowledge(root),
    }

def runtime_context_for_step(
    *,
    inputs: dict[str, Any] | None = None,
    config: dict[str, Any] | None = None,
    runs_root: str | Path | None = None,
    run_id: str | None = None,
    llm_client: Any | None = None,
) -> dict[str, Any]:
    """Adapt the financial domain context to the SDK step lifecycle."""
    return build_context(
        inputs=inputs,
        config=config,
        config_json=None,
        runs_root=runs_root,
        run_id=run_id,
        llm_client=llm_client,
    )
