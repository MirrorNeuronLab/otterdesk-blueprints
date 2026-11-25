from copy import deepcopy
from pathlib import Path

import pytest

from mn_sdk.blueprints import compile_blueprint, read_blueprint
from mn_sdk.workflow_placement import resolve_and_apply_workflow_placement


def runtime_node(name, memory, *, local):
    return {
        "name": name, "status": "healthy", "self": local, "scheduling_eligible": True,
        "coordination_store": {"identity": "test-cluster", "healthy": True, "writable_primary": True},
        "devices": [{"id": f"{name}-gpu", "kind": "gpu", "type": "integrated_gpu" if local else "nvidia/gpu",
                     "vendor": "apple" if local else "nvidia", "driver": "metal" if local else "cuda", "memory_total_mb": memory,
                     "memory_free_mb": memory}],
        "hardware": {
            "cpu": {"logical_processors": 16}, "memory": {"total_mb": memory},
            "disk": {"available_mb": 128 * 1024},
            "gpu": {"available": True, "count": 1, "vendor": "apple" if local else "nvidia",
                    "memory_total_mb": memory, "memory_free_mb": memory},
            "native_sdk_grpc": {"enabled": True, "target": f"{name}:55052",
                                "capabilities": ["resource_admission_v2", "docker_worker_prepare_v1", "docker_compose_prepare_v1"]},
        },
    }


@pytest.mark.parametrize("name,specialized", [("software_verifier_suite", False), ("cctv_operator", True)])
def test_owner_placement_uses_the_coworkers_declared_model(tmp_path, monkeypatch, name, specialized):
    monkeypatch.setenv("MN_HOME", str(tmp_path / "mn"))
    package = read_blueprint(Path(__file__).resolve().parents[1] / name)
    compiled = compile_blueprint(package).manifest
    model = package.manifest["model_requirement"]
    profile = compiled["policies"]["resource_allocation"]
    assert compiled["metadata"]["model_requirement"] == model
    assert profile["mode"] == "shared"
    small = runtime_node("mini", 24 * 1024, local=True)
    large = runtime_node("spark", 128 * 1024, local=False)

    def place(nodes):
        return resolve_and_apply_workflow_placement(
            deepcopy(compiled), resource_report={"nodes": nodes}, system_summary={"nodes": nodes}, env={}
        )

    if specialized:
        assert model == {"model": "nvidia/Cosmos3-Edge", "gpu_memory_mb": 49152}
        assert profile["devices"][0]["reservation_memory_mb"] == model["gpu_memory_mb"]
        assert place([small, large])["selected_node"] == "spark"
        with pytest.raises(RuntimeError, match="gpu_memory"):
            place([small])
    else:
        assert model == {"model": "default"}
        assert profile["shared_default_model"] and not profile.get("devices")
        assert place([small])["selected_node"] == "mini"
        small.pop("devices")
        small["hardware"].pop("gpu")
        assert place([small])["selected_node"] == "mini"
