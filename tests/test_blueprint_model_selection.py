"""Exercise blueprint model contracts with the SDK's real model selection."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import mn_sdk.model_runtime as model_runtime
from mn_sdk.blueprints import read_blueprint, resolve_config
from mn_sdk.model_access.runtime import clear_runtime_model_cache, ensure_runtime_model


@pytest.mark.parametrize(
    (
        "blueprint_id",
        "vendor",
        "memory_mb",
        "remote_memory_mb",
        "expected",
        "selected_node",
    ),
    [
        ("vc_assistant", "apple", 16384, None, "gemma4:e2b", "local"),
        ("vc_assistant", "nvidia", 8192, None, "gemma4:e2b", "local"),
        ("research_assistant", "apple", 24576, None, "gemma4:e2b", "local"),
        ("research_assistant", "nvidia", 8192, None, "gemma4:e2b", "local"),
        (
            "research_assistant",
            "apple",
            24576,
            131072,
            "nemotron-3.5-lightning:latest",
            "remote",
        ),
        (
            "vc_assistant",
            "nvidia",
            131072,
            None,
            "nemotron-3.5-lightning:latest",
            "local",
        ),
        (
            "vc_assistant",
            "apple",
            16384,
            131072,
            "nemotron-3.5-lightning:latest",
            "remote",
        ),
        (
            "cctv_operator",
            "nvidia",
            131072,
            None,
            "nemotron-3.5-lightning:latest",
            "local",
        ),
        (
            "cctv_operator",
            "apple",
            16384,
            131072,
            "nemotron-3.5-lightning:latest",
            "remote",
        ),
    ],
)
@pytest.mark.parametrize("installed", [False, True])
def test_blueprint_model_selection_preserves_default_and_explicit_model_contracts(
    monkeypatch,
    blueprint_id,
    vendor,
    memory_mb,
    remote_memory_mb,
    expected,
    selected_node,
    installed,
):
    root = Path(__file__).resolve().parents[1]
    config = resolve_config(read_blueprint(root / blueprint_id)).data
    catalog_file = Path(model_runtime.__file__).with_name("model_catalog.json")
    catalog = {
        entry["id"]: entry for entry in json.loads(catalog_file.read_text())["models"]
    }
    monkeypatch.setattr(model_runtime, "load_model_catalog", lambda: catalog)
    prepared = []

    class Core:
        def get_resource(self):
            devices = [("local", vendor, memory_mb)]
            if remote_memory_mb is not None:
                devices.append(("remote", "nvidia", remote_memory_mb))
            return {
                "nodes": [
                    {
                        "name": name,
                        "status": "healthy",
                        "scheduling_eligible": True,
                        "devices": [
                            {
                                "kind": "gpu",
                                "type": "integrated_gpu"
                                if vendor == "apple"
                                else "gpu",
                                "vendor": vendor,
                                "memory_total_mb": memory_mb,
                                "memory_free_mb": memory_mb,
                            }
                        ],
                    }
                    for name, vendor, memory_mb in devices
                ]
            }

        def get_system_summary(self):
            return {
                "nodes": [
                    {
                        "name": node["name"],
                        "status": "healthy",
                        "scheduling_eligible": True,
                        "grpc_host": "127.0.0.1"
                        if node["name"] == "local"
                        else "192.0.2.2",
                        "native_sdk_grpc": {
                            "enabled": True,
                            "host": "127.0.0.1"
                            if node["name"] == "local"
                            else "192.0.2.2",
                            "port": 55052,
                        },
                    }
                    for node in self.get_resource()["nodes"]
                ]
            }

    class Native:
        def get_resource(self):
            return {
                "models": [{"id": expected, "model": catalog[expected]["model"]}]
                if installed
                else []
            }

        def prepare_runtime_model(self, request):
            prepared.append(request["id"])
            return {
                "status": "already_installed" if installed else "installed",
                "node": request["node"],
                "model": request["model"],
                "docker_model": request["model"],
                "gateway": {"host_api_base": "http://127.0.0.1:4000/v1"},
            }

    llm = config["llm"]
    llm = {
        **llm,
        **llm.get("configs", {}).get(llm.get("default_config", "primary"), {}),
    }
    authored_model = (
        "nemotron-3.5-lightning:latest"
        if blueprint_id == "cctv_operator"
        else "default"
    )
    assert llm["model"] == authored_model
    clear_runtime_model_cache()
    try:
        binding = ensure_runtime_model(
            "llm",
            llm["model"],
            provider=llm["provider"],
            backend=llm.get("backend", "auto"),
            context_size=llm.get("context_size"),
            control_client=Core(),
            client_factory=lambda **_: Native(),
            env={"MN_RUNTIME_MODEL_MANAGED": "1"},
        )
        assert binding.catalog_id == expected
        assert binding.api_model == authored_model
        assert binding.node == selected_node
        assert binding.selection["installed"] is installed
        assert binding.status == ("already_installed" if installed else "installed")
        assert prepared == [expected]
    finally:
        clear_runtime_model_cache()
