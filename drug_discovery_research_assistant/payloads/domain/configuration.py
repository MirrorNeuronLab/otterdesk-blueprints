"""Scientific input precedence and runtime-provided output destinations."""
import copy
import os
from pathlib import Path
from mn_sdk.blueprint_support import source_manifest

SOURCE = source_manifest(__file__)
BLUEPRINT_ID = SOURCE["metadata"]["blueprint_id"]
INPUT_KEYS = frozenset(SOURCE["contracts"]["inputs"])


def output_directory(block):
    return Path(os.environ["MN_JOB_OUTPUT_DIR"]) if os.environ.get("MN_JOB_OUTPUT_DIR") else block.store.run_dir


def research_inputs(block, inputs):
    values = dict((block.config.get("inputs") or {}).get("payload") or {})
    values.update({key: value for key, value in inputs.items() if key in INPUT_KEYS and value is not None})
    folder = values.get("input_folder")
    if folder and not Path(folder).is_absolute():
        workdir = os.environ.get("MN_WORKDIR")
        if not workdir:
            raise ValueError("SDK worker directory is required for staged scientific inputs.")
        values["input_folder"] = str(Path(workdir) / folder)
    return values


def cycle_configuration(block, state):
    config = copy.deepcopy(block.config)
    config.setdefault("inputs", {}).setdefault("payload", {}).update(state["research_inputs"])
    config["inputs"]["payload"].update(targets=state["targets"], output_folder=str(output_directory(block)))
    return config
