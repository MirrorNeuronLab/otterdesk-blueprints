"""Verify the optional UI against committed results, not another inference."""

import hashlib
import json
import re

import pytest
from PIL import Image
from test_ocr import ROOT, batch, pdf_bytes
from test_ocr import worker as worker


def projection(path):
    source = path.read_text()
    return json.loads(
        re.search(
            r'<script id="report-data" type="application/json">(.*?)</script>',
            source,
            re.S,
        )[1]
    )


def test_report_contains_captured_original_exact_result_and_portable_assets(worker):
    original = (worker.folder / "source.png").read_bytes()
    worker.execute()
    entry = worker.store.path("web/index.html")
    view = projection(entry)
    document = view["document"]
    assert (entry.parent / document["original"]).read_bytes() == original
    assert document["source_sha256"] == hashlib.sha256(original).hexdigest()
    page = document["pages"][0]
    preview = page.pop("preview")
    assert page == worker.responses[0]["pages"][0]
    with Image.open(entry.parent / preview) as image:
        assert image.size == (80, 30)
    assert (
        worker.store.read_path("documents/source.png/ocr_result.json")
        == worker.responses[0]
    )
    assert len(batch(worker)["files"][0]["artifacts"]) == 3
    assert (entry.parent / "assets/vendor/Geist-Variable.woff2").is_file()
    handle = json.loads(worker.store.path("web_ui.json").read_text())
    assert handle["adapter"] == "static_html"
    assert "index.html" in json.dumps(handle)
    (worker.folder / "source.png").write_bytes(b"changed after capture")
    worker.execute()
    assert len(worker.calls) == 1
    assert (entry.parent / document["original"]).read_bytes() == original


def test_pdf_office_failure_and_skipped_navigation(worker, monkeypatch):
    (worker.folder / "pages.pdf").write_bytes(pdf_bytes(2))
    (worker.folder / "slides.pptx").write_bytes(b"synthetic office bytes")
    (worker.folder / "broken.pdf").write_bytes(b"%PDF-corrupt")
    (worker.folder / "notes.txt").write_text("Unsupported")
    monkeypatch.setattr("domain.documents.render_office", lambda *a, **k: pdf_bytes(3))
    worker.execute()
    entry = worker.store.path("web/index.html")
    view = projection(entry)
    assert view["summary"] == {
        "completed_count": 3,
        "failed_count": 1,
        "skipped_count": 1,
    }
    assert view["files"][0]["status"] == "completed"
    for file in view["files"]:
        if file["page"] is None:
            assert file["status"] == "skipped"
            continue
        document = projection(entry.parent / file["page"])["document"]
        if file["source"] == "slides.pptx":
            assert document["converted"] and len(document["pages"]) == 3
            assert (
                entry.parent / document["original"]
            ).read_bytes() == b"synthetic office bytes"
        if file["source"] == "pages.pdf":
            assert len(document["pages"]) == 2
        if file["status"] == "failed":
            assert document["error"] and not document["pages"]
        for page in document["pages"]:
            with Image.open(entry.parent / page["preview"]) as image:
                assert image.width > 0 and max(image.size) <= 1600


@pytest.mark.parametrize("stage", ["render", "assets", "handle"])
def test_optional_report_failure_cannot_lose_authoritative_results(
    worker, monkeypatch, stage
):
    import domain.reporting as reporting

    publish = reporting._publish

    def fail(*args, **kwargs):
        raise RuntimeError("Synthetic UI failure")

    def publish_or_fail(block, writes, key):
        assert block.store.path("ocr_result.json").is_file()
        if key == stage:
            fail()
        return publish(block, writes, key)

    if stage == "render":
        monkeypatch.setattr(reporting, "render", fail)
    else:
        monkeypatch.setattr(reporting, "_publish", publish_or_fail)
    output = worker.execute()
    assert output.outputs
    assert batch(worker)["completed_count"] == 1
    assert worker.store.path("documents/source.png/text.txt").is_file()
    assert not worker.store.path("web_ui.json").exists()


def test_preview_failure_retains_text_and_original_download(worker, monkeypatch):
    monkeypatch.setattr("domain.reporting.MAX_PREVIEW_TOTAL", 1)
    worker.execute()
    view = projection(worker.store.path("web/index.html"))["document"]
    assert "unavailable" in view["preview_note"]
    assert view["pages"][0]["text"] == worker.responses[0]["pages"][0]["text"]
    assert worker.store.path("web/" + view["original"]).is_file()
    assert worker.store.path("web_ui.json").is_file()


def test_report_treats_untrusted_text_as_data(worker):
    from domain.reporting import render

    text = '</script><img src=x onerror="alert(1)">& unsafe'
    page = render({"source": text, "pages": [{"text": text}]}, [], {})
    assert b"<img src=x" not in page
    assert b"\\u003c/script>" in page
    assert b"connect-src &#x27;none&#x27;" in page


def test_default_downloads_and_optional_static_ui_contract():
    config = json.loads((ROOT / "config/default.json").read_text())
    assert config["outputs"]["folder_path"] == "~/Downloads/nvidia-ocr"
    artifacts = json.loads((ROOT / "contracts.json").read_text())["outputs"][
        "artifacts"
    ]
    assert all(
        not item["required"]
        for item in artifacts
        if item["artifact_id"].startswith("web")
    )
    ui = json.loads((ROOT / "extensions/ui.json").read_text())["web_ui"]
    assert ui["enabled"] and ui["adapter"] == "static_html"
