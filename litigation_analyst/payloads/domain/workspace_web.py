"""Offline workspace publication. No service, CDN, implicit sharing or source execution."""
import base64
import hashlib
import html
import json
from pathlib import Path
import shutil

from mn_sdk.step_runtime import artifact_reference
from mn_sdk.blueprint_support import write_json


def render(workspace):
    assets = Path(__file__).with_name("workspace_assets")
    script = (assets / "workspace.js").read_text()
    style = (assets / "workspace.css").read_text()
    payload = json.dumps(workspace, ensure_ascii=False, allow_nan=False).replace("<", "\\u003c").replace("&", "\\u0026")
    script_hash = base64.b64encode(hashlib.sha256(script.encode()).digest()).decode()
    csp = f"default-src 'none'; script-src 'sha256-{script_hash}'; style-src 'unsafe-inline'; img-src 'self' data:; frame-src 'self'; object-src 'none'; connect-src 'none'; base-uri 'none'; form-action 'none'"
    return ("<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<meta http-equiv="Content-Security-Policy" content="{html.escape(csp, quote=True)}">'
        f'<title>{html.escape(workspace["title"])} · OtterDesk</title><style>{style}</style></head>'
        '<body><a class="skip" href="#content">Skip to investigation</a><div id="app"></div>'
        '<p id="notice" role="status" aria-live="polite"></p><dialog id="source-dialog"></dialog>'
        '<dialog id="review-dialog"></dialog><dialog id="export-dialog"></dialog>'
        f'<script id="workspace-data" type="application/json">{payload}</script><script>{script}</script></body></html>')


def publish(context, workspace):
    root = Path(context["run_dir"])
    # JSON is authoritative; optional rendering cannot invalidate verified outputs.
    (root / "case/workspace.json").write_text(json.dumps(workspace, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    refs = [artifact_reference("investigation_workspace", "case/workspace.json")]
    web = root / "web"
    try:
        page = render(workspace)
        maximum = context["config"].get("workspace", {}).get("max_page_bytes", 32*1024*1024)
        if type(maximum) is not int or maximum < 1 or len(page.encode()) > maximum:
            raise ValueError("Workspace page exceeds configured byte limit")
        web.mkdir(exist_ok=True)
        originals = web / "originals"
        # Rebuilding a permission projection must remove old copied originals.
        if originals.exists():
            shutil.rmtree(originals)
        originals.mkdir()
        for source in workspace["sources"]:
            if not source["original_included"]:
                continue
            original = root / "case/originals" / source["original_sha256"]
            if original.is_symlink() or hashlib.sha256(original.read_bytes()).hexdigest() != source["original_sha256"]:
                raise ValueError("Original source integrity verification failed")
            # Fixed extension prevents an imported HTML/SVG file from executing.
            suffix = ".pdf" if source["media_type"] == "application/pdf" else ".bin"
            shutil.copyfile(original, originals / (source["original_sha256"] + suffix))
        (web / "index.html").write_text(page, encoding="utf-8")
        page_path = (web / "index.html").resolve()
        handle = {"kind": "output", "adapter": "static_html", "title": workspace["title"],
            "path": str(page_path), "url": page_path.as_uri(), "metadata": {"renderer": "static_html", "optional": True}}
        write_json(root / "web_ui.json", handle)
        status = {"status": "Available", "path": "web/index.html", "handle": handle}
        refs.append(artifact_reference("interactive_investigation", "web/index.html"))
        refs.append(artifact_reference("web_ui_handle", "web_ui.json"))
    except (OSError, ValueError, TypeError) as error:
        # Do not retain a prior page with a broader source authorization.
        if web.exists():
            shutil.rmtree(web)
        (root / "web_ui.json").unlink(missing_ok=True)
        status = {"status": "Unavailable", "reason": type(error).__name__,
                  "affected": "Webpage preview; verified workspace JSON and draft remain available"}
    (root / "workspace_status.json").write_text(json.dumps(status), encoding="utf-8")
    return status, refs
