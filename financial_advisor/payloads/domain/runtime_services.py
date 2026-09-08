"""Financial Advisor runtime context and service preparation."""

from .common import *
from .knowledge import load_financial_knowledge
from .review_services import build_llm_client
from .state import load_state, runtime_context_path

def _config_overlay(
    config: dict[str, Any] | None, config_json: str | None
) -> dict[str, Any] | None:
    """Keep the local runner's optional JSON overlay within the SDK contract."""

    if not config_json:
        return config
    decoded = json.loads(config_json)
    if not isinstance(decoded, dict):
        raise ValueError("Financial Advisor config_json must be a JSON object")
    return deep_merge(decoded, config or {})


def _resolve_document_folder(
    raw_folder: Any, *, payload_root: Path, blueprint_root: Path
) -> Path:
    return resolve_existing_path(
        str(raw_folder or ""),
        [payload_root, blueprint_root, blueprint_root.parent],
        blueprint_id=BLUEPRINT_ID,
    )

def build_context(
    *,
    inputs: dict[str, Any] | None,
    config: dict[str, Any] | None,
    config_json: str | None,
    runs_root: str | Path | None,
    run_id: str | None,
    llm_client: Any | None,
) -> dict[str, Any]:
    base = create_blueprint_run_context(
        runtime_file=__file__,
        blueprint_id=BLUEPRINT_ID,
        inputs=inputs,
        config=_config_overlay(config, config_json),
        runs_root=runs_root,
        run_id=run_id,
    )
    payload = base.payload
    persisted = read_json(runtime_context_path(base.run_dir))
    persisted_folder = persisted.get("document_folder") if persisted else None
    document_folder = _resolve_document_folder(
        persisted_folder or payload.get("document_folder") or payload.get("input_folder"),
        payload_root=base.layout.payload_root,
        blueprint_root=base.layout.root,
    )
    payload["document_folder"] = str(document_folder)
    payload["input_folder"] = str(document_folder)
    payload["output_folder"] = str(base.output_folder)
    context = base.to_mapping()
    context.update({
        "_base_context": base,
        "blueprint_dir": base.layout.root,
        "document_folder": document_folder,
        "runs_root": base.run_dir.parent,
        "state": load_state(base.run_dir)
        or {"workflow": {}, "actor_findings": {}, "model_profiles_used": {}},
        "active_knowledge": load_financial_knowledge(base.layout.root),
    })
    context["llm"] = build_llm_client(base.config, payload, llm_client)
    return context

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
