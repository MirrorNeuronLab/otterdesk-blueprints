"""Runtime context only; secrets stay in the process environment."""
from mn_sdk.blueprint_support import create_blueprint_run_context
from mn_sdk.blueprint_support import source_manifest

def runtime_context_for_step(inputs=None, config=None, **options):
    blueprint_id = source_manifest(__file__)["identity"]["id"]
    return create_blueprint_run_context(runtime_file=__file__, blueprint_id=blueprint_id,
        inputs=inputs, config=config, **options).to_mapping()
