"""SDK-owned configuration, context and persistence only."""
from mn_sdk.blueprint_support import create_blueprint_run_context, persist_blueprint_run_context, source_manifest


def runtime_context_for_step(*, inputs=None, config=None, runs_root=None, run_id=None):
    manifest = source_manifest(__file__)
    context = create_blueprint_run_context(runtime_file=__file__, blueprint_id=manifest['metadata']['blueprint_id'],
        inputs=inputs, config=config, runs_root=runs_root, run_id=run_id)
    context.run_dir.mkdir(parents=True, exist_ok=True)
    persist_blueprint_run_context(context)
    return context.to_mapping()
