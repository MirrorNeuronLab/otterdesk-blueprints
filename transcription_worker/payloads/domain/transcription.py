"""Transcribe prepared recordings using the SDK's durable model journal."""

from mn_nvidia_transcribe_skill import (
    MODEL_REVISION,
    SOURCE_MODEL,
    build_transcription_request,
    parse_completion,
)
from mn_sdk.blueprint.context import source_manifest
from mn_sdk.blueprint.hooks import ProcessingProgress, fingerprint
from mn_sdk.blueprint.models import model_request
from mn_sdk.blueprint.outputs import publish_artifact_bundle
from mn_sdk_common.publication import ArtifactWrite

from .alignment import playback_alignment, request_timestamps
from .audio_preparation import read_prepared_audio
from .reporting import publish_replay


def _time(seconds):
    milliseconds = round(seconds * 1000)
    hours, milliseconds = divmod(milliseconds, 3600000)
    minutes, milliseconds = divmod(milliseconds, 60000)
    seconds, milliseconds = divmod(milliseconds, 1000)
    return f"{hours:02}:{minutes:02}:{seconds:02}.{milliseconds:03}"


def run(block, inputs):
    prepared_inputs = [
        (item, read_prepared_audio(block, item))
        for item in inputs["prepared_audio"]["recordings"]
    ]
    declaration = source_manifest(__file__)["runtime"]["models"]["transcribe"]
    if sum(len(prepared["chunks"]) for _, prepared in prepared_inputs) >= block.max_calls:
        raise ValueError("Audio inventory exceeds the declared model call budget")
    writes, records = [], []
    progress = ProcessingProgress(
        "audio_second",
        total=sum(
            chunk["end_seconds"] - chunk["start_seconds"]
            for _, prepared in prepared_inputs
            for chunk in prepared["chunks"]
        ),
        context=block,
    ).start()
    for item, prepared in prepared_inputs:
        block.check()
        sections, chunks, text_bytes = [], [], 0
        for chunk in prepared["chunks"]:
            block.check()
            request = build_transcription_request(block.store.read_bytes(chunk["audio"]))
            request_timestamps(request)
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
            key = fingerprint([item["source"], chunk["index"]])
            response = model_request(block, request, key=key)
            text = parse_completion(response)
            text_bytes += len(text.encode())
            if text_bytes > 4 * 1024 * 1024:
                raise ValueError("Transcript exceeds 4 MiB per recording")
            progress.record_model_response(
                block, request, key=key,
                units=chunk["end_seconds"] - chunk["start_seconds"],
            )
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
                    "text": text,
                    "audio": chunk["audio"],
                    "alignment": playback_alignment(
                        response, text, chunk["end_seconds"] - chunk["start_seconds"]
                    ),
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
            + "\n\nHeadings label input chunks. Speaker labels restart in each chunk. "
            + "Word alignment, when available, is saved in transcription_result.json.\n\n"
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
    progress.finish()
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
    publish_replay(block, records)
    return {"report": reference.to_dict(), "file_count": len(records)}
