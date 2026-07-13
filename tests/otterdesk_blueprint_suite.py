from __future__ import annotations

import importlib.util
import json
import os
import py_compile
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
SDK_SRC = WORKSPACE / "mn-python-sdk"
SUPPORT_SRC = WORKSPACE / "mn-skills" / "blueprint_support_skill" / "src"
AGENTS_ROOT = WORKSPACE / "mn-agents"
if str(SDK_SRC) not in sys.path:
    sys.path.insert(0, str(SDK_SRC))
if str(SUPPORT_SRC) not in sys.path:
    sys.path.insert(0, str(SUPPORT_SRC))

FOLDER_INPUT_FIELDS = {
    "drug_discovery_research_assistant": {"input_folder", "output_folder"},
    "financial_advisor": {"document_folder", "input_folder", "output_folder"},
    "generic_customer_service_voice_coworker": {"input_folder", "output_folder"},
    "medical_deid_record_intake_assistant": {"document_folder", "output_folder"},
    "legal_assistant": {"document_folder", "input_folder", "output_folder"},
    "purchase_research_assistant": {"input_folder", "output_folder"},
    "safety_video_analyser": {"input_folder", "output_folder"},
    "vc_assistant": {"document_folder", "output_folder"},
    "video_watch_assistant": {"input_folder", "output_folder"},
}

from mn_blueprint_support import render_manifest_agent_templates
from mn_blueprint_support.experience import (
    FINAL_ARTIFACT_REQUIRED_FIELDS,
    HUMAN_CONTROL_MODES,
    STANDARD_OBSERVABILITY_PANELS,
    STATUS_PHASES,
)
from mn_blueprint_support.openshell_network import (
    build_openshell_network_policy,
    endpoint_from_uri,
    write_openshell_network_policy,
)
from mn_blueprint_support.workflow_manifest import (
    run_workflow_manifest_file,
    validate_workflow_manifest,
)


def _pid_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _wait_until(predicate, timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.1)
    return predicate()


def _manifest_paths() -> list[Path]:
    return sorted(path / "manifest.json" for path in ROOT.iterdir() if (path / "manifest.json").exists())


def _indexed_blueprints() -> list[dict]:
    return json.loads((ROOT / "index.json").read_text())


def _indexed_non_vc_blueprints() -> list[dict]:
    return [
        entry
        for entry in _indexed_blueprints()
        if entry["id"] not in {"vc_assistant", "gtm_ai_workflow"}
    ]


def _contains_key(value, target: str) -> bool:
    if isinstance(value, dict):
        return any(key == target or _contains_key(item, target) for key, item in value.items())
    if isinstance(value, list):
        return any(_contains_key(item, target) for item in value)
    return False


def _json_strings(value, path: tuple[str, ...] = ()):
    if isinstance(value, dict):
        for key, item in value.items():
            yield from _json_strings(item, (*path, str(key)))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _json_strings(item, (*path, str(index)))
    elif isinstance(value, str):
        yield path, value


def _assert_directory_path_metadata(spec: dict, context: object) -> None:
    assert spec.get("type") == "local_path", context
    assert spec.get("path_kind") == "directory", context


def _default_input_folder(blueprint_id: str) -> str:
    return f"{blueprint_id}/examples/sample_inputs"


def _default_output_folder(blueprint_id: str) -> str:
    if blueprint_id == "vc_assistant":
        return f"~/Downloads/{blueprint_id}"
    return f"~/Download/{blueprint_id}"


def _flow_nodes(manifest: dict) -> list[dict]:
    nodes = manifest.get("agents", {}).get("nodes", [])
    return nodes if isinstance(nodes, list) else []


def _flow_edges(manifest: dict) -> list[dict]:
    edges = manifest.get("agents", {}).get("edges", [])
    return edges if isinstance(edges, list) else []


def _agent_entrypoints(manifest: dict) -> list[str]:
    entrypoints = manifest.get("agents", {}).get("entrypoints", [])
    return entrypoints if isinstance(entrypoints, list) else []


def _template_nodes(manifest: dict) -> list[dict]:
    nodes = manifest.get("metadata", {}).get("agent_templates", {}).get("nodes", [])
    return nodes if isinstance(nodes, list) else []


def _node_config(node: dict) -> dict:
    config = node.get("config")
    if isinstance(config, dict):
        return config
    config = node.get("with")
    return config if isinstance(config, dict) else {}


def _is_workflow_manifest(manifest: dict) -> bool:
    return manifest.get("apiVersion") == "mn.workflow/v1" and isinstance(manifest.get("workflow", {}).get("steps"), list)


def _runtime_worker_ids(manifest: dict) -> list[str]:
    workers: list[str] = []
    for binding in ((manifest.get("runtime") or {}).get("bindings") or {}).values():
        for worker in binding.get("workers") or []:
            if isinstance(worker, dict) and worker.get("id"):
                workers.append(worker["id"])
    return workers


GPU_HARD_REQUIREMENT = {
    "min_count": 1,
    "vendor": "nvidia",
    "driver": "cuda",
    "min_api_version": "12.0",
    "api_version_operator": ">=",
    "min_memory_mb": 49152,
    "memory_operator": ">=",
    "enforcement": "hard",
}


GPU_WORKER_DEVICE_REQUIREMENT = {
    "vendor": "nvidia",
    "driver": "cuda",
    "min_api_version": "12.0",
    "api_version_operator": ">=",
    "min_memory_mb": 49152,
    "memory_operator": ">=",
}


SKILL_DEPENDENCY_VERSION = "1.2.7"
SKILL_DEPENDENCY_VERSION_OVERRIDES = {
    "mirrorneuron-rag-skill": "1.2.14",
}
IMPORT_MARKER_PACKAGES = {
    "mn_blueprint_support": "mirrorneuron-blueprint-support-skill",
    "mn_litellm_communicate_skill": "mirrorneuron-litellm-communicate-skill",
    "mn_llm_ocr_skill": "mirrorneuron-llm-ocr-skill",
    "mn_w3m_browser_skill": "mirrorneuron-w3m-browser-skill",
    "mn_web_browser_skill": "mirrorneuron-web-browser-skill",
    "mn_rag_skill": "mirrorneuron-rag-skill",
    "mn_websocket_stream_skill": "mirrorneuron-websocket-stream-skill",
    "mn_evidence_engine_skill": "mirrorneuron-evidence-engine-skill",
    "mn_actor_review_skill": "mirrorneuron-actor-review-skill",
    "mn_client_report_skill": "mirrorneuron-client-report-skill",
    "mn_document_reading_skill": "mirrorneuron-document-reading-skill",
    "mn_public_research_orchestrator_skill": "mirrorneuron-public-research-orchestrator-skill",
    "mn_scoring_framework_skill": "mirrorneuron-scoring-framework-skill",
    "mn_autonomous_research_skill": "mirrorneuron-autonomous-research-skill",
}
SKILL_NAME_PACKAGES = {
    "llm_ocr_skill": "mirrorneuron-llm-ocr-skill",
    "rag_skill": "mirrorneuron-rag-skill",
    "w3m_browser_skill": "mirrorneuron-w3m-browser-skill",
    "web_browser_skill": "mirrorneuron-web-browser-skill",
    "websocket_stream": "mirrorneuron-websocket-stream-skill",
}
BLUEPRINT_TRANSITIVE_SKILL_PACKAGES = {
    "financial_advisor": {"mirrorneuron-litellm-communicate-skill"},
    "vc_assistant": {"mirrorneuron-litellm-communicate-skill"},
}


def _completion_threshold(value) -> bool:
    if isinstance(value, int):
        return value > 0
    if isinstance(value, str):
        return value.isdigit() and int(value) > 0
    return False


def _expected_skill_dependency_packages(blueprint_dir: Path) -> set[str]:
    packages: set[str] = set()
    packages.update(BLUEPRINT_TRANSITIVE_SKILL_PACKAGES.get(blueprint_dir.name, set()))
    payloads = blueprint_dir / "payloads"
    if payloads.is_dir():
        for path in payloads.rglob("*.py"):
            text = path.read_text(encoding="utf-8", errors="ignore")
            for marker, package in IMPORT_MARKER_PACKAGES.items():
                if marker in text:
                    packages.add(package)

    config_path = blueprint_dir / "config" / "default.json"
    if config_path.is_file():
        config = json.loads(config_path.read_text())
        for section_name in ("input_skills", "output_skills"):
            section = config.get(section_name)
            if not isinstance(section, dict):
                continue
            for entry in section.values():
                if not isinstance(entry, dict):
                    continue
                package = entry.get("package")
                if isinstance(package, str) and package.startswith("mirrorneuron-") and "-skill" in package:
                    packages.add(package)
                skill = entry.get("skill")
                if isinstance(skill, str) and skill in SKILL_NAME_PACKAGES:
                    packages.add(SKILL_NAME_PACKAGES[skill])

    manifest = json.loads((blueprint_dir / "manifest.json").read_text())
    registration = (
        manifest.get("metadata", {})
        .get("web_ui", {})
        .get("registration", {})
    )
    package = registration.get("package") if isinstance(registration, dict) else None
    if isinstance(package, str) and package.startswith("mirrorneuron-blueprint-support-skill"):
        packages.add("mirrorneuron-blueprint-support-skill")
    return packages


def test_otterdesk_manifests_pin_gar_skill_dependencies():
    for manifest_path in _manifest_paths():
        blueprint_id = manifest_path.parent.name
        manifest = json.loads(manifest_path.read_text())
        dependencies = manifest.get("skill_dependencies")
        assert isinstance(dependencies, list), blueprint_id
        by_name = {dependency.get("name"): dependency for dependency in dependencies if isinstance(dependency, dict)}

        assert set(by_name) == _expected_skill_dependency_packages(manifest_path.parent), blueprint_id
        assert "mn-skills" not in by_name
        for name, dependency in by_name.items():
            expected_version = SKILL_DEPENDENCY_VERSION_OVERRIDES.get(name, SKILL_DEPENDENCY_VERSION)
            assert dependency == {
                "type": "pip",
                "source": "gar",
                "name": name,
                "version": expected_version,
            }, (blueprint_id, name)


def test_video_gpu_blueprints_declare_hard_nvidia_cuda_requirements_consistently():
    targets = {
        "safety_video_analyser": ("video_understanding_agent", "video_understanding"),
        "video_watch_assistant": ("visual_detector", "primary"),
    }
    for blueprint_id, (worker_id, runtime_model_key) in targets.items():
        manifest = json.loads((ROOT / blueprint_id / "manifest.json").read_text())
        assert manifest["requirements"]["gpu"] == GPU_HARD_REQUIREMENT
        assert manifest["runtime"]["resources"]["gpu"] == GPU_HARD_REQUIREMENT
        assert manifest["runtime"]["models"][runtime_model_key]["model"] == "medium"
        assert manifest["runtime"]["models"][runtime_model_key]["install_mode"] == "cluster_provided"

        worker = next(node for node in _flow_nodes(manifest) if node["node_id"] == worker_id)
        _assert_hard_gpu_worker_requirements(worker)

        for template in _template_nodes(manifest):
            for key in ("original_node", "rendered_node"):
                rendered = template.get(key)
                if isinstance(rendered, dict) and rendered.get("node_id") == worker_id:
                    _assert_hard_gpu_worker_requirements(rendered)

    config = json.loads((ROOT / "video_watch_assistant" / "config" / "default.json").read_text())
    assert config["llm"]["model"] == "medium"
    assert config["llm"]["install_mode"] == "cluster_provided"
    assert config["resources"]["gpu"] == GPU_HARD_REQUIREMENT
    assert config["resources"]["required_capabilities"] == ["nvidia", "cuda"]

    safety_config = json.loads((ROOT / "safety_video_analyser" / "config" / "default.json").read_text())
    assert safety_config["vl_model"]["model"] == "medium"
    assert safety_config["vl_model"]["install_mode"] == "cluster_provided"


def test_all_blueprints_declare_actor_style_llm_config():
    required_llm_keys = {"enabled", "mode", "mock_mode", "model", "default_config", "configs", "agents", "responsibilities"}
    for manifest_path in _manifest_paths():
        manifest = json.loads(manifest_path.read_text())
        blueprint_id = manifest["metadata"]["blueprint_id"]
        config = json.loads((manifest_path.parent / "config" / "default.json").read_text())
        llm = config.get("llm")
        assert isinstance(llm, dict), blueprint_id
        assert required_llm_keys <= set(llm), blueprint_id
        assert llm["enabled"] is True, blueprint_id
        assert llm["default_config"] in llm["configs"], blueprint_id
        assert isinstance(llm["responsibilities"], list) and len(llm["responsibilities"]) >= 3, blueprint_id

        workers = _runtime_worker_ids(manifest)
        if manifest.get("kind") == "WorkflowSource":
            graph_nodes = [
                step["id"]
                for step in manifest.get("workflow", {}).get("steps", [])
                if isinstance(step, dict) and step.get("id")
            ]
        else:
            graph_nodes = [node["node_id"] for node in _flow_nodes(manifest)]
        required_actor_ids = workers or graph_nodes
        valid_actor_ids = set(workers) | set(graph_nodes)
        agents = llm["agents"]
        assert isinstance(agents, dict) and agents, blueprint_id
        assert set(required_actor_ids) <= set(agents), blueprint_id
        assert set(agents) <= valid_actor_ids, blueprint_id
        for actor_id, spec in agents.items():
            assert spec.get("llm_config") == llm["default_config"], (blueprint_id, actor_id)
            if "model" in spec:
                assert spec["model"], (blueprint_id, actor_id)
            assert str(spec.get("role") or "").strip(), (blueprint_id, actor_id)
            responsibilities = spec.get("responsibilities")
            assert isinstance(responsibilities, list) and len(responsibilities) >= 3, (blueprint_id, actor_id)
            assert all(str(item).strip() for item in responsibilities), (blueprint_id, actor_id)


def _assert_hard_gpu_worker_requirements(worker: dict) -> None:
    assert worker["constraints"] == [
        {"attribute": "capabilities", "operator": "contains_all", "value": ["nvidia", "cuda"]}
    ]
    assert worker["resources"]["gpu_count"] == 1
    devices = worker["resources"]["devices"]
    assert len(devices) == 1
    assert devices[0]["kind"] == "gpu"
    assert devices[0]["type"] == "nvidia/gpu"
    assert devices[0]["count"] == 1
    for key, value in GPU_WORKER_DEVICE_REQUIREMENT.items():
        assert devices[0][key] == value


def test_otterdesk_blueprints_are_workflow_driven_manifests():
    for manifest_path in _manifest_paths():
        manifest = json.loads(manifest_path.read_text())
        assert "graph_id" not in manifest, manifest_path.parent.name
        if not _is_workflow_manifest(manifest):
            continue
        if manifest["metadata"]["blueprint_id"] == "gtm_ai_workflow":
            continue
        blueprint_id = manifest["metadata"]["blueprint_id"]

        assert manifest["apiVersion"] == "mn.workflow/v1", blueprint_id
        assert manifest["kind"] == "Workflow", blueprint_id
        assert manifest["id"] == blueprint_id
        assert manifest["workflow"]["workflow_id"] == f"{blueprint_id}_v1"
        assert manifest["contract"]["inputs"], blueprint_id
        assert manifest["contract"]["outputs"]["primary"]["path"] == "final_artifact.json"
        assert manifest["contract"]["status"]["heartbeat"] is True, blueprint_id
        if manifest.get("type") != "service":
            assert validate_workflow_manifest(manifest) == []

        steps = manifest["workflow"]["steps"]
        bindings = manifest["runtime"]["bindings"]
        nodes = _flow_nodes(manifest)
        edges = _flow_edges(manifest)
        assert steps, blueprint_id
        assert nodes, blueprint_id
        assert edges, blueprint_id
        assert "flow" not in manifest
        assert "graph_id" not in manifest
        assert "nodes" not in manifest and "edges" not in manifest and "entrypoints" not in manifest
        node_ids = {node["node_id"] for node in nodes}
        step_ids = {step["id"] for step in steps}
        assert set(_agent_entrypoints(manifest)) <= node_ids, blueprint_id
        assert manifest["workflow"]["entrypoint"] == manifest["workflow"]["source"]
        assert manifest["workflow"]["entrypoint"] in step_ids, blueprint_id
        assert manifest["workflow"]["entrypoint"] == steps[0]["id"]
        for edge in manifest["workflow"]["edges"]:
            assert edge["from"] in step_ids, (blueprint_id, edge)
            assert edge["to"] in step_ids, (blueprint_id, edge)
        for edge in edges:
            assert edge["from_node"] in node_ids, (blueprint_id, edge)
            assert edge["to_node"] in node_ids, (blueprint_id, edge)
        assert manifest["workflow"]["schema"] == "mn.workflow.problem_graph/v1"
        assert manifest["workflow"]["dynamic"]["enabled"] is False
        assert manifest["metadata"]["standard"]["workflow_model"] == "contract -> workflow -> agents/runtime"
        for step in steps:
            assert {"id", "kind", "label", "goal", "action", "run", "emits", "on"} <= set(step), (blueprint_id, step)
            assert {"required", "retry", "failure_policy", "uncertainty"} <= set(step["control"]), (blueprint_id, step)
            assert step["control"]["retry"]["max_attempts"] >= 1, (blueprint_id, step)
            assert step["run"] in bindings, (blueprint_id, step)
            workers = bindings[step["run"]].get("workers") or []
            assert workers, (blueprint_id, step["run"])
            for worker in workers:
                assert {"id", "role"} <= set(worker), (blueprint_id, step["run"], worker)


def test_otterdesk_workflow_join_modes_use_runtime_contract_values():
    allowed_modes = {"all_required", "min_success"}
    for manifest_path in _manifest_paths():
        manifest = json.loads(manifest_path.read_text())
        if not _is_workflow_manifest(manifest):
            continue
        blueprint_id = manifest["metadata"]["blueprint_id"]
        for index, step in enumerate(manifest["workflow"]["steps"]):
            join = step.get("join")
            if not isinstance(join, dict):
                continue
            assert join.get("mode") in allowed_modes, (blueprint_id, index, step.get("id"), join)


def test_otterdesk_json_uses_python311_for_host_python_commands():
    bare_python3 = re.compile(r"(?<![\w.])python3(?!\.\d)")

    for json_path in sorted(ROOT.rglob("*.json")):
        if ".pytest_cache" in json_path.parts:
            continue
        data = json.loads(json_path.read_text())
        for value_path, value in _json_strings(data):
            if "system_packages" in value_path:
                continue
            if not bare_python3.search(value):
                continue
            if (
                value == "python3"
                and json_path.name == "manifest.json"
                and len(value_path) >= 2
                and value_path[-2:] == ("command", "0")
            ):
                command_owner = data
                for part in value_path[:-2]:
                    command_owner = command_owner[int(part)] if isinstance(command_owner, list) else command_owner[part]
                if command_owner.get("runner_module") == "MirrorNeuron.Runner.DockerWorker":
                    continue
            assert value.startswith("/usr/bin/python3"), (json_path, value_path, value)


def test_otterdesk_topology_metadata_matches_runtime_nodes():
    for manifest_path in _manifest_paths():
        manifest = json.loads(manifest_path.read_text())
        if not _flow_nodes(manifest) or not _template_nodes(manifest):
            continue
        blueprint_id = manifest["metadata"]["blueprint_id"]
        runtime_nodes = {node["node_id"] for node in _flow_nodes(manifest)}
        metadata_nodes = {
            node["node_id"]: node["uses"]
            for node in _template_nodes(manifest)
        }

        assert set(metadata_nodes) == runtime_nodes, blueprint_id


def test_gtm_ai_workflow_uses_current_flow_runtime_graph():
    pytest.skip("gtm_ai_workflow is not part of the current blueprint catalog")
    manifest = json.loads((ROOT / "gtm_ai_workflow" / "manifest.json").read_text())
    nodes = _flow_nodes(manifest)
    edges = _flow_edges(manifest)
    node_ids = {node["node_id"] for node in nodes}

    assert "nodes" not in manifest
    assert "edges" not in manifest
    assert "entrypoints" not in manifest
    assert _agent_entrypoints(manifest) == ["ingress"]
    assert manifest["workflow"]["entrypoint"] == "load_inputs"
    assert "ingress" in node_ids
    assert len(nodes) == 10
    assert len(edges) == 10
    assert all(edge["from_node"] in node_ids and edge["to_node"] in node_ids for edge in edges)
    assert {edge["edge_id"] for edge in edges} >= {
        "ingress_to_monitor_scheduler",
        "ingress_to_inbox_poller",
    }

    ingress_node = next(node for node in nodes if node["node_id"] == "ingress")
    assert ingress_node["type"] == "map"
    assert ingress_node["agent_type"] == "router"
    assert "uses" not in ingress_node and "with" not in ingress_node

    ingress_template = next(
        node for node in _template_nodes(manifest) if node["node_id"] == "ingress"
    )
    assert ingress_template["uses"] == "mn-agents.control_router@1"
    assert "node_type" not in ingress_template.get("with", {})

    monitor_config = _node_config(next(node for node in nodes if node["node_id"] == "monitor_scheduler_agent"))
    assert monitor_config["module"] == "Synaptic.MonitorScheduler"
    assert monitor_config["module_source"] == "monitor_scheduler/beam_modules/monitor_scheduler.ex"

    poller_config = _node_config(next(node for node in nodes if node["node_id"] == "inbox_poller_agent"))
    assert poller_config["module"] == "Synaptic.InboxPoller"
    assert poller_config["module_source"] == "inbox_poller/beam_modules/inbox_poller.ex"


def test_otterdesk_completion_contract_is_explicit_and_terminal_sinks_are_reachable():
    for manifest_path in _manifest_paths():
        manifest = json.loads(manifest_path.read_text())
        if not _is_workflow_manifest(manifest):
            continue
        blueprint_id = manifest["metadata"]["blueprint_id"]
        node_by_id = {node["node_id"]: node for node in _flow_nodes(manifest)}
        step_runs = {step["run"] for step in manifest["workflow"]["steps"]}
        outgoing_counts: dict[str, int] = {}
        incoming_edges: dict[str, list[dict]] = {}

        assert not _contains_key(manifest, "complete_job"), blueprint_id
        assert not _contains_key(manifest, "complete_job?"), blueprint_id

        for edge in _flow_edges(manifest):
            assert "message_type" in edge and edge["message_type"], (blueprint_id, edge)
            assert "event" not in edge, (blueprint_id, edge)
            assert edge["from_node"] in node_by_id, (blueprint_id, edge)
            assert edge["to_node"] in node_by_id, (blueprint_id, edge)
            outgoing_counts[edge["from_node"]] = outgoing_counts.get(edge["from_node"], 0) + 1
            incoming_edges.setdefault(edge["to_node"], []).append(edge)

        terminal_sinks = []
        for node in _flow_nodes(manifest):
            node_id = node["node_id"]
            config = _node_config(node)
            terminal_sink = config.get("terminal_sink") is True
            complete_run = config.get("complete_run") is True
            complete_on_message = config.get("complete_on_message") is True
            complete_after = _completion_threshold(config.get("complete_after"))
            output_message_type = config.get("output_message_type")

            assert not _contains_key(config, "complete_job"), (blueprint_id, node_id)
            assert not _contains_key(config, "complete_job?"), (blueprint_id, node_id)
            assert not (node_id in step_runs and complete_run), (blueprint_id, node_id)
            if complete_run or terminal_sink:
                assert terminal_sink is True, (blueprint_id, node_id)
                assert complete_run is True, (blueprint_id, node_id)
                assert outgoing_counts.get(node_id, 0) == 0, (blueprint_id, node_id)
                terminal_sinks.append(node_id)
            if complete_on_message or complete_after:
                assert output_message_type or (terminal_sink and complete_run), (blueprint_id, node_id)

        if manifest.get("type") == "service":
            assert terminal_sinks == [], blueprint_id
            continue

        assert terminal_sinks == ["report_sink"], blueprint_id
        sink_edges = incoming_edges.get("report_sink", [])
        assert len(sink_edges) == 1, blueprint_id
        final_step_node = manifest["workflow"]["sink"]
        final_step_config = _node_config(node_by_id[final_step_node])
        assert sink_edges[0]["from_node"] == final_step_node, blueprint_id
        assert sink_edges[0]["message_type"] == final_step_config["output_message_type"], blueprint_id


def test_otterdesk_rendered_completion_contract_is_valid():
    for manifest_path in _manifest_paths():
        manifest = json.loads(manifest_path.read_text())
        if not _is_workflow_manifest(manifest):
            continue
        blueprint_id = manifest["metadata"]["blueprint_id"]
        rendered = render_manifest_agent_templates(manifest, AGENTS_ROOT)
        rendered_nodes = {node["node_id"]: node for node in _flow_nodes(rendered)}
        step_runs = {step["run"] for step in manifest["workflow"]["steps"]}
        outgoing_counts: dict[str, int] = {}

        for edge in _flow_edges(rendered):
            outgoing_counts[edge["from_node"]] = outgoing_counts.get(edge["from_node"], 0) + 1

        for node_id, node in rendered_nodes.items():
            config = node.get("config", {})
            assert not _contains_key(config, "complete_job"), (blueprint_id, node_id)
            assert not _contains_key(config, "complete_job?"), (blueprint_id, node_id)
            if config.get("complete_run") is True:
                assert config.get("terminal_sink") is True, (blueprint_id, node_id)
                assert node_id not in step_runs, (blueprint_id, node_id)
                assert outgoing_counts.get(node_id, 0) == 0, (blueprint_id, node_id)
            if config.get("complete_on_message") is True or _completion_threshold(config.get("complete_after")):
                assert config.get("output_message_type") or (
                    config.get("terminal_sink") is True and config.get("complete_run") is True
                ), (blueprint_id, node_id)

def test_otterdesk_batch_workflows_complete_with_shared_runner(tmp_path):
    for manifest_path in _manifest_paths():
        manifest = json.loads(manifest_path.read_text())
        if not _is_workflow_manifest(manifest) or manifest.get("type") == "service":
            continue

        blueprint_id = manifest["metadata"]["blueprint_id"]
        run_dir = tmp_path / blueprint_id
        result = run_workflow_manifest_file(
            manifest_path,
            run_dir=run_dir,
            run_id=f"{blueprint_id}-test-run",
            auto_human="approve",
            speed=0.001,
            ui=False,
        )

        assert result["run"]["status"] == "completed", blueprint_id
        assert len(result["workflow"]["steps"]) == len(manifest["workflow"]["steps"]), blueprint_id
        assert (run_dir / "final_artifact.json").exists(), blueprint_id
        event_records = [json.loads(line) for line in (run_dir / "events.jsonl").read_text().splitlines() if line.strip()]
        event_types = {record["type"] for record in event_records}
        assert "workflow_step_attempt_completed" in event_types, blueprint_id
        assert "workflow_finished" in event_types, blueprint_id


class FakeBlueprintActorLLM:
    provider = "fake"
    model = "fake-blueprint-actor"

    def __init__(self) -> None:
        self.calls = 0
        self.fallback_calls = 0
        self.prompts: list[dict[str, str]] = []

    def generate_json(self, *, system_prompt: str, user_prompt: str, fallback: dict):
        self.calls += 1
        self.prompts.append({"system": system_prompt, "user": user_prompt})
        response = dict(fallback)
        response["summary"] = response.get("summary") or "Actor reviewed the packet."
        response["provider"] = self.provider
        response["model"] = self.model
        return response


def _load_script(path: Path, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_document_ocr_blueprints_emit_actor_findings_and_usage(tmp_path):
    targets = [
        "medical_deid_record_intake_assistant",
    ]
    for blueprint_id in targets:
        runner_path = ROOT / blueprint_id / "payloads" / "document_workflow" / "scripts" / "run_blueprint.py"
        module = _load_script(runner_path, f"{blueprint_id}_actor_runner_test")
        docs = tmp_path / blueprint_id / "docs"
        docs.mkdir(parents=True)
        (docs / "sample.txt").write_text("Sample source text with invoice total 123.45 and review notes.", encoding="utf-8")
        fake_llm = FakeBlueprintActorLLM()

        result = module.run_blueprint(
            inputs={
                "document_folder": str(docs),
                "output_folder": str(tmp_path / blueprint_id / "outputs"),
            },
            config={"llm": {"mode": "fake"}},
            runs_root=tmp_path,
            run_id=f"{blueprint_id}-actors",
            llm_client=fake_llm,
        )

        artifact = result["final_artifact"]
        actor_ids = set((result["final_artifact"]["actor_findings"] or {}).keys())
        expected_actor_ids = set((json.loads((ROOT / blueprint_id / "config" / "default.json").read_text())["llm"]["agents"]).keys())
        assert actor_ids == expected_actor_ids, blueprint_id
        assert artifact["llm_usage"]["calls"] == len(expected_actor_ids), blueprint_id
        assert fake_llm.calls == len(expected_actor_ids), blueprint_id
        events = [
            json.loads(line)
            for line in (tmp_path / f"{blueprint_id}-actors" / "events.jsonl").read_text().splitlines()
            if line.strip()
        ]
        actor_events = [event for event in events if event["type"] == "actor_activity"]
        assert {event["payload"]["agent_id"] for event in actor_events} == expected_actor_ids, blueprint_id


def test_safety_video_scripts_emit_actor_findings(tmp_path):
    video_dir = tmp_path / "videos"
    video_dir.mkdir()
    (video_dir / "workplace_safety.mp4").write_bytes(b"fake-video")
    env = dict(os.environ)
    env["MN_BLUEPRINT_CONFIG_JSON"] = json.dumps({"video_inputs": {"folder_path": str(video_dir)}})

    understanding = subprocess.run(
        [sys.executable, str(ROOT / "safety_video_analyser" / "payloads" / "safety_video_analyser" / "scripts" / "run_video_understanding.py")],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert understanding.returncode == 0, understanding.stderr
    analysis = json.loads((tmp_path / "video_analysis.json").read_text())
    assert set(analysis["actor_findings"]) == {"video_understanding_agent"}
    assert analysis["actor_activity"][0]["agent_id"] == "video_understanding_agent"

    input_file = tmp_path / "report_input.json"
    input_file.write_text(json.dumps({"analysis": analysis}), encoding="utf-8")
    report_env = dict(os.environ)
    report_env["MN_INPUT_FILE"] = str(input_file)
    report = subprocess.run(
        [sys.executable, str(ROOT / "safety_video_analyser" / "payloads" / "safety_video_analyser" / "scripts" / "run_report_generator.py")],
        cwd=tmp_path,
        env=report_env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert report.returncode == 0, report.stderr
    result = json.loads((tmp_path / "safety_video_report.json").read_text())
    assert set(result["actor_findings"]) == {"video_understanding_agent", "report_generator"}
    assert {event["agent_id"] for event in result["actor_activity"]} == {"video_understanding_agent", "report_generator"}

def test_otterdesk_blueprints_declare_membrane_context_memory_layer():
    for manifest_path in _manifest_paths():
        blueprint_dir = manifest_path.parent
        manifest = json.loads(manifest_path.read_text())
        if not _is_workflow_manifest(manifest):
            continue
        config = json.loads((blueprint_dir / "config" / "default.json").read_text())
        blueprint_id = manifest["metadata"]["blueprint_id"]
        if blueprint_id == "gtm_ai_workflow":
            continue
        expected_namespace = f"{blueprint_id}_context"

        config_layer = config.get("memory_layer")
        manifest_layer = manifest["metadata"].get("memory_layer")
        assert config_layer == manifest_layer, blueprint_dir.name
        assert config_layer["enabled"] is True
        assert config_layer["enabled_env"] == "MN_CONTEXT_MEMORY_ENABLED"
        assert config_layer["conversation_enabled"] is True
        assert config_layer["conversation_enabled_env"] == "OTTERDESK_CONTEXT_MEMORY_ENABLED"
        assert config_layer["namespace"] == expected_namespace
        assert config_layer["collection"] == "mn_memory"
        assert config_layer["sdk_distribution"] == "mirrorneuron-membrane-python-sdk"
        assert config_layer["sdk_import_package"] == "mn_context_engine_sdk"
        assert config_layer["project_path"] == "${MN_MEMBRANE_PROJECT_PATH}"
        assert config_layer["python_sdk_path"] == "${MN_MEMBRANE_SDK_PATH}"

        conversation = config_layer["conversation"]
        assert conversation["agent_role"] == "otterdesk_chat"
        assert conversation["include_runtime_events"] is True
        assert conversation["include_runtime_logs"] is True
        assert conversation["include_human_events"] is True
        assert conversation["token_budget"] > conversation["target_tokens"] > 0
        assert "Membrane context memory optimization" in manifest["metadata"]["runtime_features"]


def test_otterdesk_blueprints_declare_product_experience_contracts():
    expected_modes = {
        "drug_discovery_research_assistant": "approval_required",
        "financial_advisor": "approval_required",
        "purchase_research_assistant": "approval_required",
        "video_watch_assistant": "notice_only",
        "generic_customer_service_voice_coworker": "notice_only",
        "medical_deid_record_intake_assistant": "approval_required",
        "legal_assistant": "approval_required",
        "vc_assistant": "approval_required",
    }
    required_schema_keys = {
        "artifact_record",
        "events",
        "final_artifact",
        "human_control",
        "inputs",
        "logs",
        "resources",
        "status_contract",
        "web_ui",
    }
    required_events = {
        "blueprint_status",
        "blueprint_phase_started",
        "blueprint_phase_completed",
        "blueprint_phase_failed",
        "artifact_written",
        "human_notice",
        "human_input_requested",
        "human_input_received",
        "human_input_timeout",
        "human_decision_applied",
    }

    for manifest_path in _manifest_paths():
        blueprint_dir = manifest_path.parent
        manifest = json.loads(manifest_path.read_text())
        if not _is_workflow_manifest(manifest):
            continue
        config = json.loads((blueprint_dir / "config" / "default.json").read_text())
        metadata = manifest["metadata"]
        blueprint_id = metadata["blueprint_id"]
        if blueprint_id not in expected_modes:
            continue

        input_contract = metadata["input_contract"]
        assert input_contract["schema_version"] == "mn.blueprint.input_contract.v1", blueprint_id
        assert {"mock", "json", "file", "env_json"} <= set(input_contract["supported_adapters"])
        assert input_contract["required_inputs"], blueprint_id
        assert input_contract["resolved_artifact"] == "inputs.json"
        assert "mock" in input_contract["profiles"]
        assert input_contract["privacy_classification"] == config["privacy"]["default_classification"]
        for item in input_contract["required_inputs"] + input_contract["optional_inputs"]:
            assert {"name", "type", "description", "example"} <= set(item), (blueprint_id, item)

        human_control = metadata["human_control"]
        assert human_control == config["human_control"], blueprint_id
        assert human_control["mode"] in HUMAN_CONTROL_MODES
        assert human_control["mode"] == expected_modes[blueprint_id]
        assert human_control["enabled"] is True
        if human_control["mode"] == "approval_required":
            assert human_control["allowed_decisions"] == ["approve", "revise", "reject"]
            assert human_control["blocked_actions"], blueprint_id
            assert human_control["timeout_seconds"] > 0
            assert human_control["default_action"] in {"reject", "revise"}
        else:
            assert human_control["notice_event"] == "human_notice"
            assert human_control["requires_ack"] is False

        status_contract = metadata["status_contract"]
        assert status_contract["schema_version"] == "mn.blueprint.status_contract.v1"
        assert status_contract["source"] == "run_store"
        assert status_contract["heartbeat_event"] == "agent_beacon"
        assert status_contract["heartbeat_required"] is True
        assert status_contract["beacon_event"] == "agent_beacon"
        assert status_contract["beacon_interval_ms"] == 15000
        assert status_contract["beacon_timeout_ms"] == 45000
        assert status_contract["beacon_missed_action"] == "fail_attempt"
        assert [phase["phase"] for phase in status_contract["phases"]] == list(STATUS_PHASES)
        assert all(phase["start_event"] == "blueprint_phase_started" for phase in status_contract["phases"])
        assert all(phase["completion_event"] == "blueprint_phase_completed" for phase in status_contract["phases"])
        assert all(phase["failure_event"] == "blueprint_phase_failed" for phase in status_contract["phases"])

        final_contract = metadata["output_contract"]["final_artifact"]
        assert final_contract["schema_version"] == "mn.blueprint.final_artifact_contract.v1"
        assert set(FINAL_ARTIFACT_REQUIRED_FIELDS) <= set(final_contract["required_fields"])
        artifacts = metadata["output_contract"]["artifacts"]
        artifact_ids = {artifact["artifact_id"] for artifact in artifacts}
        assert {"run_metadata", "resolved_config", "resolved_inputs", "event_stream", "result", "final_artifact"} <= artifact_ids
        assert {"logs", "resources", "web_ui", "human_events"} <= artifact_ids
        for artifact in artifacts:
            assert {"artifact_id", "type", "path", "producer", "mime_type", "schema_version", "source_refs"} <= set(artifact), (
                blueprint_id,
                artifact,
            )

        dashboard = metadata["observability_dashboard"]
        assert dashboard["schema_version"] == "mn.blueprint.observability_dashboard.v1"
        assert set(STANDARD_OBSERVABILITY_PANELS) <= set(dashboard["panels"])
        assert {"events.jsonl", "human.jsonl", "logs.jsonl", "resources.jsonl", "final_artifact.json"} <= set(dashboard["reads"])
        assert set(dashboard["panels"]) <= set(config["web_ui"]["dashboard"]["standard_panels"])

        schemas = config["schemas"]
        assert required_schema_keys <= set(schemas), blueprint_id
        assert required_events <= set(config["logging"]["events"]), blueprint_id
        assert "human_control" in config["interfaces"]["config_sections"]
        assert "human_control" in metadata["interfaces"]["config"]

        review = metadata["init_config_review"]
        assert review["required"] is True
        assert review["fields"], blueprint_id
        for field in review["fields"]:
            assert {"path", "label", "default", "description"} <= set(field), (blueprint_id, field)


def test_otterdesk_folder_path_inputs_declare_directory_path_metadata():
    for manifest_path in _manifest_paths():
        manifest = json.loads(manifest_path.read_text())
        metadata = manifest.get("metadata", {})
        blueprint_id = metadata.get("blueprint_id") or manifest_path.parent.name
        expected_folder_inputs = FOLDER_INPUT_FIELDS.get(blueprint_id, set())
        contract_inputs = manifest.get("contract", {}).get("inputs", {})

        for name, spec in contract_inputs.items():
            if name in expected_folder_inputs or name.endswith("_folder") or name == "output_folder":
                _assert_directory_path_metadata(spec, (blueprint_id, "contract.inputs", name))

        input_contract = metadata.get("input_contract", {})
        input_items = input_contract.get("required_inputs", []) + input_contract.get("optional_inputs", [])
        by_name = {item.get("name"): item for item in input_items if isinstance(item, dict)}
        for name in expected_folder_inputs:
            assert name in by_name, (blueprint_id, name)
            _assert_directory_path_metadata(by_name[name], (blueprint_id, "metadata.input_contract", name))
        for name, item in by_name.items():
            if isinstance(name, str) and (name.endswith("_folder") or name == "output_folder"):
                _assert_directory_path_metadata(item, (blueprint_id, "metadata.input_contract", name))

        review = metadata.get("init_config_review", {})
        for field in review.get("fields", []):
            if not isinstance(field, dict):
                continue
            path = str(field.get("path") or "")
            name = str(field.get("name") or "")
            if path.endswith(".folder_path") or name == "output_folder":
                _assert_directory_path_metadata(field, (blueprint_id, "metadata.init_config_review", path or name))


def test_otterdesk_blueprints_declare_standard_default_input_and_output_folders():
    for manifest_path in _manifest_paths():
        blueprint_dir = manifest_path.parent
        blueprint_id = blueprint_dir.name
        manifest = json.loads(manifest_path.read_text())
        config = json.loads((blueprint_dir / "config" / "default.json").read_text())
        expected_input = _default_input_folder(blueprint_id)
        expected_output = _default_output_folder(blueprint_id)

        assert (blueprint_dir / "examples" / "sample_inputs").is_dir(), blueprint_id

        contract_inputs = manifest["contract"]["inputs"]
        assert contract_inputs["input_folder"]["example"] == expected_input, blueprint_id
        assert contract_inputs["output_folder"]["example"] == expected_output, blueprint_id
        _assert_directory_path_metadata(contract_inputs["input_folder"], (blueprint_id, "contract.input_folder"))
        _assert_directory_path_metadata(contract_inputs["output_folder"], (blueprint_id, "contract.output_folder"))

        payload = config["inputs"]["payload"]
        assert payload["input_folder"] == expected_input, blueprint_id
        assert payload["output_folder"] == expected_output, blueprint_id
        assert config["outputs"]["folder_path"] == expected_output, blueprint_id

        review_fields = {
            field["path"]: field
            for field in manifest["metadata"]["init_config_review"]["fields"]
            if isinstance(field, dict) and "path" in field
        }
        visible_input_folder_paths = [
            path
            for path in review_fields
            if path == "inputs.payload.input_folder" or (path.endswith(".folder_path") and path != "outputs.folder_path")
        ]
        assert len(visible_input_folder_paths) == 1, blueprint_id
        assert review_fields[visible_input_folder_paths[0]]["default"] == expected_input, blueprint_id
        assert "inputs.payload.output_folder" not in review_fields, blueprint_id
        assert review_fields["outputs.folder_path"]["default"] == expected_output, blueprint_id


def test_indexed_non_vc_blueprints_ship_non_placeholder_sample_inputs():
    for entry in _indexed_non_vc_blueprints():
        blueprint_id = entry["id"]
        sample_dir = ROOT / entry["path"] / "examples" / "sample_inputs"
        assert sample_dir.is_dir(), blueprint_id

        real_files = [
            path
            for path in sample_dir.iterdir()
            if path.is_file() and path.name != ".gitkeep"
        ]
        assert real_files, blueprint_id

        dataset_manifest_path = sample_dir / "SAMPLE_DATASET_MANIFEST.json"
        assert dataset_manifest_path.is_file(), blueprint_id
        dataset_manifest = json.loads(dataset_manifest_path.read_text())
        schema = dataset_manifest.get("schema") or dataset_manifest.get("schema_version")
        if schema is not None:
            assert schema == "otterdesk.sample_dataset.v1", blueprint_id
        assert dataset_manifest["blueprint_id"] == blueprint_id, blueprint_id
        assert dataset_manifest.get("description") or dataset_manifest.get("demo_source"), blueprint_id

        listed_files = dataset_manifest.get("files")
        assert isinstance(listed_files, list) and listed_files, blueprint_id
        for item in listed_files:
            if isinstance(item, str):
                assert (sample_dir / item).is_file(), (blueprint_id, item)
                continue
            assert {"path", "type", "contains_pii", "intended_use"} <= set(item), (blueprint_id, item)
            assert (sample_dir / item["path"]).is_file(), (blueprint_id, item["path"])


def test_indexed_non_vc_blueprints_have_non_trivial_rag_knowledge():
    for entry in _indexed_non_vc_blueprints():
        blueprint_id = entry["id"]
        blueprint_dir = ROOT / entry["path"]
        manifest = json.loads((blueprint_dir / "manifest.json").read_text())
        rag = manifest.get("knowledge_rag") or manifest.get("metadata", {}).get("knowledge_rag", {})
        if not rag.get("enabled"):
            continue

        knowledge_dir = blueprint_dir / rag.get("knowledge_dir", "knowledge")
        assert knowledge_dir.is_dir(), blueprint_id
        knowledge_files = [
            path
            for path in knowledge_dir.rglob("*")
            if path.is_file() and path.suffix.lower() in {".md", ".txt"}
        ]
        assert knowledge_files, blueprint_id

        combined = "\n".join(path.read_text(encoding="utf-8") for path in knowledge_files)
        assert len(combined) >= 1800, blueprint_id
        lowered = combined.lower()
        assert "evidence" in lowered, blueprint_id
        assert "review" in lowered, blueprint_id


def test_product_ready_llm_configs_use_explicit_live_docker_model_runner_profile():
    targets = {
        "drug_discovery_research_assistant",
        "medical_deid_record_intake_assistant",
        "legal_assistant",
        "purchase_research_assistant",
    }
    for blueprint_id in sorted(targets):
        config = json.loads((ROOT / blueprint_id / "config" / "default.json").read_text())
        llm = config["llm"]
        primary = llm["configs"]["primary"]

        assert llm["provider"] == "docker_model_runner", blueprint_id
        assert llm["model"] == "small", blueprint_id
        assert llm["runtime_model"] == "small", blueprint_id
        assert llm["backend"] == "llama.cpp", blueprint_id
        assert primary["provider"] == "docker_model_runner", blueprint_id
        assert primary["model"] == "small", blueprint_id
        assert primary["runtime_model"] == "small", blueprint_id
        assert primary["backend"] == "llama.cpp", blueprint_id
        assert llm["live_model_profile"]["runtime_model"] == "small", blueprint_id


def test_otterdesk_init_config_review_does_not_duplicate_folder_controls():
    for manifest_path in _manifest_paths():
        blueprint_id = manifest_path.parent.name
        manifest = json.loads(manifest_path.read_text())
        fields = manifest["metadata"]["init_config_review"]["fields"]
        paths = [field.get("path") for field in fields if isinstance(field, dict)]
        visible_input_folder_paths = [
            path
            for path in paths
            if isinstance(path, str)
            and (path == "inputs.payload.input_folder" or (path.endswith(".folder_path") and path != "outputs.folder_path"))
        ]
        visible_output_folder_paths = [path for path in paths if path in {"inputs.payload.output_folder", "outputs.folder_path"}]

        assert len(visible_input_folder_paths) == 1, (blueprint_id, visible_input_folder_paths)
        assert visible_output_folder_paths == ["outputs.folder_path"], (blueprint_id, visible_output_folder_paths)
        if any(path.endswith(".folder_path") and path != "outputs.folder_path" for path in visible_input_folder_paths):
            assert "inputs.payload.input_folder" not in paths, blueprint_id


def test_otterdesk_blueprint_descriptions_are_customer_facing_and_synchronized():
    index_by_id = {entry["id"]: entry for entry in json.loads((ROOT / "index.json").read_text())}
    for manifest_path in _manifest_paths():
        blueprint_dir = manifest_path.parent
        blueprint_id = blueprint_dir.name
        manifest = json.loads(manifest_path.read_text())
        config = json.loads((blueprint_dir / "config" / "default.json").read_text())
        description = manifest.get("description")

        assert isinstance(description, str) and len(description) >= 160, blueprint_id
        assert description == manifest["metadata"]["description"], blueprint_id
        assert description == config["metadata"]["description"], blueprint_id
        assert description == index_by_id[blueprint_id]["description"], blueprint_id
        assert any(marker in description for marker in ("Give it", "Put ")), blueprint_id
        assert "input folder" in description, blueprint_id
        assert "output folder" in description, blueprint_id


EXPECTED_BATCH_SUGGESTED_SCHEDULES = {
    "drug_discovery_research_assistant": {"cron": "0 8 * * 1", "cadence": "weekly"},
    "financial_advisor": {"cron": "0 8 * * *", "cadence": "daily"},
    "medical_deid_record_intake_assistant": {"cron": "0 * * * *", "cadence": "hourly"},
    "legal_assistant": {"cron": "0 8 * * 1-5", "cadence": "weekday_daily"},
    "purchase_research_assistant": {"cron": "0 8 * * 1", "cadence": "weekly"},
    "safety_video_analyser": {"cron": "0 2 * * *", "cadence": "daily"},
    "vc_assistant": {"cron": "0 7 * * *", "cadence": "daily"},
}

CONTINUOUS_BLUEPRINTS_WITHOUT_SUGGESTED_SCHEDULES = {
    "generic_customer_service_voice_coworker",
    "video_watch_assistant",
}


def _expected_schedule(blueprint_id: str) -> dict:
    expected = dict(EXPECTED_BATCH_SUGGESTED_SCHEDULES[blueprint_id])
    expected["advisory_only"] = True
    expected["note"] = "Suggested cadence only; runtime decides the actual schedule."
    return expected


def _embedded_manifest_configs(manifest: dict):
    for node in manifest.get("agents", {}).get("nodes", []):
        env = (node.get("config") or {}).get("environment") or {}
        if env.get("MN_BLUEPRINT_CONFIG_JSON"):
            yield json.loads(env["MN_BLUEPRINT_CONFIG_JSON"])
    for template in manifest.get("metadata", {}).get("agent_templates", {}).get("nodes", []):
        env = (template.get("with") or {}).get("environment") or {}
        if env.get("MN_BLUEPRINT_CONFIG_JSON"):
            yield json.loads(env["MN_BLUEPRINT_CONFIG_JSON"])


def test_batch_blueprints_declare_advisory_schedules():
    index_by_id = {entry["id"]: entry for entry in json.loads((ROOT / "index.json").read_text())}

    for blueprint_id in sorted(EXPECTED_BATCH_SUGGESTED_SCHEDULES):
        blueprint_dir = ROOT / blueprint_id
        config = json.loads((blueprint_dir / "config" / "default.json").read_text())
        manifest = json.loads((blueprint_dir / "manifest.json").read_text())
        schedule = config.get("suggested_schedule")

        assert schedule == _expected_schedule(blueprint_id)
        assert re.fullmatch(r"(\S+\s+){4}\S+", schedule["cron"])
        assert schedule["advisory_only"] is True
        triggers = config.get("triggers") or {}
        if "schedule" in triggers:
            assert triggers["schedule"] in (None, False), blueprint_id
        for embedded_config in _embedded_manifest_configs(manifest):
            assert embedded_config.get("suggested_schedule") == schedule, blueprint_id

    assert index_by_id["safety_video_analyser"]["type"] == "batch"
    assert index_by_id["vc_assistant"]["type"] == "batch"
    for blueprint_id in CONTINUOUS_BLUEPRINTS_WITHOUT_SUGGESTED_SCHEDULES:
        config = json.loads((ROOT / blueprint_id / "config" / "default.json").read_text())
        assert "suggested_schedule" not in config, blueprint_id


def test_index_entries_point_to_loadable_blueprint_folders():
    index = json.loads((ROOT / "index.json").read_text())
    assert index
    ids = [entry["id"] for entry in index]
    assert len(ids) == len(set(ids))

    for entry in index:
        blueprint_dir = ROOT / entry["path"]
        manifest_path = blueprint_dir / "manifest.json"
        assert blueprint_dir.exists(), entry
        assert manifest_path.exists(), entry
        manifest = json.loads(manifest_path.read_text())
        assert manifest["metadata"]["blueprint_id"] == entry["id"]
        assert "graph_id" not in manifest
        assert "graph_id" not in entry
        manifest_workflow_id = (
            manifest.get("workflow", {}).get("workflow_id")
            if isinstance(manifest.get("workflow"), dict)
            else manifest.get("workflow_id")
        )
        assert manifest_workflow_id == entry["workflow_id"]
        assert manifest["job_name"] == entry["job_name"]


def test_generic_customer_service_voice_blueprint_contract():
    blueprint_dir = ROOT / "generic_customer_service_voice_coworker"
    manifest = json.loads((blueprint_dir / "manifest.json").read_text())
    config = json.loads((blueprint_dir / "config" / "default.json").read_text())
    script = (blueprint_dir / "scripts" / "pre-launch.sh").read_text()
    cleanup = (blueprint_dir / "scripts" / "post-launch.sh").read_text()

    assert manifest["type"] == "service"
    assert "voice_service" in _agent_entrypoints(manifest)
    assert manifest["runtime"]["resources"]["gpu"]["min_count"] == 1
    assert manifest["runtime"]["worker_defaults"]["pool"] == "nvidia-accelerated"
    assert manifest["runtime"]["models"]["primary"]["model"] == "medium"
    assert manifest["runtime"]["models"]["asr"]["model"] == "otterdesk-voice-asr:default"
    assert manifest["runtime"]["models"]["tts"]["model"] == "otterdesk-voice-tts:default"
    voice_node = next(node for node in _flow_nodes(manifest) if node["node_id"] == "voice_service")
    voice_config = _node_config(voice_node)
    assert voice_config["execution_profile"] == "nvidia-accelerated-voice"
    assert voice_config["pool"] == "nvidia-accelerated"
    assert voice_config["pool_slots"] == 1
    assert voice_config["agent_beacon_required"] is False
    assert voice_config["command"] == ["bash", "scripts/run_voice_service.sh"]
    assert voice_config["upload_path"] == "voice_service"
    assert voice_node["resources"]["gpu_count"] == 1
    assert {port["label"]: port["port"] for port in voice_node["resources"]["ports"]} == {
        "voice_https": 7863,
        "nvidia_asr": 8080,
        "docker_model_runner": 12434,
        "magpie_tts": 8001,
    }
    assert voice_node["constraints"][0]["attribute"] == "capabilities"
    assert voice_node["constraints"][0]["operator"] == "contains_any"
    assert "nvidia-dgx-spark" in voice_node["constraints"][0]["value"]
    assert "nvidia-gb10" in voice_node["constraints"][0]["value"]
    assert voice_config["public_url"] == "https://localhost:7863/customer-service"

    payload = config["inputs"]["payload"]
    assert payload["business_name"] == "Otter Slice Pizza"
    assert "spark_host" not in payload
    assert payload["voice"] == "aria"
    assert payload["voice_https_port"] == 7863
    assert payload["voice_local_proxy_port"] == 7863
    assert config["web_ui"]["dashboard"]["voice_url"] == "https://localhost:7863/customer-service"
    assert config["streams"]["customer_service_voice_stream"]["transport"] == "webrtc"
    assert manifest["input_validation"]["rules"] == []
    assert "validate_rtsp_source.py" not in json.dumps(manifest)

    assert "NVIDIA-accelerated runtime launch" in script
    assert "CUSTOMER_SERVICE_SPARK" not in script
    assert "CUSTOMER_SERVICE_KNOWLEDGE_PATH" in script
    assert "MN_PRE_LAUNCH_READY_FILE" in script
    assert "customer_service_knowledge.txt" in script
    assert "MN_POST_LAUNCH_REASON" in cleanup
    assert "customer_service_voice_cleanup_deferred" in cleanup
    assert "voice_proxy.pid" not in cleanup
    assert "voice_service.pid" in cleanup
    assert "serve_customer_service_https.py" in cleanup
    assert "scripts/model_service.sh stop" not in cleanup


def test_generic_customer_service_rag_chunking_and_retrieval():
    payload_dir = ROOT / "generic_customer_service_voice_coworker" / "payloads" / "voice_service"
    sys.path.insert(0, str(payload_dir))
    try:
        from rag import build_rag_context, chunk_text, retrieve
    finally:
        try:
            sys.path.remove(str(payload_dir))
        except ValueError:
            pass

    text = """
    Hours:
    The support desk is open Monday through Friday from 9 AM to 5 PM.

    Appointments:
    Customers can reschedule an appointment with at least 24 hours notice.

    Billing:
    Billing disputes must be escalated to a human support lead.
    """
    chunks = chunk_text(text, max_tokens=18, overlap=4)
    assert len(chunks) >= 3
    results = retrieve("Can I reschedule my appointment tomorrow?", chunks, top_k=2)
    assert results
    assert "reschedule" in results[0].text.lower()

    context, selected = build_rag_context("billing dispute refund", text, top_k=2)
    assert selected
    assert "Billing disputes" in context


def test_generic_customer_service_knowledge_persistence(tmp_path, monkeypatch):
    payload_dir = ROOT / "generic_customer_service_voice_coworker" / "payloads" / "voice_service"
    sys.path.insert(0, str(payload_dir))
    try:
        from knowledge_store import ensure_knowledge_file, knowledge_metadata, read_knowledge, write_knowledge
    finally:
        try:
            sys.path.remove(str(payload_dir))
        except ValueError:
            pass

    knowledge_path = tmp_path / "knowledge" / "customer_service_knowledge.txt"
    monkeypatch.setenv("CUSTOMER_SERVICE_KNOWLEDGE_PATH", str(knowledge_path))
    ensure_knowledge_file(seed_text="Hours are 10 to 4.")
    assert read_knowledge() == "Hours are 10 to 4.\n"

    metadata = write_knowledge("Emergency calls go to the dispatcher.")
    assert metadata.bytes > 0
    assert metadata.sha256
    assert "dispatcher" in read_knowledge()
    assert knowledge_metadata().sha256 == metadata.sha256
    assert (knowledge_path.parent / "customer_service_knowledge.meta.json").exists()


def test_purchase_research_final_artifact_uses_product_output_fields(tmp_path):
    runner_path = ROOT / "purchase_research_assistant" / "payloads" / "document_workflow" / "scripts" / "run_blueprint.py"
    spec = importlib.util.spec_from_file_location("otterdesk_purchase_runner_product_test", runner_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    result = module.run_blueprint(
        inputs={"purchase_type": "car", "item_description": "used hybrid SUV", "budget": 30000},
        config={"llm": {"mode": "fake"}},
        runs_root=tmp_path,
        run_id="purchase-product-contract",
    )
    artifact = result["final_artifact"]

    assert set(FINAL_ARTIFACT_REQUIRED_FIELDS) <= set(artifact)
    assert artifact["evidence"]
    assert {"inputs.json", "events.jsonl", "result.json"} <= set(artifact["source_refs"])
    expected_actor_ids = set(json.loads((ROOT / "purchase_research_assistant" / "config" / "default.json").read_text())["llm"]["agents"])
    assert set(artifact["actor_findings"]) == expected_actor_ids
    assert artifact["llm_usage"]["calls"] >= len(expected_actor_ids)

    events = [
        json.loads(line)
    for line in (tmp_path / "purchase-product-contract" / "events.jsonl").read_text().splitlines()
        if line.strip()
    ]
    event_types = {event["type"] for event in events}
    assert {"blueprint_status", "blueprint_phase_started", "blueprint_phase_completed", "artifact_written"} <= event_types


def test_video_watch_declares_otterdesk_chat_system_prompt():
    blueprint_dir = ROOT / "video_watch_assistant"
    manifest = json.loads((blueprint_dir / "manifest.json").read_text())
    prompt = (blueprint_dir / "payloads" / "prompts" / "chat-system.md").read_text()

    assert "payloads/prompts/" in manifest["metadata"]["configuration_contract"]["optional_files"]
    assert "Video Watch Assistant" in prompt
    assert "co-worker" in prompt
    assert "human-in-the-loop" in prompt


def test_video_watch_declares_domain_agent_aliases():
    manifest = json.loads((ROOT / "video_watch_assistant" / "manifest.json").read_text())

    template_aliases = {
        node["node_id"]: node["alias"]
        for node in manifest["metadata"]["agent_templates"]["nodes"]
    }
    assert template_aliases == {
        "ingress": "video_monitor",
        "video_frame_tick_source": "frame_sampler",
        "visual_detector": "quality_controller",
    }

    worker_ids = [
        worker["id"]
        for binding in manifest["runtime"]["bindings"].values()
        for worker in binding["workers"]
    ]
    assert worker_ids == [
        "visual_target_detector",
        "quality_controller",
        "frame_sampler",
        "video_source_validator",
        "video_monitor",
        "watch_summary_writer",
    ]
    assert all(
        worker.get("alias") == worker["id"]
        for binding in manifest["runtime"]["bindings"].values()
        for worker in binding["workers"]
    )
    assert [step["label"] for step in manifest["workflow"]["steps"]] == [
        "Start Video Monitor",
        "Sample Video Frames",
        "Detect Visual Targets",
        "Write Watch Summary",
    ]


def test_otterdesk_nodes_use_shared_agent_templates_and_render():
    for manifest_path in _manifest_paths():
        manifest = json.loads(manifest_path.read_text())
        if not _flow_nodes(manifest) or not _template_nodes(manifest):
            continue
        template_nodes = _template_nodes(manifest)
        original_nodes = {node["node_id"]: node for node in template_nodes}
        control_by_step = {
            step["id"]: step["control"]
            for step in manifest.get("workflow", {}).get("steps", [])
            if isinstance(step.get("control"), dict)
        }
        assert template_nodes, manifest_path
        for node in template_nodes:
            assert "uses" in node, (manifest_path.parent.name, node.get("node_id"))
            assert node["uses"].startswith("mn-agents."), (manifest_path.parent.name, node.get("node_id"))
            assert "@" in node["uses"] and not node["uses"].endswith("@latest")
            if "with" in node:
                assert isinstance(node.get("with"), dict), (manifest_path.parent.name, node.get("node_id"))
            assert not {"agent_type", "type", "role", "config"} & set(node), (
                manifest_path.parent.name,
                node.get("node_id"),
            )

        rendered = render_manifest_agent_templates(manifest, AGENTS_ROOT)
        rendered_nodes = _flow_nodes(rendered)
        assert len(rendered_nodes) == len(template_nodes)
        assert all("uses" not in node and "with" not in node for node in rendered_nodes)
        for node in rendered_nodes:
            if node.get("agent_type") != "executor":
                continue
            config = node["config"]
            node_id = node["node_id"]
            assert config["beacon_enabled"] is True, (manifest_path.parent.name, node_id)
            assert config["beacon_interval_ms"] == 15000, (manifest_path.parent.name, node_id)
            assert config["beacon_timeout_ms"] == 45000, (manifest_path.parent.name, node_id)
            assert config["beacon_missed_action"] == "fail_attempt", (manifest_path.parent.name, node_id)
            if original_nodes[node_id]["uses"].startswith("mn-agents.data_python_executor@"):
                configured_beacon_required = original_nodes[node_id].get("with", {}).get(
                    "agent_beacon_required"
                )
                if isinstance(configured_beacon_required, bool):
                    assert config["agent_beacon_required"] is configured_beacon_required, (
                        manifest_path.parent.name,
                        node_id,
                    )
                else:
                    assert config["agent_beacon_required"] is True, (
                        manifest_path.parent.name,
                        node_id,
                    )
            if node_id in control_by_step:
                control = control_by_step[node_id]
                assert config["timeout_seconds"] == control["timeout_seconds"], (manifest_path.parent.name, node_id)
                assert config["max_attempts"] == control["retry"]["max_attempts"], (manifest_path.parent.name, node_id)
                assert config["retry_backoff_ms"] == int(control["retry"]["backoff_seconds"] * 1000), (
                    manifest_path.parent.name,
                    node_id,
                )


def test_otterdesk_manifests_require_runtime_workflow_control_contract():
    expected_statuses = {
        "pending",
        "ready",
        "queued",
        "running",
        "retry_wait",
        "blocked",
        "completed",
        "partial",
        "skipped",
        "failed",
    }
    expected_events = {
        "workflow_step_attempt_started",
        "workflow_step_beacon",
        "workflow_step_attempt_completed",
        "workflow_step_attempt_timed_out",
        "workflow_step_attempt_retry_scheduled",
        "workflow_step_blocked",
        "workflow_step_completed",
        "workflow_step_failed",
        "workflow_message_dead_lettered",
    }

    for manifest_path in _manifest_paths():
        manifest = json.loads(manifest_path.read_text())
        if not _is_workflow_manifest(manifest):
            continue
        workflow_control = manifest.get("runtime", {}).get("workflow_control")
        assert workflow_control, manifest_path.parent.name
        assert workflow_control["schema_version"] == "mn.workflow.runtime_control.v1"
        assert workflow_control["enabled"] is True
        assert workflow_control["source_of_truth"] == "workflow.steps"
        assert workflow_control["state_ledger"]["enabled"] is True
        assert workflow_control["state_ledger"]["persisted_field"] == "workflow_state"
        assert set(workflow_control["state_ledger"]["step_statuses"]) == expected_statuses
        assert workflow_control["state_ledger"]["message_ledger"] is True
        assert workflow_control["state_ledger"]["delivery_semantics"] == "at_least_once_with_idempotency"
        assert workflow_control["attempts"]["stale_attempt_outputs"] == "ignore"
        assert workflow_control["attempts"]["retry_policy_source"] == "workflow.steps[].control.retry"
        assert workflow_control["attempts"]["timeout_source"] == "workflow.steps[].control.timeout_seconds"
        assert workflow_control["liveness"] == {
            "event": "agent_beacon",
            "interval_ms": 15000,
            "timeout_ms": 45000,
            "required": True,
            "missed_action": "fail_attempt",
        }
        assert workflow_control["reconciliation"] == {
            "interval_ms": 2000,
            "on_timeout": "fail_attempt_then_retry",
            "on_missed_beacon": "fail_attempt_then_retry",
            "on_retry_exhausted": "apply_step_failure_policy",
        }
        assert workflow_control["pause_cancel"] == {
            "pause_mode": "stop_active_attempts",
            "resume_mode": "reconcile_from_workflow_state",
            "cancel_mode": "terminate_active_attempts",
        }
        assert set(workflow_control["events"]) == expected_events

        status_contract = manifest.get("metadata", {}).get("status_contract", {})
        assert status_contract["runtime_state_source"] == "workflow_state"
        assert status_contract["attempt_event"] == "workflow_step_attempt_started"
        assert status_contract["retry_event"] == "workflow_step_attempt_retry_scheduled"
        assert status_contract["blocked_event"] == "workflow_step_blocked"
        assert set(status_contract["terminal_step_events"]) == {
            "workflow_step_completed",
            "workflow_step_partial",
            "workflow_step_skipped",
            "workflow_step_failed",
        }


def test_otterdesk_workflow_steps_are_bounded_and_retryable():
    for manifest_path in _manifest_paths():
        manifest = json.loads(manifest_path.read_text())
        manual_stop_service = (
            manifest.get("type") == "service"
            and isinstance(manifest.get("service"), dict)
            and manifest["service"].get("run_until") == "manual_stop"
        )
        for step in manifest.get("workflow", {}).get("steps", []):
            control = step.get("control", {})
            if manual_stop_service:
                # The service must remain alive until a user sends SIGTERM or
                # creates STOP; imposing a per-step deadline would turn it back
                # into a finite batch workflow. Runtime cancellation controls
                # remain the termination boundary for this manifest type.
                continue
            assert isinstance(control.get("timeout_seconds"), int), (manifest_path.parent.name, step.get("id"))
            assert control["timeout_seconds"] > 0, (manifest_path.parent.name, step.get("id"))
            assert control["retry"]["max_attempts"] >= 1, (manifest_path.parent.name, step.get("id"))
            assert control["retry"]["backoff_seconds"] >= 0, (manifest_path.parent.name, step.get("id"))

def test_video_watch_openshell_policy_is_generated_by_shared_helper(tmp_path):
    blueprint_dir = ROOT / "video_watch_assistant"
    config = json.loads((blueprint_dir / "config" / "default.json").read_text())
    manifest = json.loads((blueprint_dir / "manifest.json").read_text())
    network = config["openshell_network"]

    endpoints = [
        endpoint_from_uri(
            item["name"],
            item["uri"],
            item["binaries"],
            allowed_ips=item.get("allowed_ips"),
            allow_any_ip=bool(item.get("allow_any_ip")),
        )
        for item in network["endpoints"]
    ]
    generated_policy = build_openshell_network_policy(endpoints, include_dns=network.get("include_dns", True))
    generated_path = write_openshell_network_policy(generated_policy, tmp_path / "video-egress.yaml")
    committed_path = blueprint_dir / "payloads" / network["policy_path"]

    assert generated_path.read_text() == committed_path.read_text()
    assert "0.0.0.0/0" not in committed_path.read_text()

    rendered = render_manifest_agent_templates(manifest, AGENTS_ROOT)
    visual_node = next(node for node in _flow_nodes(rendered) if node["node_id"] == "visual_detector")
    assert visual_node["config"]["runner_module"] == "MirrorNeuron.Runner.DockerWorker"
    assert visual_node["config"]["docker_worker_image"] == "visual_detector/docker_worker"
    assert visual_node["config"]["workdir"] == "/mn/job/visual_detector"
    assert visual_node["config"]["command"] == ["bash", "scripts/run_detector_in_docker_worker.sh"]
    assert visual_node["config"]["policy"] == network["policy_path"]
    assert visual_node["config"]["upload_paths"] == [{"source": "visual_detector", "target": "visual_detector"}]
    assert "PYTHONPATH" not in visual_node["config"]["environment"]


def test_video_watch_detector_script_compiles_with_shared_helper_import():
    py_compile.compile(
        str(ROOT / "video_watch_assistant" / "payloads" / "visual_detector" / "scripts" / "analyze_video_frame.py"),
        doraise=True,
    )


def test_video_watch_pre_launch_owns_mediamtx_preview_config():
    blueprint_dir = ROOT / "video_watch_assistant"
    config = json.loads((blueprint_dir / "config" / "default.json").read_text())
    manifest = json.loads((blueprint_dir / "manifest.json").read_text())
    script = (blueprint_dir / "scripts" / "pre-launch.sh").read_text()
    cleanup_script = (blueprint_dir / "scripts" / "post-launch.sh").read_text()

    assert "webrtc: true" in script
    assert "choose_available_webrtc_ports" in script
    assert "BROWSER_PREVIEW_URI" in script
    assert "MN_POST_LAUNCH_STATE_FILE" in script
    assert "post_launch_state.json" in script
    assert "pre_launch_preflight" in script
    assert '"browser_video_source": "${BROWSER_PREVIEW_URI}"' in script
    assert '"browser_publish_source": "disabled"' in script
    assert '"cleanup_script": "scripts/post-launch.sh"' in script
    assert "terminate_mediamtx_on_port" in cleanup_script
    assert "MN_PRE_LAUNCH_PROCESS_FILE" in cleanup_script
    assert "PRE_LAUNCH_PROCESS_GROUP_ID" in cleanup_script
    assert "terminate_process_group" in cleanup_script
    assert "RTSP_PORT" in cleanup_script
    assert "WEBRTC_PORT" in cleanup_script

    dashboard = config["web_ui"]["dashboard"]
    assert dashboard["browser_video_source"] == "disabled"
    assert dashboard["browser_publish_source"] == "disabled"
    assert dashboard["rendering"]["layout"]["column_regions"] == [
        {"w": 12, "x": 0},
        {"w": 12, "x": 12},
    ]
    video_panel = next(panel for panel in dashboard["grafana"]["panels"] if panel["type"] == "video")
    assert video_panel["options"]["browserSource"] == "${browser_video_source}"
    assert video_panel["options"]["browserPublishSource"] == "${browser_publish_source}"
    assert dashboard["video_preview_bridge"]["enabled"] is False
    assert dashboard["video_preview_bridge"]["auto_start"] is False
    assert dashboard["video_preview_bridge"]["cleanup_script"] == "scripts/post-launch.sh"

    manifest_web_ui = manifest["metadata"]["web_ui"]
    assert manifest_web_ui["browser_video_source"] == "disabled"
    assert manifest_web_ui["browser_publish_source"] == "disabled"
    assert manifest_web_ui["rendering"]["layout"]["column_regions"] == [
        {"w": 12, "x": 0},
        {"w": 12, "x": 12},
    ]
    assert manifest_web_ui["video_preview_bridge"]["enabled"] is False
    assert manifest_web_ui["video_preview_bridge"]["auto_start"] is False
    assert manifest_web_ui["video_preview_bridge"]["cleanup_script"] == "scripts/post-launch.sh"


def test_video_watch_post_launch_collects_pre_launch_process_group():
    blueprint_dir = ROOT / "video_watch_assistant"
    child_pid: int | None = None
    process_group_id: int | None = None
    proc: subprocess.Popen | None = None
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        run_dir = root / "run"
        run_dir.mkdir()
        marker = root / "spawned.json"
        spawner = root / "spawn_child.py"
        spawner.write_text(
            "import json\n"
            "import os\n"
            "import subprocess\n"
            "import sys\n"
            "from pathlib import Path\n"
            "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'])\n"
            "Path(sys.argv[1]).write_text(json.dumps({\n"
            "    'parent_pid': os.getpid(),\n"
            "    'process_group_id': os.getpgrp(),\n"
            "    'child_pid': child.pid,\n"
            "}))\n"
        )
        try:
            proc = subprocess.Popen([sys.executable, str(spawner), str(marker)], start_new_session=True)
            assert _wait_until(marker.exists)
            process_info = json.loads(marker.read_text())
            child_pid = int(process_info["child_pid"])
            process_group_id = int(process_info["process_group_id"])
            proc.wait(timeout=5)
            assert _pid_exists(child_pid)

            process_file = run_dir / "pre_launch_process.json"
            process_file.write_text(json.dumps({
                "pid": int(process_info["parent_pid"]),
                "process_group_id": process_group_id,
            }))
            env = os.environ.copy()
            env.update({
                "MN_RUN_DIR": str(run_dir),
                "MN_PRE_LAUNCH_PROCESS_FILE": str(process_file),
                "MN_POST_LAUNCH_REASON": "test",
            })

            subprocess.run(
                ["bash", str(blueprint_dir / "scripts" / "post-launch.sh")],
                cwd=blueprint_dir,
                env=env,
                check=True,
                timeout=12,
            )

            assert _wait_until(lambda: not _pid_exists(child_pid), timeout=8)
        finally:
            if process_group_id is not None:
                try:
                    os.killpg(process_group_id, 9)
                except OSError:
                    pass
            if child_pid is not None and _pid_exists(child_pid):
                try:
                    os.kill(child_pid, 9)
                except OSError:
                    pass
            if proc is not None and proc.poll() is None:
                proc.kill()
                proc.wait(timeout=5)


def _load_video_watch_validator():
    path = ROOT / "video_watch_assistant" / "payloads" / "validation" / "validate_rtsp_source.py"
    spec = importlib.util.spec_from_file_location("video_watch_validate_rtsp_source", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_video_watch_default_validator_checks_demo_video(monkeypatch, tmp_path):
    validator = _load_video_watch_validator()
    demo = tmp_path / "sample.mp4"
    demo.write_bytes(b"fake-video")
    monkeypatch.setenv(
        "MN_BLUEPRINT_CONFIG_JSON",
        json.dumps({
            "video_source": {
                "uri": "rtsp://127.0.0.1:8554/video-watch",
                "demo_video": str(demo),
            }
        }),
    )
    monkeypatch.setattr(validator.shutil, "which", lambda _name: "/usr/bin/ffprobe")
    calls = []

    def fake_run(command, **_kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="video\n", stderr="")

    monkeypatch.setattr(validator.subprocess, "run", fake_run)

    assert validator.main() == 0
    assert str(demo) in calls[0]
    assert "-rtsp_transport" not in calls[0]


def test_video_watch_dynamic_mapped_validator_skips_ffprobe_when_missing(monkeypatch, tmp_path):
    validator = _load_video_watch_validator()
    demo = tmp_path / "sample.mp4"
    demo.write_bytes(b"fake-video")
    monkeypatch.setenv(
        "MN_BLUEPRINT_CONFIG_JSON",
        json.dumps({
            "video_source": {
                "uri": "rtsp://127.0.0.1:8567/video-watch",
                "demo_video": str(demo),
            }
        }),
    )
    monkeypatch.setattr(validator.shutil, "which", lambda _name: None)

    def fail_run(*_args, **_kwargs):
        raise AssertionError("demo mapped endpoint should not require ffprobe")

    monkeypatch.setattr(validator.subprocess, "run", fail_run)

    assert validator.main() == 0


def test_video_watch_runtime_bundle_allows_host_validated_demo_video(monkeypatch, tmp_path):
    validator = _load_video_watch_validator()
    runtime_bundle = tmp_path / "bundle_123"
    runtime_bundle.mkdir()
    monkeypatch.chdir(runtime_bundle)
    monkeypatch.setenv(
        "MN_BLUEPRINT_CONFIG_JSON",
        json.dumps({
            "video_source": {
                "uri": "rtsp://127.0.0.1:8567/video-watch",
                "demo_video": "data/sample.mp4",
            }
        }),
    )
    monkeypatch.setattr(validator.shutil, "which", lambda _name: None)
    monkeypatch.setattr(validator.Path, "cwd", lambda: Path("/tmp/bundle_123"))

    assert validator.main() == 0


def test_video_watch_external_rtsp_validator_probes_stream(monkeypatch):
    validator = _load_video_watch_validator()
    monkeypatch.setenv(
        "MN_BLUEPRINT_CONFIG_JSON",
        json.dumps({"video_source": {"uri": "rtsp://camera.example/live"}}),
    )
    monkeypatch.setattr(validator.shutil, "which", lambda _name: "/usr/bin/ffprobe")
    calls = []

    def fake_run(command, **_kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="video\n", stderr="")

    monkeypatch.setattr(validator.subprocess, "run", fake_run)

    assert validator.main() == 0
    assert "rtsp://camera.example/live" in calls[0]
    assert "-rtsp_transport" in calls[0]
