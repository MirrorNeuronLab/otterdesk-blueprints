"""Publish a self-contained view of the completed OpenUSD scene."""

import base64
import hashlib
import json
from pathlib import Path
from string import Template

from mn_sdk.blueprint.outputs import publish_artifact_bundle
from mn_sdk_common.publication import ArtifactWrite

ASSETS = Path(__file__).with_name("viewer")
TITLE = "LiDAR scene preview"
PAGE = "web/index.html"


def csp_hash(content):
    return base64.b64encode(hashlib.sha256(content.encode("utf-8")).digest()).decode("ascii")


def render_preview(report, projection):
    template = Template((ASSETS / "index.html").read_text(encoding="utf-8"))
    script = (ASSETS / "viewer.js").read_text(encoding="utf-8")
    style = (ASSETS / "viewer.css").read_text(encoding="utf-8")
    minimum, maximum = report["bounds_m"]
    dimensions = " × ".join(f"{high - low:,.2f}" for low, high in zip(minimum, maximum, strict=True))
    total = report["point_count"]
    shown = projection["count"]
    point_summary = f"{total:,} points" if shown == total else f"{shown:,} of {total:,} points"
    return template.substitute(
        title=TITLE,
        script_hash=csp_hash(script),
        style_hash=csp_hash(style),
        script=script,
        style=style,
        data=json.dumps(projection, allow_nan=False, separators=(",", ":")).replace("<", "\\u003c"),
        point_summary=point_summary,
        dimensions=f"{dimensions} m",
    ).encode("utf-8")


def publish_preview(block, report, projection):
    from mn_sdk_web_ui import static_run_report_handle

    receipt = publish_artifact_bundle(block, [
        ArtifactWrite("web_preview", PAGE, render_preview(report, projection), kind="html", required=False),
    ], receipt_path=block.root + "/preview.json")
    if receipt["warnings"] or receipt["delivery_warnings"]:
        raise OSError("The preview document could not be published.")
    handle = static_run_report_handle(block.store.run_dir, PAGE, title=TITLE)
    receipt = publish_artifact_bundle(block, [
        ArtifactWrite("web_ui", "web_ui.json", json.dumps(handle).encode("utf-8"), kind="json", required=False),
    ], receipt_path=block.root + "/preview-handle.json")
    if receipt["warnings"] or receipt["delivery_warnings"]:
        raise OSError("The preview handle could not be published.")
