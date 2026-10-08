"""VC workers use the current document package without retired distributions."""

from __future__ import annotations

import builtins
import importlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_vc_intake_imports_and_reads_without_retired_document_packages(
    monkeypatch, tmp_path
):
    original_import = builtins.__import__
    retired = {"mn_document_reading_skill", "mn_pdf_extract_skill", "mn_llm_ocr_skill"}

    def current_packages_only(name, *args, **kwargs):
        if name.split(".", 1)[0] in retired:
            raise ModuleNotFoundError(name)
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", current_packages_only)
    monkeypatch.syspath_prepend(str(ROOT / "vc_assistant" / "payloads"))
    intake = importlib.import_module("domain.intake")
    documents = importlib.import_module("mn_docs_to_markdown_skill")
    assert intake.shared_document_paths is documents.document_paths
    assert intake.redact_common_pii is documents.redact_common_pii

    folder = tmp_path / "inputs"
    company = folder / "example-startup"
    company.mkdir(parents=True)
    source = company / "pitch.txt"
    source.write_text("Company: Example Startup\nContact: founder@example.test\n")
    records = intake.scan_documents(folder, {"source_context": {"enabled": False}})
    record = records["Example Startup"][0]
    assert record["sha256"] == documents.file_sha256(source)
    assert "[REDACTED-EMAIL]" in record["text_preview"]
    assert "founder@example.test" not in record["text_preview"]
