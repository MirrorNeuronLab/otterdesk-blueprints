"""Optional completed-run replay, composed with the shared runtime report shell."""

import json
from pathlib import Path

from mn_sdk.blueprint.hooks import fingerprint, report_activity
from mn_sdk.blueprint.outputs import publish_artifact_bundle
from mn_sdk_common.publication import ArtifactWrite

ASSETS = Path(__file__).with_name("report_assets")


def render(record, recordings, run_id):
    from mn_web_report_skill import render_document

    page = render_document(
        title="Audio transcript",
        identity=record["source"],
        content_html=(ASSETS / "content.html").read_text(),
        script=(ASSETS / "replay.js").read_text(),
        style=(ASSETS / "replay.css").read_text(),
        data={"recording": record, "recordings": recordings, "run_id": run_id},
    )
    # The shared shell defaults to no media. This domain view opts into only
    # same-origin captured audio; all other template/CSP restrictions stay intact.
    marker = "frame-src &#x27;self&#x27;;"
    if marker not in page:
        raise ValueError("Shared report media policy could not be applied")
    return page.replace(marker, marker + " media-src &#x27;self&#x27;;", 1).encode()


def publish_replay(block, records):
    """Called only after all authoritative transcripts and their index are delivered."""
    if any(
        chunk["alignment"]["status"] != "ready"
        for record in records
        for chunk in record["chunks"]
    ):
        report_activity(
            "Transcripts saved. Playback report unavailable: word timing could not be verified.",
            kind="diagnostic",
            level="warning",
            step_id=block.step_id,
            run_dir=block.store.run_dir,
        )
        return
    try:
        _publish_replay(block, records)
    except Exception:
        # UI rendering/publication cannot turn completed domain work into failure.
        # Recheck cancellation/budget so the optional boundary never swallows it.
        block.check()
        report_activity(
            "Transcripts saved. The playback report could not be published.",
            kind="diagnostic",
            level="warning",
            step_id=block.step_id,
            run_dir=block.store.run_dir,
        )


def _publish_replay(block, records):
    recordings = [
        {
            "source": record["source"],
            "page": "index.html" if i == 0 else fingerprint(record["source"]) + ".html",
        }
        for i, record in enumerate(records)
    ]
    pages = []
    for record, destination in zip(records, recordings):
        identity = fingerprint(record["source"])
        chunks = []
        for chunk in record["chunks"]:
            path = f"web/audio/{identity}-{chunk['index']}.wav"
            write = ArtifactWrite(
                "audio",
                path,
                lambda ref=chunk["audio"]: block.store.read_bytes(ref),
                kind="audio",
                required=False,
                revision=chunk["audio"]["sha256"],
            )
            receipt = publish_artifact_bundle(
                block,
                [write],
                receipt_path=f"{block.root}/replay-{identity}-{chunk['index']}.json",
            )
            if receipt["warnings"] or receipt.get("delivery_warnings"):
                raise ValueError("Playback audio was not delivered")
            chunks.append(
                {
                    key: chunk[key]
                    for key in (
                        "index",
                        "start_seconds",
                        "end_seconds",
                        "text",
                        "alignment",
                    )
                }
                | {"audio": path.removeprefix("web/")}
            )
        projection = {
            key: record[key] for key in ("source", "source_sha256", "duration_seconds")
        }
        projection["chunks"] = chunks
        # Stage non-entry pages first. No discoverable report exists until the
        # complete batch, all media and every recording page have been verified.
        pages.append(
            ArtifactWrite(
                "page-" + identity,
                "web/" + destination["page"],
                lambda value=projection: render(value, recordings, block.run_id),
                kind="html",
                required=False,
                revision=fingerprint(projection),
            )
        )
    for index, page in enumerate([*pages[1:], pages[0]]):
        receipt = publish_artifact_bundle(
            block, [page], receipt_path=f"{block.root}/replay-page-{index}.json"
        )
        if receipt["warnings"] or receipt.get("delivery_warnings"):
            raise ValueError("Playback page was not delivered")

    def handle():
        from mn_sdk_web_ui import static_run_report_handle

        return json.dumps(
            static_run_report_handle(
                block.store.run_dir,
                "web/index.html",
                title="Audio transcript",
                optional=True,
            )
        ).encode()

    publish_artifact_bundle(
        block,
        [
            ArtifactWrite(
                "web_ui",
                "web_ui.json",
                handle,
                kind="json",
                required=False,
                revision=fingerprint(recordings),
                mode=0o644,
            )
        ],
        receipt_path=block.root + "/replay-handle.json",
    )
