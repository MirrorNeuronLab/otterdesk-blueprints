"""Offline browser fixture, with explicitly synthetic OCR text and regions."""

import json
from pathlib import Path
import shutil
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "payloads"))
from domain.reporting import ASSETS, render
from mn_web_report_skill import write_assets


def write_fixture(root):
    root = Path(root).resolve()
    web = root / "web"
    write_assets(web / "assets")
    for suffix in ("js", "css"):
        shutil.copyfile(
            ASSETS / ("comparison." + suffix), web / ("assets/comparison." + suffix)
        )
    (web / "originals").mkdir()
    (web / "previews").mkdir()
    original = (
        Path(__file__).resolve().parents[1] / "examples/sample_inputs/stock_gs200.jpg"
    )
    shutil.copyfile(original, web / "originals/sample.jpg")
    shutil.copyfile(original, web / "previews/sample.jpg")
    text = (
        'Synthetic Nasdaq & AMEX\n</script><img src=x onerror="window.injected=true">'
    )
    regions = [
        {
            "text": line,
            "confidence": 0.9,
            "bbox": [0.05, 0.15 + i * 0.2, 0.9, 0.3 + i * 0.2],
        }
        for i, line in enumerate(text.splitlines())
    ]
    pages = [
        {
            "page_number": 1,
            "width": 626,
            "height": 580,
            "text": text,
            "regions": regions,
            "preview": "previews/sample.jpg",
        },
        {
            "page_number": 2,
            "width": 626,
            "height": 580,
            "text": "Page two text",
            "regions": [
                {
                    "text": "Page two text",
                    "confidence": 0.8,
                    "bbox": [0.1, 0.1, 0.7, 0.2],
                }
            ],
            "preview": "previews/sample.jpg",
        },
    ]
    files = [
        {"source": "Newspaper.jpg", "status": "completed", "page": "index.html"},
        {
            "source": "LongNestedSourceName/" * 10 + "empty.docx",
            "status": "completed",
            "page": "empty.html",
        },
        {"source": "broken.pdf", "status": "failed", "page": "failed.html"},
        {"source": "notes.txt", "status": "skipped", "page": None},
    ]
    record = {
        "source": files[0]["source"],
        "source_sha256": "a" * 64,
        "input_sha256": "a" * 64,
        "model_revision": "b" * 40,
        "status": "completed",
        "converted": False,
        "original": "originals/sample.jpg",
        "pages": pages,
        "warnings": [],
        "text_url": "../documents/sample/text.txt",
        "json_url": "../documents/sample/ocr_result.json",
    }
    summary = {"completed_count": 2, "failed_count": 1, "skipped_count": 1}
    (root / "documents/sample").mkdir(parents=True)
    (root / "documents/sample/text.txt").write_text(text + "\nPage two text")
    (root / "documents/sample/ocr_result.json").write_text(json.dumps(record))
    (web / "index.html").write_bytes(render(record, files, summary))
    empty = {
        **record,
        "source": files[1]["source"],
        "converted": True,
        "pages": [{**pages[0], "text": "", "regions": []}],
    }
    (web / "empty.html").write_bytes(render(empty, files, summary))
    failed = {
        **record,
        "source": "broken.pdf",
        "status": "failed",
        "pages": [],
        "error": "Invalid PDF document",
    }
    (web / "failed.html").write_bytes(render(failed, files, summary))


if __name__ == "__main__":
    write_fixture(sys.argv[1])
