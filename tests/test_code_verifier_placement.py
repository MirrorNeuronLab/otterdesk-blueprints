from copy import deepcopy
from pathlib import Path

import pytest

from mn_sdk.blueprints import compile_blueprint, read_blueprint
from mn_sdk.workflow_placement import resolve_and_apply_workflow_placement


def runtime_node(name, memory, *, local):
    return {
        "name": name, "status": "healthy", "self": local, "scheduling_eligible": True,
        "coordination_store": {"identity": "test-cluster", "healthy": True, "writable_primary": True},
        "devices": [{"id": f"{name}-gpu", "kind": "gpu", "type": "integrated_gpu" if local else "gpu",
                     "vendor": "apple" if local else "nvidia", "memory_total_mb": memory,
                     "memory_free_mb": memory}],
        "hardware": {
            "cpu": {"logical_processors": 16}, "memory": {"total_mb": memory},
            "disk": {"available_mb": 128 * 1024},
            "gpu": {"available": True, "count": 1, "vendor": "apple" if local else "nvidia",
                    "memory_total_mb": memory, "memory_free_mb": memory},
            "native_sdk_grpc": {"enabled": True, "target": f"{name}:55052",
                                "capabilities": ["exclusive_run_v1"]},
        },
    }


@pytest.mark.parametrize("spark_available", [True, False])
def test_code_verifier_requires_large_accelerator_before_placement(tmp_path, monkeypatch, spark_available):
    monkeypatch.setenv("MN_HOME", str(tmp_path / "mn"))
    package = read_blueprint(Path(__file__).resolve().parents[1] / "code_verifier")
    manifest = deepcopy(compile_blueprint(package).manifest)
    assert manifest["requirements"]["gpu"]["min_memory_mb"] == 48 * 1024
    nodes = [runtime_node("mini", 24 * 1024, local=True)]
    if spark_available:
        nodes.append(runtime_node("spark", 128 * 1024, local=False))
    options = {"resource_report": {"nodes": nodes}, "system_summary": {"nodes": nodes}, "env": {}}

    if not spark_available:
        with pytest.raises(RuntimeError, match="gpu_memory"):
            resolve_and_apply_workflow_placement(manifest, **options)
        return

    placement = resolve_and_apply_workflow_placement(manifest, **options)
    assert placement["selected_node"] == "spark"
    assert placement["requirements"]["min_gpu_memory_mb"] == 48 * 1024
    for worker in manifest["agents"]["nodes"]:
        assert any(constraint.get("attribute") == "node.name" and constraint.get("value") == "spark"
                   for constraint in worker["constraints"])
