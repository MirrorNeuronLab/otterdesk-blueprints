from __future__ import annotations

from pathlib import Path

from mn_sdk.blueprints import blueprint_definition, read_blueprint, resolve_config

ROOT = Path(__file__).resolve().parents[1]


def test_purchasing_manager_runner_uses_embedded_config_when_default_file_is_not_mounted(
    monkeypatch, tmp_path
):
    blueprint = ROOT / "purchasing_manager"
    manifest = blueprint_definition(read_blueprint(blueprint / "manifest.json"))
    config = resolve_config(read_blueprint(blueprint)).data
    runtime_source = (blueprint / "payloads" / "runtime" / "runtime.py").read_text(
        encoding="utf-8"
    )
    runtime_services = (
        blueprint / "payloads" / "domain" / "runtime_services.py"
    ).read_text(encoding="utf-8")

    assert manifest["config"]["embed"] is True
    assert "llm" in manifest["config"]["data"]
    assert config["inputs"]["payload"]["input_folder"] == "@/examples/sample_inputs"
    assert "create_blueprint_run_context" in runtime_services
    assert "@/" not in runtime_services
    assert "domain.runtime_services" in runtime_source
