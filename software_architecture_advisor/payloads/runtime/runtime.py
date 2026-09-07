"""SDK-owned configuration, run context, and persistence integration."""
from mn_sdk.blueprint_support import create_blueprint_run_context, persist_blueprint_run_context, source_manifest


def runtime_context_for_step(*, inputs=None, config=None, runs_root=None, run_id=None):
    manifest = source_manifest(__file__)
    base = create_blueprint_run_context(
        runtime_file=__file__, blueprint_id=manifest["metadata"]["blueprint_id"],
        inputs={key: value for key, value in (inputs or {}).items() if value is not None}, config=config, runs_root=runs_root, run_id=run_id,
    )
    base.run_dir.mkdir(parents=True, exist_ok=True)
    persist_blueprint_run_context(base)
    return base.to_mapping()
