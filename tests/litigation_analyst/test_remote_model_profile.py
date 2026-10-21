"""Litigation uses the registered provider and its declared request budget."""
# ruff: noqa: F811 -- Imported pytest fixtures are requested by parameter name.
import json
from pathlib import Path

import pytest
from mn_sdk.blueprint_runtime import blueprint_runtime_environment
from mn_sdk.blueprints import (
    blueprint_definition,
    catalog_record,
    read_blueprint,
    resolve_config,
)
from mn_sdk.model_registry import (
    add_registered_models,
    load_provider_definition,
    set_registered_default_model,
)
from test_litigation_analyst import modules  # noqa: F401 -- Module-local pytest fixture.

ROOT = Path(__file__).resolve().parents[2] / "litigation_analyst"


@pytest.mark.parametrize("provider", ["openai", "openrouter", "openai-compatible"])
def test_registered_remote_default_uses_any_gpu_and_16gb(tmp_path, monkeypatch, provider):
    monkeypatch.setenv("MN_HOME", str(tmp_path / "runtime"))
    package = read_blueprint(ROOT)
    baseline = catalog_record(package, ROOT.name)["requirements"]
    assert baseline["gpu"]["min_memory_mb"] == 49152
    path = tmp_path / "remote.json"
    path.write_text(json.dumps({"provider": {provider: {
        "options": {"baseURL": "http://remote.test:8000/v1"},
        "models": {"remote/custom-model": {}},
    }}}))
    add_registered_models(load_provider_definition(path))
    set_registered_default_model("remote/custom-model")
    config = resolve_config(package)
    requirements = blueprint_definition(package, config)["requirements"]
    assert requirements["gpu"] == {"min_count": 1, "enforcement": "hard"}
    assert requirements["memory"] == {"min_gb": 16}
    assert requirements["cpu"] == baseline["cpu"]
    assert requirements["disk"] == baseline["disk"]
    assert config.data["resources"] == requirements
    assert catalog_record(package, ROOT.name)["requirements"] == requirements
    environment = blueprint_runtime_environment(ROOT, config=config.data, include_docker_worker_runtime_env=True)
    assert environment["MN_LLM_PROVIDER"] == "litellm"
    assert environment["MN_LLM_MODEL"] == "default"
    assert environment.get("MN_RUNTIME_MODEL_MANAGED") != "1"
    local = resolve_config(package, {"llm": {"model": "local/chat"}})
    assert blueprint_definition(package, local)["requirements"] == baseline


@pytest.mark.parametrize("selection,expected", [("default", "configured/remote"), ("explicit/model", "explicit/model")])
def test_relationship_extractor_inherits_provider_binding(modules, monkeypatch, tmp_path, selection, expected):
    from domain.relationship_index import _model
    from mn_sdk.llm import LLMClient
    original = LLMClient(model="configured/remote", provider="litellm", api_base="http://managed.test/v1")
    monkeypatch.setattr(LLMClient, "from_env", lambda **kwargs: original)
    from litigation_native_test_support import block_context
    native = block_context({'run_dir':tmp_path / 'run', "config": {"source_relationships": {"model": selection}}})
    current, model, revision = _model(native, None)
    assert model == expected
    assert current.provider == original.provider
    assert current.api_base == original.api_base
    assert revision is None


def test_investigation_admission_and_dispatch_share_configured_output_reserve(modules, monkeypatch, tmp_path):
    from domain import round_model
    frozen = {"config": {"context_memory": {"policy": {"window_tokens": 32768, "output_tokens": 8192}}},
              "payload": {"goal": "Compare the authorization and reversal evidence"},
              "memory_scope": {"job_id": "job", "run_id": "run"}}
    observed = []
    monkeypatch.setattr(round_model, "prompt", lambda *args: ("policy", {"evidence": []}))
    monkeypatch.setattr(round_model, "runtime_text_memory", lambda *args, **kwargs: None)
    def capacity(*args, **kwargs):
        observed.append(("admission", kwargs["policy"].output_tokens, kwargs["max_tokens"]))
        return 12000
    def decision(*args, **kwargs):
        observed.append(("dispatch", kwargs["policy"].output_tokens, kwargs["max_tokens"]))
        return {"result": "recorded"}
    monkeypatch.setattr(round_model, "json_decision_capacity", capacity)
    monkeypatch.setattr(round_model, "durable_json_decision", decision)
    assert round_model.evidence_room(frozen, "assess", "review", {}, {}) == 12000
    assert round_model.complete(tmp_path, frozen, "assessment", "assess", "review", {}, {}) == {"result": "recorded"}
    assert observed == [("admission", 8192, 8192), ("admission", 8192, 8192), ("dispatch", 8192, 8192)]



def test_investigation_preserves_the_configured_remote_provider(modules, monkeypatch, tmp_path):
    from domain import round_model
    from mn_sdk.llm import LLMClient
    client = LLMClient(model="default", provider="litellm", api_base="http://managed.test/v1")
    frozen = {"config": {"context_memory": {"policy": {"window_tokens": 32768, "output_tokens": 8192}}},
              "payload": {"goal": "Review the supplied authorization records"},
              "memory_scope": {"job_id": "job", "run_id": "run"}}
    monkeypatch.setattr(round_model, "prompt", lambda *args: ("policy", {}))
    monkeypatch.setattr(round_model, "runtime_text_memory", lambda *args, **kwargs: None)
    monkeypatch.setattr(round_model, "json_decision_capacity", lambda *args, **kwargs: 10000)

    def decide(*args, **kwargs):
        assert kwargs["client"] is client
        assert kwargs["client"].provider == "litellm"
        assert kwargs["client"].api_base == "http://managed.test/v1"
        return {"result": "recorded"}

    monkeypatch.setattr(round_model, "durable_json_decision", decide)
    assert round_model.complete(tmp_path, frozen, "review", "review", "inspect", {}, {}, client) == {"result": "recorded"}
