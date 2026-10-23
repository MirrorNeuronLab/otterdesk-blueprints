"""CT request policy; the stock native block owns dispatch and recovery."""

from pathlib import Path
from mn_sdk.integrations.block_inputs import capture_declared_inputs

MAX_CT_BYTES = 64 * 1024 * 1024


def prepare(block, inputs):
    inputs = capture_declared_inputs(block, inputs, runtime_file=__file__)
    source = Path(inputs.get("ct_file") or "")
    region = inputs.get("region")
    prompt = inputs.get("prompt") or f'write a structured {"abdominal" if region == "abdomen" else "chest"} CT report'
    if region not in {"chest", "abdomen"} or not isinstance(prompt, str) or not 0 < len(prompt) <= 2000:
        raise ValueError("A matching chest/abdomen region and bounded research question are required.")
    if not source.is_absolute() or not source.is_file() or source.is_symlink():
        raise ValueError("CT input must be a resolved staged file.")
    with source.open("rb") as stream:
        volume = stream.read(MAX_CT_BYTES + 1)
    if not 0 < len(volume) <= MAX_CT_BYTES:
        raise ValueError("CT input exceeds the file limit or is empty.")
    reference = block.store.commit_bytes(f"{block.root}/ct-input.bin", volume, kind="ct_volume")
    return {"path": "/ct", "payload": {
        "volume_base64": {"$artifact": reference.to_dict(), "encoding": "base64"},
        "region": region, "prompt": prompt}}


def accepted(block, result):
    answer, revision = result.get("answer"), result.get("model_revision")
    return (result.get("research_only") is True and isinstance(answer, str)
        and 0 < len(answer.strip()) <= 32000 and isinstance(revision, str) and 0 < len(revision) <= 128)
