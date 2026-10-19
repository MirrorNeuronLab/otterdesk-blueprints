"""The advisor uses the shared resource profile for every remote default."""

import json
from pathlib import Path

import pytest

from mn_sdk.blueprints import blueprint_definition, catalog_record, read_blueprint, resolve_config
from mn_sdk.blueprint_runtime import blueprint_runtime_environment
from mn_sdk.model_registry import add_registered_models, load_provider_definition, set_registered_default_model


ROOT = Path(__file__).resolve().parents[2] / "software_architecture_advisor"


@pytest.mark.parametrize("provider", ["openai", "openrouter", "openai-compatible"])
def test_remote_provider_default_relaxes_only_the_advisor_model_hardware(tmp_path, monkeypatch, provider):
    monkeypatch.setenv("MN_HOME", str(tmp_path / "runtime"))
    package = read_blueprint(ROOT)
    baseline = catalog_record(package, ROOT.name)["requirements"]
    assert baseline["gpu"]["min_memory_mb"] == 49152
    definition = tmp_path / "provider.json"
    definition.write_text(json.dumps({"provider": {provider: {
        "options": {"baseURL": "http://remote.test:8000/v1"},
        "models": {"remote/custom-model": {}},
    }}}))
    add_registered_models(load_provider_definition(definition))
    set_registered_default_model("remote/custom-model")

    config = resolve_config(package)
    requirements = catalog_record(package, ROOT.name)["requirements"]
    assert requirements["gpu"] == {"min_count": 1, "enforcement": "hard"}
    assert requirements["memory"] == {"min_gb": 16}
    assert requirements["cpu"] == baseline["cpu"]
    assert requirements["disk"] == baseline["disk"]
    assert config.data["opencode"]["model"] == "mn/default"
    assert config.data["resources"] == requirements
    assert blueprint_definition(package, config)["requirements"] == requirements

    explicit_local = resolve_config(package, {"opencode": {"model": "mn/local/chat"}})
    assert blueprint_definition(package, explicit_local)["requirements"] == baseline


def test_remote_default_is_projected_to_the_gateway_without_local_llm_preparation(tmp_path, monkeypatch):
    test_remote_provider_default_relaxes_only_the_advisor_model_hardware(tmp_path, monkeypatch, "openai-compatible")
    package = read_blueprint(ROOT)
    config = resolve_config(package)
    environment = blueprint_runtime_environment(ROOT, config=config.data, include_docker_worker_runtime_env=True)
    assert environment["MN_LLM_PROVIDER"] == "litellm"
    assert environment["MN_LLM_MODEL"] == "default"
    assert environment.get("MN_RUNTIME_MODEL_MANAGED") != "1"


def test_opencode_remote_default_uses_the_advertised_gateway_host(monkeypatch):
    from domain.opencode_models import prepare_gateway
    monkeypatch.setenv("MN_LLM_PROVIDER", "litellm")
    monkeypatch.setenv("MN_LLM_API_BASE", "http://mn-litellm-proxy:4000/v1")
    monkeypatch.setenv("MN_SELECTED_RUNTIME_NODE", "mirror_neuron@10.0.4.27")
    def unexpected_prepare(*args, **kwargs):
        pytest.fail("A remote provider must not prepare a local LLM")
    monkeypatch.setattr("mn_sdk.model_access.runtime._prepare_managed_binding", unexpected_prepare)
    descriptor = prepare_gateway({"model": "mn/default"})
    assert descriptor["api_base"] == "http://10.0.4.27:4000/v1"
    assert descriptor["model"] == "default"
    assert descriptor["node"] == "mirror_neuron@10.0.4.27"
