"""Offline workspace publication. No service, CDN, implicit sharing or source execution."""
import hashlib
import json
from pathlib import Path
import shutil

from mn_sdk.step_runtime import artifact_reference
from mn_sdk.blueprint_support import write_json
from mn_web_report_skill import render_document


def render(workspace, *, max_bytes=32*1024*1024):
    assets = Path(__file__).with_name("workspace_assets")
    script = "\n".join((assets / name).read_text() for name in ("navigation.js", "workspace.js", "reading.js"))
    style = (assets / "workspace.css").read_text() + (assets / "report-domain.css").read_text()
    return render_document(title="Litigation review", identity=workspace.get("matter_scope", {}).get("parties") and " / ".join(workspace["matter_scope"]["parties"]) or workspace["title"],
        content_html='<div id="app"></div>'
        '<p id="notice" role="status" aria-live="polite"></p>'
        '<dialog id="review-dialog"></dialog><dialog id="export-dialog"></dialog>',
        script=script, style=style, data=workspace, data_id="workspace-data", max_bytes=max_bytes,
        description="Draft for attorney review · Source records, model assessment and human review remain distinct.")


def publish(context, workspace):
    root = Path(context.store.run_dir)
    # JSON is authoritative; optional rendering cannot invalidate verified outputs.
    (root / "case/workspace.json").write_text(json.dumps(workspace, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    refs = [artifact_reference("investigation_workspace", "case/workspace.json")]
    web = root / "web"
    try:
        from .workspace_review import attach
        workspace = attach(workspace)
        (root / "case/workspace.json").write_text(json.dumps(workspace, ensure_ascii=False, allow_nan=False), encoding="utf-8")
        maximum = context.config.get("workspace", {}).get("max_page_bytes", 32*1024*1024)
        page = render(workspace, max_bytes=maximum)
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
    except (OSError, ValueError, TypeError, RuntimeError, KeyError) as error:
        # Do not retain a prior page with a broader source authorization.
        if web.exists():
            shutil.rmtree(web)
        (root / "web_ui.json").unlink(missing_ok=True)
        status = {"status": "Unavailable", "reason": type(error).__name__,
                  "affected": "Webpage preview; verified workspace JSON and draft remain available"}
    (root / "workspace_status.json").write_text(json.dumps(status), encoding="utf-8")
    return status, refs
