"""Folder transcription policy; the SDK journals model calls and publication."""

from pathlib import Path

from mn_nvidia_transcribe_skill import (
    MODEL_REVISION,
    SOURCE_MODEL,
    build_transcription_request,
    parse_completion,
    prepare_audio,
    scan_audio_folder,
)
from mn_sdk.blueprint.context import source_manifest
from mn_sdk.blueprint.hooks import fingerprint
from mn_sdk.blueprint.inputs import capture_declared_inputs
from mn_sdk.blueprint.models import model_request
from mn_sdk.blueprint.outputs import capture_file, materialize_file, publish_artifact_bundle
from mn_sdk_common.publication import ArtifactWrite


def _snapshot(block, folder):
    records = []
    for path in scan_audio_folder(folder):
        block.check()
        relative = path.relative_to(folder).as_posix()
        ref = capture_file(block, path, key=relative)
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


def _chunks(block, item, seconds):
    source = materialize_file(
        block,
        item["file"],
        path=block.root
        + "/audio-inputs/"
        + fingerprint(item["source"])
        + Path(item["source"]).suffix,
    )
    with prepare_audio(source, chunk_seconds=seconds) as document:
        if document.source_sha256 != item["source_sha256"]:
            raise ValueError("Audio snapshot does not match its source hash")
        chunks = []
        for chunk in document.chunks():
            block.check()
            ref = block.store.commit_bytes(
                block.root
                + "/audio-chunks/"
                + fingerprint(item["source"])
                + "/"
                + str(chunk.index)
                + ".wav",
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


def _time(seconds):
    milliseconds = round(seconds * 1000)
    hours, milliseconds = divmod(milliseconds, 3600000)
    minutes, milliseconds = divmod(milliseconds, 60000)
    seconds, milliseconds = divmod(milliseconds, 1000)
    return f"{hours:02}:{minutes:02}:{seconds:02}.{milliseconds:03}"


def run(block, inputs):
    inputs = capture_declared_inputs(block, inputs, runtime_file=__file__)
    folder = Path(inputs.get("input_folder") or "")
    if not folder.is_absolute():
        raise ValueError("An absolute staged audio folder is required")
    seconds = inputs.get("chunk_seconds", 300)
    if type(seconds) is not int or not 1 <= seconds <= 300:
        raise ValueError("chunk_seconds must be 1–300")
    inventory_path = block.root + "/audio-inventory.json"
    inventory = block.read_checkpoint(
        block.freeze_checkpoint(inventory_path, lambda: _snapshot(block, folder)),
        expected_path=inventory_path,
    )
    declaration = source_manifest(__file__)["runtime"]["models"]["transcribe"]
    prepared_inputs = []
    for item in inventory:
        block.check()
        prepared_path = block.root + "/prepared-audio/" + fingerprint(item["source"]) + ".json"
        prepared = block.read_checkpoint(
            block.freeze_checkpoint(prepared_path, lambda item=item: _chunks(block, item, seconds)),
            expected_path=prepared_path,
        )
        prepared_inputs.append((item, prepared))
    if sum(len(prepared["chunks"]) for _, prepared in prepared_inputs) >= block.max_calls:
        raise ValueError("Audio inventory exceeds the declared model call budget")
    writes, records = [], []
    for item, prepared in prepared_inputs:
        block.check()
        sections, chunks, text_bytes = [], [], 0
        for chunk in prepared["chunks"]:
            block.check()
            request = build_transcription_request(block.store.read_bytes(chunk["audio"]))
            request["model"] = declaration["model"]
            request["payload"]["model"] = declaration["model_spec"]["api_model"]
            request["options"].update(
                provider=declaration["provider"],
                backend=declaration["backend"],
                model_spec=declaration["model_spec"],
            )
            request["payload"]["messages"][0]["content"][1]["audio_url"]["url"] = {
                "$artifact": chunk["audio"],
                "encoding": "data_uri",
                "mime_type": "audio/wav",
            }
            response = model_request(
                block, request, key=fingerprint([item["source"], chunk["index"]])
            )
            text = parse_completion(response)
            text_bytes += len(text.encode())
            if text_bytes > 4 * 1024 * 1024:
                raise ValueError("Transcript exceeds 4 MiB per recording")
            sections.append(
                "## "
                + _time(chunk["start_seconds"])
                + " – "
                + _time(chunk["end_seconds"])
                + "\n\n"
                + (text or "[No transcript text returned for this chunk.]")
            )
            chunks.append(
                {
                    "index": chunk["index"],
                    "start_seconds": chunk["start_seconds"],
                    "end_seconds": chunk["end_seconds"],
                    "empty": not bool(text),
                }
            )
        markdown = (
            "# Audio transcript\n\nSource: "
            + item["source"]
            + "\n\nSource SHA-256: "
            + item["source_sha256"]
            + "\n\nModel: "
            + SOURCE_MODEL
            + "\n\nModel revision: "
            + MODEL_REVISION
            + "\n\nTimes label input chunks; they are not word alignments. Chunk boundaries may split words.\n\n"
            + "\n\n".join(sections)
            + "\n"
        )
        path = "transcripts/" + item["source"] + ".md"
        transcript = block.store.commit_bytes(path, markdown.encode(), kind="markdown")
        writes.append(
            ArtifactWrite(
                "transcript-" + fingerprint(item["source"]),
                path,
                block.store.read_bytes(transcript),
                kind="markdown",
                authoritative=True,
            )
        )
        records.append(
            {
                "source": item["source"],
                "source_sha256": item["source_sha256"],
                "duration_seconds": prepared["duration_seconds"],
                "transcript": transcript.to_dict(),
                "chunks": chunks,
            }
        )
    report = {
        "schema": "mn.nvidia_transcribe.batch.v1",
        "source_model": SOURCE_MODEL,
        "model_revision": MODEL_REVISION,
        "file_count": len(records),
        "files": records,
    }
    reference = block.store.commit("transcription_result.json", report, kind="transcription_result")
    writes.append(
        ArtifactWrite(
            "transcription_result",
            "transcription_result.json",
            block.store.read_bytes(reference),
            kind="transcription_result",
            authoritative=True,
        )
    )
    publish_artifact_bundle(block, writes, receipt_path=block.root + "/publication.json")
    return {"report": reference.to_dict(), "file_count": len(records)}
