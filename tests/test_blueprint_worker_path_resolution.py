from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _load_runner(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_medical_deid_runner_resolves_config_from_docker_worker_attempt_root(monkeypatch, tmp_path):
    runner = _load_runner(
        "medical_deid_runner_path_test",
        ROOT / "medical_deid_record_intake_assistant" / "payloads" / "document_workflow" / "scripts" / "run_blueprint.py",
    )
    attempt_root = tmp_path / "runs" / "stage_medical_inputs" / "i1-a1-23108"
    script_path = attempt_root / "document_workflow" / "scripts" / "run_blueprint.py"
    config_path = attempt_root / "config" / "default.json"
    script_path.parent.mkdir(parents=True)
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        json.dumps(
            {
                "identity": {"blueprint_id": "medical_deid_record_intake_assistant"},
                "inputs": {"payload": {"document_folder": "docs", "output_folder": str(tmp_path / "out")}},
                "outputs": {"folder_path": str(tmp_path / "out")},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.delenv("MN_BLUEPRINT_CONFIG_PATH", raising=False)
    monkeypatch.delenv("MN_BLUEPRINT_BUNDLE_DIR", raising=False)
    monkeypatch.delenv("MN_BLUEPRINT_CONFIG_JSON", raising=False)
    monkeypatch.setattr(runner, "__file__", str(script_path))

    assert script_path.parents[3] != attempt_root
    assert runner.default_config_path() == config_path
    assert runner.resolve_blueprint_dir() == attempt_root
    assert runner.load_resolved_config()["identity"]["blueprint_id"] == "medical_deid_record_intake_assistant"


def test_property_deal_runner_uses_embedded_config_when_default_file_is_not_mounted(monkeypatch, tmp_path):
    runner = _load_runner(
        "property_deal_runner_path_test",
        ROOT / "property_deal_research_assistant" / "payloads" / "simulation_loop" / "scripts" / "run_blueprint.py",
    )
    attempt_root = tmp_path / "runs" / "collect_deal_context" / "i1-a1-23108"
    script_path = attempt_root / "simulation_loop" / "scripts" / "run_blueprint.py"
    script_path.parent.mkdir(parents=True)
    embedded_config = json.loads((ROOT / "property_deal_research_assistant" / "config" / "default.json").read_text(encoding="utf-8"))
    monkeypatch.delenv("MN_BLUEPRINT_CONFIG_PATH", raising=False)
    monkeypatch.delenv("MN_BLUEPRINT_BUNDLE_DIR", raising=False)
    monkeypatch.setenv("MN_BLUEPRINT_CONFIG_JSON", json.dumps(embedded_config))
    monkeypatch.setattr(runner, "__file__", str(script_path))

    assert script_path.parents[3] != attempt_root
    assert runner.default_config_path() == attempt_root / "config" / "default.json"
    result = runner.run_blueprint(
        inputs={"steps": 1, "seed": 77},
        config={"llm": {"mode": "fake"}},
        runs_root=tmp_path / "runs-out",
        run_id="property-embedded-config",
    )
    assert result["identity"]["blueprint_id"] == "property_deal_research_assistant"
    assert result["run"]["run_id"] == "property-embedded-config"
