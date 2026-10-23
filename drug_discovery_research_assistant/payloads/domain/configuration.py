"""Scientific input precedence and runtime-provided output destinations."""
import copy
from mn_sdk.blueprint_support import source_manifest
from mn_sdk.integrations.block_inputs import capture_declared_inputs

SOURCE = source_manifest(__file__)
BLUEPRINT_ID = SOURCE["metadata"]["blueprint_id"]


def research_inputs(block, inputs):
    return capture_declared_inputs(block, inputs, runtime_file=__file__)


def cycle_configuration(block, state):
    config = copy.deepcopy(block.config)
    config.setdefault("inputs", {}).setdefault("payload", {}).update(state["research_inputs"])
    config["inputs"]["payload"].update(targets=state["targets"], output_folder=str(block.output_directory))
    return config
