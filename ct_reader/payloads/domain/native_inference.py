"""CT-specific request snapshot and reconciliation for the standard native block."""

from pathlib import Path

from domain.reporting import MAX_CT_BYTES, review_ct


def prepare(context, inputs):
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
    reference = context.store.commit_bytes(f"{context.root}/ct-input.bin", volume, kind="ct_volume")
    return {"volume": reference.to_dict(), "inputs": {"ct_file": str(source), "region": region, "prompt": prompt}}


def compute(context, request):
    payload, references = review_ct({"run_dir": context.store.run_dir, "payload": request["inputs"]},
        source_bytes=context.store.read_bytes(request["volume"]))
    # Include hashes of the authoritative report bytes in the block receipt.
    artifacts = [context.store.commit_bytes(item["path"], context.store.path(item["path"]).read_bytes(), kind="ct_report").to_dict()
        for item in references]
    return {**payload, "artifacts": artifacts}


def accepted(context, result):
    return result.get("research_only") is True and len(result.get("artifacts", [])) == 2


def reconcile(context, effect):
    request = effect["data"]
    path = context.store.path("final_artifact.json")
    if not path.is_file():
        return {"state": "unknown"}
    # review_ct checks the source hash, region and prompt before reusing a result;
    # it can reconstruct an interrupted Markdown write without model dispatch.
    return {"state": "succeeded", "value": compute(context, request)}
