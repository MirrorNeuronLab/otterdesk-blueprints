from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

def test_purchase_research_runner_uses_embedded_config_when_default_file_is_not_mounted(monkeypatch, tmp_path):
    blueprint = ROOT / "purchase_research_assistant"
    manifest = json.loads((blueprint / "manifest.json").read_text(encoding="utf-8"))
    config = json.loads((blueprint / "config" / "default.json").read_text(encoding="utf-8"))
    runtime_source = (blueprint / "payloads" / "runtime" / "runtime.py").read_text(encoding="utf-8")
    runtime_services = (blueprint / "payloads" / "domain" / "runtime_services.py").read_text(encoding="utf-8")

    assert manifest["config"]["embed"] is True
    assert "llm" in manifest["config"]["manifest_defaults"]
    assert config["inputs"]["payload"]["input_folder"] == "@/examples/sample_inputs"
    assert "create_blueprint_run_context" in runtime_services
    assert "@/" not in runtime_services
    assert "domain.runtime_services" in runtime_source
