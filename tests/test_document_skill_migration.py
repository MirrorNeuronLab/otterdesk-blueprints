"""Published blueprints depend only on the consolidated document capability."""

import ast
import builtins
import importlib
import json
from pathlib import Path

import pytest
from workspace_paths import companion_workspace

ROOT = Path(__file__).resolve().parents[1]
CATALOG = json.loads((ROOT / "index.json").read_text())
RETIRED_IMPORTS = {"mn_document_reading_skill", "mn_pdf_extract_skill", "mn_llm_ocr_skill"}
RETIRED_PACKAGES = {"mirrorneuron-document-reading-skill", "mirrorneuron-pdf-extract-skill", "mirrorneuron-llm-ocr-skill"}


def test_companion_catalog_has_only_the_consolidated_document_skill():
    skills = companion_workspace(ROOT) / "mn-skills"
    assert (skills / "docs_to_markdown_skill" / "pyproject.toml").is_file()
    for name in ("document_reading_skill", "pdf_extract_skill", "llm_ocr_skill"):
        assert not (skills / name).exists()


@pytest.mark.parametrize("blueprint", CATALOG)
def test_catalog_has_no_retired_document_dependencies_or_imports(blueprint):
    root = ROOT / blueprint
    for path in root.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            imports = ([node.module] if isinstance(node, ast.ImportFrom)
                       else [name.name for name in node.names] if isinstance(node, ast.Import) else [])
            assert not {name.split(".", 1)[0] for name in imports if name} & RETIRED_IMPORTS, path
    for path in [*root.rglob("*.json"), *root.rglob("requirements*.txt")]:
        assert not any(name in path.read_text() for name in RETIRED_PACKAGES), path


@pytest.mark.parametrize("blueprint", ["procurement_manager", "research_assistant"])
def test_packet_intake_runs_without_retired_document_skills(blueprint, monkeypatch, tmp_path):
    original_import = builtins.__import__

    def current_packages_only(name, *args, **kwargs):
        if name.split(".", 1)[0] in RETIRED_IMPORTS:
            raise ModuleNotFoundError(name)
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", current_packages_only)
    monkeypatch.syspath_prepend(str(ROOT / blueprint / "payloads"))
    inputs = importlib.import_module("domain.inputs")
    documents = importlib.import_module("mn_docs_to_markdown_skill")
    assert inputs.extract_document is documents.extract_document
    assert inputs.scan_document_packet is documents.scan_document_packet
    (tmp_path / "request.txt").write_text("A synthetic request with supporting evidence.")
    records, warnings = inputs.load_input_documents(tmp_path, {})
    assert len(records) == 1 and records[0]["status"] == "extracted"
    assert records[0]["text"] == "A synthetic request with supporting evidence."
    assert warnings == []
