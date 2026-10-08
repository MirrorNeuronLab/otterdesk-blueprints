"""Read CCTV's authoritative model definitions from its staged source manifest."""

from mn_sdk.blueprint_support import source_manifest


def cosmos_model_spec():
    declaration = source_manifest(__file__)["runtime"]["models"]["vision"]
    return declaration["model_spec"]
