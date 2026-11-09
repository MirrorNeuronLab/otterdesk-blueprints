"""Optional offline comparison of captured source pages and committed OCR."""

import hashlib
import html
import json
from pathlib import Path
from urllib.parse import quote

from mn_sdk.blueprint.hooks import fingerprint, report_activity
from mn_sdk.blueprint.outputs import materialize_file, publish_artifact_bundle
from mn_sdk_common.publication import ArtifactWrite

from .previews import page_previews

ASSETS = Path(__file__).with_name("report_assets")
MAX_PREVIEW_TOTAL = 512 * 1024**2
MAX_HTML_BYTES = 32 * 1024**2


def render(record, files, summary):
    """Custom view using the shared report's external assets and browser API."""
    data = (
        json.dumps(
            {"document": record, "files": files, "summary": summary},
            ensure_ascii=False,
            allow_nan=False,
        )
        .replace("<", "\\u003c")
        .replace("&", "\\u0026")
    )
    identity = html.escape(record["source"], quote=True)
    csp = (
        "default-src 'none'; script-src 'self'; style-src 'self'; font-src 'self'; "
        "img-src 'self'; connect-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'"
    )
    page = f'''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="{html.escape(csp, quote=True)}">
<title>OCR report — {identity}</title>
<link rel="stylesheet" href="assets/report-components.css">
<link rel="stylesheet" href="assets/report-fonts.css">
<link rel="stylesheet" href="assets/report-template.css">
<link rel="stylesheet" href="assets/comparison.css">
<script defer src="assets/report-ui.js"></script><script defer src="assets/comparison.js"></script>
</head><body class="report vbg-report"><a class="skip" href="#report-main">Skip to results</a>
<header class="report-header"><div class="report-identity"><h1>OCR report</h1>
<span id="identity" title="{identity}">{identity}</span></div><div id="report-actions"></div></header>
<div class="report-root-layout"><div id="report-navigation"></div>
<main id="report-main" class="report-main" tabindex="-1">{(ASSETS / "content.html").read_text()}</main></div>
<div id="report-inspector-ui"></div><script id="report-data" type="application/json">{data}</script>
</body></html>'''.encode()
    if len(page) > MAX_HTML_BYTES:
        raise ValueError("Comparison report exceeds its byte limit")
    return page


def _publish(block, writes, key):
    receipt = publish_artifact_bundle(
        block, writes, receipt_path=block.root + "/comparison/" + key + ".json"
    )
    if receipt["warnings"] or receipt.get("delivery_warnings"):
        raise ValueError("Comparison assets could not be delivered")


def _bytes(block, ref, key):
    if ref["kind"] == "block_file":
        return materialize_file(
            block, ref, path=block.root + "/comparison-inputs/" + key
        ).read_bytes()
    return block.store.read_bytes(ref)


def publish_comparison(block, batch, inputs):
    try:
        _publish_comparison(block, batch, inputs)
    except Exception:
        # Presentation is optional; domain results were already published.
        block.check()
        report_activity(
            "OCR results saved. The comparison report could not be published.",
            kind="diagnostic",
            level="warning",
            step_id=block.step_id,
            run_dir=block.store.run_dir,
        )


def _publish_comparison(block, batch, inputs):
    from mn_web_report_skill import asset_bytes, asset_names
    from mn_sdk_web_ui import static_run_report_handle

    _publish(
        block,
        [
            ArtifactWrite(
                "asset-" + fingerprint(name),
                "web/assets/" + name,
                asset_bytes(name),
                kind="asset",
                required=False,
            )
            for name in asset_names()
        ]
        + [
            ArtifactWrite(
                "comparison-" + suffix,
                "web/assets/comparison." + suffix,
                (ASSETS / ("comparison." + suffix)).read_bytes(),
                kind="asset",
                required=False,
            )
            for suffix in ("css", "js")
        ],
        "assets",
    )
    # Start on a readable document, while retaining failed/skipped entries in Files.
    ordered = sorted(batch["files"], key=lambda record: record["status"] != "completed")
    files = [
        {
            "source": record["source"],
            "status": record["status"],
            "page": "index.html"
            if index == 0
            else fingerprint(record["source"]) + ".html",
        }
        for index, record in enumerate(ordered)
    ]
    files.extend(
        {**item, "status": "skipped", "page": None} for item in batch["skipped"]
    )
    summary = {
        key: batch[key] for key in ("completed_count", "failed_count", "skipped_count")
    }
    sources = {item["source"]: (item, prepared) for item, prepared in inputs}
    preview_bytes = 0
    entry_page = None
    for record, destination in zip(ordered, files):
        block.check()
        item, prepared = sources[record["source"]]
        identity = fingerprint(item["source"])
        original = "originals/" + identity + Path(item["source"]).suffix.lower()
        original_bytes = _bytes(block, item["file"], identity)
        if hashlib.sha256(original_bytes).hexdigest() != item["source_sha256"]:
            raise ValueError("Original preview source hash mismatch")
        _publish(
            block,
            [
                ArtifactWrite(
                    "original",
                    "web/" + original,
                    original_bytes,
                    kind="source",
                    required=False,
                )
            ],
            identity + "-original",
        )
        projection = {key: record[key] for key in ("source", "source_sha256", "status")}
        projection.update(
            original=original,
            pages=[],
            error=record.get("error"),
            converted=bool(prepared.get("input_sha256"))
            and prepared["input_sha256"] != item["source_sha256"],
        )
        if record["status"] == "completed":
            prefix = "documents/" + item["source"] + "/"
            result = block.store.read_path(prefix + "ocr_result.json")
            projection.update(
                input_sha256=result["input_sha256"],
                model_revision=result["model_revision"],
                warnings=result["warnings"],
                pages=result["pages"],
                text_url="../" + quote(prefix + "text.txt", safe="/"),
                json_url="../" + quote(prefix + "ocr_result.json", safe="/"),
            )
            try:
                data = _bytes(block, prepared["document"], identity + "-prepared")
                if hashlib.sha256(data).hexdigest() != result["input_sha256"]:
                    raise ValueError("OCR preview input hash mismatch")
                for number, png in page_previews(
                    data, prepared["suffix"], check=block.check
                ):
                    preview_bytes += len(png)
                    if preview_bytes > MAX_PREVIEW_TOTAL:
                        raise ValueError("Batch preview budget exhausted")
                    path = "previews/" + identity + "-" + str(number) + ".png"
                    _publish(
                        block,
                        [
                            ArtifactWrite(
                                "preview",
                                "web/" + path,
                                png,
                                kind="image",
                                required=False,
                            )
                        ],
                        identity + "-" + str(number),
                    )
                    projection["pages"][number - 1]["preview"] = path
            except Exception:
                block.check()
                projection["preview_note"] = (
                    "Some page previews are unavailable. Open the original file to compare."
                )
        page = ArtifactWrite(
            "page",
            "web/" + destination["page"],
            render(projection, files, summary),
            kind="html",
            required=False,
        )
        if destination["page"] == "index.html":
            entry_page = page
        else:
            _publish(block, [page], identity + "-page")
    # Publish the entry only after its linked assets and sibling pages exist.
    _publish(block, [entry_page], "index")
    handle = json.dumps(
        static_run_report_handle(
            block.store.run_dir, "web/index.html", title="OCR report", optional=True
        )
    ).encode()
    _publish(
        block,
        [
            ArtifactWrite(
                "web_ui", "web_ui.json", handle, kind="json", required=False, mode=0o644
            )
        ],
        "handle",
    )
