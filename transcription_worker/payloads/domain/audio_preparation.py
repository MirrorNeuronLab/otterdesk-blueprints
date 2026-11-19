"""Capture the selected recordings and prepare immutable audio sections."""

from pathlib import Path

from mn_folder_files_skill import ScanLimits, scan_folder
from mn_nvidia_transcribe_skill import prepare_audio
from mn_sdk.blueprint.context import load_runtime_config
from mn_sdk.blueprint.hooks import fingerprint
from mn_sdk.blueprint.inputs import capture_declared_inputs
from mn_sdk.blueprint.outputs import capture_file, materialize_file


INVENTORY_PATH = "transcription/audio-inventory.json"


def _snapshot(block, folder):
    staging = load_runtime_config(__file__)["local_inputs"]["folders"]
    extensions = next(
        item["allowed_extensions"]
        for item in staging
        if item["config_path"] == "inputs.payload.input_folder"
    )
    inventory = scan_folder(
        folder,
        suffixes=extensions,
        limits=ScanLimits(max_files=100, max_file_bytes=256 * 1024**2),
        check=block.check,
    )
    if not inventory.files:
        raise ValueError("Audio folder contains no supported audio files")
    records = []
    for item in inventory.files:
        block.check()
        relative = item.relative_path
        ref = capture_file(block, item.path, key=relative)
        info = block.store.read(ref)
        records.append(
            {
                "source": relative,
                "source_sha256": info["sha256"],
                "size_bytes": info["size_bytes"],
                "file": ref.to_dict(),
            }
        )
    return records


def scan(block, inputs):
    inputs = capture_declared_inputs(block, inputs, runtime_file=__file__)
    folder = Path(inputs.get("input_folder") or "")
    if not folder.is_absolute():
        raise ValueError("An absolute staged audio folder is required")
    seconds = inputs.get("chunk_seconds", 300)
    if type(seconds) is not int or not 1 <= seconds <= 300:
        raise ValueError("chunk_seconds must be 1–300")
    inventory = block.freeze_checkpoint(
        INVENTORY_PATH, lambda: _snapshot(block, folder)
    )
    return {"inventory": inventory.to_dict(), "chunk_seconds": seconds}


def _chunks(block, item, seconds):
    identity = fingerprint(item["source"])
    source = materialize_file(
        block,
        item["file"],
        path=f"{block.root}/audio-inputs/{identity}{Path(item['source']).suffix}",
    )
    with prepare_audio(source, chunk_seconds=seconds) as document:
        if document.source_sha256 != item["source_sha256"]:
            raise ValueError("Audio snapshot does not match its source hash")
        chunks = []
        for chunk in document.chunks():
            block.check()
            ref = block.store.commit_bytes(
                f"{block.root}/audio-chunks/{identity}/{chunk.index}.wav",
                chunk.wav_bytes,
                kind="transcription_chunk",
            )
            chunks.append(
                {
                    "index": chunk.index,
                    "start_seconds": chunk.start_seconds,
                    "end_seconds": chunk.end_seconds,
                    "audio": ref.to_dict(),
                }
            )
        return {"duration_seconds": document.duration_seconds, "chunks": chunks}


def _prepared_path(source):
    return f"transcription/prepared-audio/{fingerprint(source)}.json"


def prepare(block, inputs):
    scan_result = inputs["scan"]
    inventory = block.read_checkpoint(
        scan_result["inventory"], expected_path=INVENTORY_PATH
    )
    seconds = scan_result["chunk_seconds"]
    recordings = []
    for item in inventory:
        source = item["source"]
        prepared = block.freeze_checkpoint(
            _prepared_path(source), lambda item=item: _chunks(block, item, seconds)
        )
        recordings.append(
            {
                "source": source,
                "source_sha256": item["source_sha256"],
                "audio": prepared.to_dict(),
            }
        )
    return {"recordings": recordings}


def read_prepared_audio(block, recording):
    return block.read_checkpoint(
        recording["audio"], expected_path=_prepared_path(recording["source"])
    )
