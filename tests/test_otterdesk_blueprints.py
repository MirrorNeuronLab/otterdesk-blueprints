from __future__ import annotations

import importlib.util
import json
import os
import py_compile
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
SUPPORT_SRC = WORKSPACE / "mn-skills" / "blueprint_support_skill" / "src"
AGENTS_ROOT = WORKSPACE / "mn-agents"
if str(SUPPORT_SRC) not in sys.path:
    sys.path.insert(0, str(SUPPORT_SRC))

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
    WorkflowManifestError,
    compile_workflow_graph,
    run_workflow_manifest,
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


def _contains_key(value, target: str) -> bool:
    if isinstance(value, dict):
        return any(key == target or _contains_key(item, target) for key, item in value.items())
    if isinstance(value, list):
        return any(_contains_key(item, target) for item in value)
    return False


def _completion_threshold(value) -> bool:
    if isinstance(value, int):
        return value > 0
    if isinstance(value, str):
        return value.isdigit() and int(value) > 0
    return False


def test_otterdesk_blueprints_are_workflow_driven_manifests():
    for manifest_path in _manifest_paths():
        manifest = json.loads(manifest_path.read_text())
        blueprint_id = manifest["metadata"]["blueprint_id"]

        assert manifest["apiVersion"] == "mn.workflow/v1", blueprint_id
        assert manifest["kind"] == "Workflow", blueprint_id
        assert manifest["id"] == blueprint_id
        assert manifest["contract"]["inputs"], blueprint_id
        assert manifest["contract"]["outputs"]["primary"]["path"] == "final_artifact.json"
        assert manifest["contract"]["status"]["heartbeat"] is True, blueprint_id
        assert validate_workflow_manifest(manifest) == []

        steps = manifest["flow"]["steps"]
        bindings = manifest["runtime"]["bindings"]
        assert steps, blueprint_id
        assert manifest["flow"]["entrypoint"] == steps[0]["id"]
        if manifest.get("type") == "service":
            node_ids = {node["node_id"] for node in manifest["nodes"]}
            assert set(manifest["entrypoints"]) <= node_ids, blueprint_id
        else:
            assert manifest["entrypoints"] == [manifest["flow"]["entrypoint"]]
        assert manifest["flow"]["graph"]["schema"] == "mn.workflow.problem_graph/v1"
        assert manifest["flow"]["graph"]["dynamic"]["enabled"] is False
        assert "nodes" in manifest and "edges" in manifest
        assert manifest["metadata"]["standard"]["workflow_model"] == "contract -> flow -> runtime"
        for step in steps:
            assert {"id", "kind", "label", "goal", "action", "run", "emits", "on"} <= set(step), (blueprint_id, step)
            assert {"required", "retry", "failure_policy", "uncertainty"} <= set(step["control"]), (blueprint_id, step)
            assert step["control"]["retry"]["max_attempts"] >= 1, (blueprint_id, step)
            assert step["run"] in bindings, (blueprint_id, step)
            workers = bindings[step["run"]].get("workers") or []
            assert workers, (blueprint_id, step["run"])
            for worker in workers:
                assert {"id", "role"} <= set(worker), (blueprint_id, step["run"], worker)


def test_otterdesk_topology_metadata_matches_runtime_nodes():
    for manifest_path in _manifest_paths():
        manifest = json.loads(manifest_path.read_text())
        blueprint_id = manifest["metadata"]["blueprint_id"]
        runtime_nodes = {node["node_id"]: node["uses"] for node in manifest["nodes"]}
        metadata_nodes = {
            node["node_id"]: node["uses"]
            for node in manifest["metadata"]["agent_templates"]["nodes"]
        }

        assert metadata_nodes == runtime_nodes, blueprint_id


def test_otterdesk_completion_contract_is_explicit_and_terminal_sinks_are_reachable():
    for manifest_path in _manifest_paths():
        manifest = json.loads(manifest_path.read_text())
        blueprint_id = manifest["metadata"]["blueprint_id"]
        node_by_id = {node["node_id"]: node for node in manifest["nodes"]}
        step_runs = {step["run"] for step in manifest["flow"]["steps"]}
        outgoing_counts: dict[str, int] = {}
        incoming_edges: dict[str, list[dict]] = {}

        assert not _contains_key(manifest, "complete_job"), blueprint_id
        assert not _contains_key(manifest, "complete_job?"), blueprint_id

        for edge in manifest["edges"]:
            assert "message_type" in edge and edge["message_type"], (blueprint_id, edge)
            assert "event" not in edge, (blueprint_id, edge)
            assert edge["from_node"] in node_by_id, (blueprint_id, edge)
            assert edge["to_node"] in node_by_id, (blueprint_id, edge)
            outgoing_counts[edge["from_node"]] = outgoing_counts.get(edge["from_node"], 0) + 1
            incoming_edges.setdefault(edge["to_node"], []).append(edge)

        terminal_sinks = []
        for node in manifest["nodes"]:
            node_id = node["node_id"]
            config = node.get("with", {})
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
        final_step_node = manifest["flow"]["graph"]["sink"]
        final_step_config = node_by_id[final_step_node]["with"]
        assert sink_edges[0]["from_node"] == final_step_node, blueprint_id
        assert sink_edges[0]["message_type"] == final_step_config["output_message_type"], blueprint_id


def test_otterdesk_rendered_completion_contract_is_valid():
    for manifest_path in _manifest_paths():
        manifest = json.loads(manifest_path.read_text())
        blueprint_id = manifest["metadata"]["blueprint_id"]
        rendered = render_manifest_agent_templates(manifest, AGENTS_ROOT)
        rendered_nodes = {node["node_id"]: node for node in rendered["nodes"]}
        step_runs = {step["run"] for step in manifest["flow"]["steps"]}
        outgoing_counts: dict[str, int] = {}

        for edge in rendered.get("edges", manifest["edges"]):
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


def test_otterdesk_workflow_runtime_executes_manifest_steps(tmp_path):
    manifest_path = ROOT / "personal_income_tax_expert" / "manifest.json"
    result = run_workflow_manifest_file(
        manifest_path,
        run_dir=tmp_path / "tax-workflow-run",
        run_id="tax-workflow-run",
        auto_human="approve",
        speed=0.01,
        ui=False,
    )

    assert result["run"]["status"] == "completed"
    assert result["workflow"]["steps"] == [
        "intake_documents",
        "prepare_income_workpapers",
        "prepare_property_workpapers",
        "prepare_investment_workpapers",
        "merge_tax_workpapers",
        "audit_and_manager_review",
        "write_review_packet",
    ]
    assert result["workflow"]["graph"]["mode"] == "static_dag"
    assert result["workflow"]["graph"]["layers"][1] == [
        "prepare_income_workpapers",
        "prepare_property_workpapers",
        "prepare_investment_workpapers",
    ]
    run_dir = tmp_path / "tax-workflow-run"
    assert {"run.json", "config.json", "inputs.json", "events.jsonl", "resources.jsonl", "result.json", "final_artifact.json"} <= {
        path.name for path in run_dir.iterdir()
    }
    event_records = [json.loads(line) for line in (run_dir / "events.jsonl").read_text().splitlines() if line.strip()]
    events = [record["type"] for record in event_records]
    assert "workflow_step_started" in events
    assert "workflow_step_attempt_completed" in events
    assert "workflow_graph_compiled" in events
    assert "workflow_edge_satisfied" in events
    assert "workflow_join_waiting" in events
    assert "human_decision_applied" in events
    branch_ids = {"prepare_income_workpapers", "prepare_property_workpapers", "prepare_investment_workpapers"}
    branch_start_indexes = [
        index
        for index, record in enumerate(event_records)
        if record["type"] == "workflow_step_started" and record.get("payload", {}).get("step") in branch_ids
    ]
    branch_completion_indexes = [
        index
        for index, record in enumerate(event_records)
        if record["type"] == "workflow_step_completed" and record.get("payload", {}).get("step") in branch_ids
    ]
    assert len(branch_start_indexes) == 3
    assert len(branch_completion_indexes) == 3
    assert max(branch_start_indexes) < min(branch_completion_indexes)


def test_otterdesk_batch_workflows_complete_with_shared_runner(tmp_path):
    for manifest_path in _manifest_paths():
        manifest = json.loads(manifest_path.read_text())
        if manifest.get("type") == "service":
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
        assert len(result["workflow"]["steps"]) == len(manifest["flow"]["steps"]), blueprint_id
        assert (run_dir / "final_artifact.json").exists(), blueprint_id
        event_records = [json.loads(line) for line in (run_dir / "events.jsonl").read_text().splitlines() if line.strip()]
        event_types = {record["type"] for record in event_records}
        assert "workflow_step_attempt_completed" in event_types, blueprint_id
        assert "workflow_finished" in event_types, blueprint_id


def test_tax_workflow_compiles_as_static_fork_join_graph():
    manifest_path = ROOT / "personal_income_tax_expert" / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    graph = compile_workflow_graph(manifest)

    assert graph.enabled is True
    assert graph.schema == "mn.workflow.problem_graph/v1"
    assert graph.source == "intake_documents"
    assert graph.sink == "write_review_packet"
    assert graph.execution == "parallel"
    assert graph.layers[1] == [
        "prepare_income_workpapers",
        "prepare_property_workpapers",
        "prepare_investment_workpapers",
    ]
    assert graph.parents["merge_tax_workpapers"] == [
        "prepare_income_workpapers",
        "prepare_property_workpapers",
        "prepare_investment_workpapers",
    ]
    merge_edges = {edge.from_step: edge for edge in graph.edges_to("merge_tax_workpapers")}
    assert merge_edges["prepare_income_workpapers"].required is True
    assert merge_edges["prepare_property_workpapers"].required is False
    assert "partial" in merge_edges["prepare_property_workpapers"].accepts
    income_workers = manifest["runtime"]["bindings"]["prepare_income_workpapers"]["workers"]
    assert [worker["id"] for worker in income_workers] == ["income_preparer", "income_validator"]
    assert income_workers[1]["kind"] == "validator"
    assert income_workers[1]["depends_on"] == ["income_preparer"]


def test_static_graph_validation_rejects_cycles_and_overlapping_parallel_outputs():
    manifest_path = ROOT / "personal_income_tax_expert" / "manifest.json"
    manifest = json.loads(manifest_path.read_text())

    cyclic = json.loads(json.dumps(manifest))
    cyclic["flow"]["graph"]["edges"].append(
        {
            "id": "write_review_packet_to_intake_documents",
            "from": "write_review_packet",
            "to": "intake_documents",
            "event": "tax_packet_ready",
        }
    )
    with pytest.raises(WorkflowManifestError, match="source must not have incoming edges|sink must not have outgoing edges|acyclic"):
        validate_workflow_manifest(cyclic)

    overlapping = json.loads(json.dumps(manifest))
    for step in overlapping["flow"]["steps"]:
        if step["id"] in {"prepare_income_workpapers", "prepare_property_workpapers"}:
            step["out"] = {"workpapers": "$state.workpapers.branch"}
    with pytest.raises(WorkflowManifestError, match="overlapping output paths"):
        validate_workflow_manifest(overlapping)

    duplicate_edge = json.loads(json.dumps(manifest))
    duplicate_edge["flow"]["graph"]["edges"][1]["id"] = duplicate_edge["flow"]["graph"]["edges"][0]["id"]
    with pytest.raises(WorkflowManifestError, match="duplicate flow graph edge id"):
        validate_workflow_manifest(duplicate_edge)

    missing_source = json.loads(json.dumps(manifest))
    del missing_source["flow"]["graph"]["source"]
    with pytest.raises(WorkflowManifestError, match="missing required field flow.graph.source"):
        validate_workflow_manifest(missing_source)

    unreachable = json.loads(json.dumps(manifest))
    unreachable["flow"]["steps"].append(
        {
            **json.loads(json.dumps(unreachable["flow"]["steps"][1])),
            "id": "orphan_workpapers",
            "run": "prepare_income_workpapers",
        }
    )
    with pytest.raises(WorkflowManifestError, match="missing an incoming edge|unreachable from source"):
        validate_workflow_manifest(unreachable)

    invalid_retry = json.loads(json.dumps(manifest))
    invalid_retry["flow"]["steps"][1]["control"]["retry"]["max_attempts"] = 0
    with pytest.raises(WorkflowManifestError, match="max_attempts must be at least 1"):
        validate_workflow_manifest(invalid_retry)

    unbounded_retry = json.loads(json.dumps(manifest))
    unbounded_retry["flow"]["steps"][1]["control"]["retry"]["unlimited"] = True
    with pytest.raises(WorkflowManifestError, match="must be bounded"):
        validate_workflow_manifest(unbounded_retry)

    invalid_timeout = json.loads(json.dumps(manifest))
    invalid_timeout["flow"]["steps"][1]["control"]["timeout_seconds"] = -1
    with pytest.raises(WorkflowManifestError, match="timeout_seconds must be greater than or equal to zero"):
        validate_workflow_manifest(invalid_timeout)

    invalid_join = json.loads(json.dumps(manifest))
    invalid_join["flow"]["steps"][4]["join"] = {"mode": "sometimes"}
    with pytest.raises(WorkflowManifestError, match="join.mode"):
        validate_workflow_manifest(invalid_join)


def test_optional_tax_branch_can_finish_partial_and_still_merge(tmp_path):
    manifest = json.loads((ROOT / "personal_income_tax_expert" / "manifest.json").read_text())
    for step in manifest["flow"]["steps"]:
        if step["id"] == "prepare_property_workpapers":
            step["control"]["timeout_seconds"] = 0
            step["control"]["retry"]["max_attempts"] = 1

    result = run_workflow_manifest(
        manifest,
        run_dir=tmp_path / "tax-partial-run",
        run_id="tax-partial-run",
        auto_human="approve",
        speed=0.01,
        ui=False,
    )

    assert result["run"]["status"] == "completed"
    event_records = [
        json.loads(line)
        for line in (tmp_path / "tax-partial-run" / "events.jsonl").read_text().splitlines()
        if line.strip()
    ]
    assert any(
        record["type"] == "workflow_step_partial"
        and record.get("payload", {}).get("step") == "prepare_property_workpapers"
        for record in event_records
    )
    assert any(
        record["type"] == "workflow_edge_satisfied"
        and record.get("payload", {}).get("from") == "prepare_property_workpapers"
        and record.get("payload", {}).get("outcome") == "partial"
        and record.get("payload", {}).get("satisfied") is True
        for record in event_records
    )


def test_otterdesk_blueprints_declare_membrane_context_memory_layer():
    for manifest_path in _manifest_paths():
        blueprint_dir = manifest_path.parent
        manifest = json.loads(manifest_path.read_text())
        config = json.loads((blueprint_dir / "config" / "default.json").read_text())
        blueprint_id = manifest["metadata"]["blueprint_id"]
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
        "personal_income_tax_expert": "approval_required",
        "portfolio_risk_review_assistant": "approval_required",
        "property_deal_research_assistant": "approval_required",
        "video_watch_assistant": "notice_only",
        "generic_customer_service_voice_coworker": "notice_only",
        "invoice_bill_extraction_assistant": "approval_required",
        "legal_contract_clause_review_assistant": "approval_required",
        "medical_deid_record_intake_assistant": "approval_required",
        "tax_form_ocr_capture_assistant": "approval_required",
        "bank_statement_extraction_assistant": "approval_required",
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
        config = json.loads((blueprint_dir / "config" / "default.json").read_text())
        metadata = manifest["metadata"]
        blueprint_id = metadata["blueprint_id"]

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
        assert manifest["graph_id"] == entry["graph_id"]
        assert manifest["job_name"] == entry["job_name"]


def test_generic_customer_service_voice_blueprint_contract():
    blueprint_dir = ROOT / "generic_customer_service_voice_coworker"
    manifest = json.loads((blueprint_dir / "manifest.json").read_text())
    config = json.loads((blueprint_dir / "config" / "default.json").read_text())
    script = (blueprint_dir / "scripts" / "pre-launch.sh").read_text()
    cleanup = (blueprint_dir / "scripts" / "post-launch.sh").read_text()

    assert manifest["type"] == "service"
    assert "voice_service" in manifest["entrypoints"]
    assert manifest["runtime"]["resources"]["gpu"]["min_count"] == 1
    assert manifest["runtime"]["worker_defaults"]["pool"] == "nvidia-accelerated"
    assert manifest["runtime"]["models"]["primary"]["model"] == "otterdesk-voice-llm:default"
    assert manifest["runtime"]["models"]["asr"]["model"] == "otterdesk-voice-asr:default"
    assert manifest["runtime"]["models"]["tts"]["model"] == "otterdesk-voice-tts:default"
    voice_node = next(node for node in manifest["nodes"] if node["node_id"] == "voice_service")
    assert voice_node["with"]["execution_profile"] == "nvidia-accelerated-voice"
    assert voice_node["with"]["pool"] == "nvidia-accelerated"
    assert voice_node["with"]["pool_slots"] == 1
    assert voice_node["with"]["agent_beacon_required"] is False
    assert voice_node["with"]["command"] == ["bash", "scripts/run_voice_service.sh"]
    assert voice_node["with"]["upload_path"] == "voice_service"
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
    assert voice_node["with"]["public_url"] == "https://localhost:7863/customer-service"

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
    assert "scripts/nemotron.sh stop" not in cleanup


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


def test_property_deal_final_artifact_uses_product_output_fields(tmp_path):
    runner_path = ROOT / "property_deal_research_assistant" / "payloads" / "simulation_loop" / "scripts" / "run_blueprint.py"
    spec = importlib.util.spec_from_file_location("otterdesk_property_runner_product_test", runner_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    result = module.run_blueprint(
        inputs={"steps": 1, "seed": 77},
        config={"llm": {"mode": "fake"}},
        runs_root=tmp_path,
        run_id="property-product-contract",
    )
    artifact = result["final_artifact"]

    assert set(FINAL_ARTIFACT_REQUIRED_FIELDS) <= set(artifact)
    assert artifact["evidence"]
    assert {"inputs.json", "events.jsonl", "result.json"} <= set(artifact["source_refs"])

    events = [
        json.loads(line)
        for line in (tmp_path / "property-product-contract" / "events.jsonl").read_text().splitlines()
        if line.strip()
    ]
    event_types = {event["type"] for event in events}
    assert {"blueprint_status", "blueprint_phase_started", "blueprint_phase_completed", "artifact_written"} <= event_types


def test_video_watch_declares_otterdesk_chat_system_prompt():
    blueprint_dir = ROOT / "video_watch_assistant"
    manifest = json.loads((blueprint_dir / "manifest.json").read_text())
    prompt = (blueprint_dir / "prompts" / "chat-system.md").read_text()

    assert "prompts/" in manifest["metadata"]["configuration_contract"]["optional_files"]
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
    assert [step["label"] for step in manifest["flow"]["steps"]] == [
        "Start Video Monitor",
        "Sample Video Frames",
        "Detect Visual Targets",
        "Write Watch Summary",
    ]


def test_otterdesk_nodes_use_shared_agent_templates_and_render():
    for manifest_path in _manifest_paths():
        manifest = json.loads(manifest_path.read_text())
        original_nodes = {node["node_id"]: node for node in manifest["nodes"]}
        control_by_step = {
            step["id"]: step["control"]
            for step in manifest.get("flow", {}).get("steps", [])
            if isinstance(step.get("control"), dict)
        }
        assert manifest.get("nodes"), manifest_path
        for node in manifest["nodes"]:
            assert "uses" in node, (manifest_path.parent.name, node.get("node_id"))
            assert node["uses"].startswith("mn-agents."), (manifest_path.parent.name, node.get("node_id"))
            assert "@" in node["uses"] and not node["uses"].endswith("@latest")
            assert isinstance(node.get("with"), dict), (manifest_path.parent.name, node.get("node_id"))
            assert not {"agent_type", "type", "role", "config"} & set(node), (
                manifest_path.parent.name,
                node.get("node_id"),
            )

        rendered = render_manifest_agent_templates(manifest, AGENTS_ROOT)
        assert len(rendered["nodes"]) == len(manifest["nodes"])
        assert all("uses" not in node and "with" not in node for node in rendered["nodes"])
        for node in rendered["nodes"]:
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
        workflow_control = manifest.get("runtime", {}).get("workflow_control")
        assert workflow_control, manifest_path.parent.name
        assert workflow_control["schema_version"] == "mn.workflow.runtime_control.v1"
        assert workflow_control["enabled"] is True
        assert workflow_control["source_of_truth"] == "flow.steps"
        assert workflow_control["state_ledger"]["enabled"] is True
        assert workflow_control["state_ledger"]["persisted_field"] == "workflow_state"
        assert set(workflow_control["state_ledger"]["step_statuses"]) == expected_statuses
        assert workflow_control["state_ledger"]["message_ledger"] is True
        assert workflow_control["state_ledger"]["delivery_semantics"] == "at_least_once_with_idempotency"
        assert workflow_control["attempts"]["stale_attempt_outputs"] == "ignore"
        assert workflow_control["attempts"]["retry_policy_source"] == "flow.steps[].control.retry"
        assert workflow_control["attempts"]["timeout_source"] == "flow.steps[].control.timeout_seconds"
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
        for step in manifest.get("flow", {}).get("steps", []):
            control = step.get("control", {})
            assert isinstance(control.get("timeout_seconds"), int), (manifest_path.parent.name, step.get("id"))
            assert control["timeout_seconds"] > 0, (manifest_path.parent.name, step.get("id"))
            assert control["retry"]["max_attempts"] >= 1, (manifest_path.parent.name, step.get("id"))
            assert control["retry"]["backoff_seconds"] >= 0, (manifest_path.parent.name, step.get("id"))


def test_personal_income_tax_expert_runtime_topology_mirrors_workflow_graph():
    manifest = json.loads((ROOT / "personal_income_tax_expert" / "manifest.json").read_text())
    executor_nodes = [
        node for node in manifest["nodes"] if node["uses"].startswith("mn-agents.data_python_executor@")
    ]
    rendered = render_manifest_agent_templates(manifest, AGENTS_ROOT)
    rendered_nodes = {node["node_id"]: node for node in rendered["nodes"]}

    assert manifest["entrypoints"] == ["intake_documents"]
    assert [node["node_id"] for node in executor_nodes] == [
        "intake_documents",
        "prepare_income_workpapers",
        "prepare_property_workpapers",
        "prepare_investment_workpapers",
        "audit_and_manager_review",
        "write_review_packet",
    ]
    for node in executor_nodes:
        node_id = node["node_id"]
        node_config = node["with"]
        rendered_config = rendered_nodes[node_id]["config"]
        assert node_config["environment"]["MN_WORKFLOW_STEP_ID"] == node_id
        assert rendered_config["environment"]["MN_WORKFLOW_STEP_ID"] == node_id
        if node_id == "write_review_packet":
            assert "safe_to_retry" not in node_config
            assert "idempotent" not in node_config
        else:
            assert node_config["safe_to_retry"] is True
            assert node_config["idempotent"] is True
            assert node_config["side_effect"] == "read"
            assert rendered_config["safe_to_retry"] is True
            assert rendered_config["idempotent"] is True
            assert rendered_config["side_effect"] == "read"
    merge_config = next(node["with"] for node in manifest["nodes"] if node["node_id"] == "merge_tax_workpapers")
    rendered_merge_config = rendered_nodes["merge_tax_workpapers"]["config"]
    assert merge_config["complete_on_message"] is True
    assert merge_config["output_message_type"] == "tax_workpapers_merged"
    assert rendered_merge_config["output_message_type"] == "tax_workpapers_merged"
    report_config = next(node["with"] for node in manifest["nodes"] if node["node_id"] == "report_sink")
    rendered_report_config = rendered_nodes["report_sink"]["config"]
    assert report_config["terminal_sink"] is True
    assert report_config["complete_run"] is True
    assert rendered_report_config["terminal_sink"] is True
    assert rendered_report_config["complete_run"] is True
    assert [edge["from_node"] for edge in manifest["edges"][:3]] == ["intake_documents"] * 3
    assert {edge["to_node"] for edge in manifest["edges"][:3]} == {
        "prepare_income_workpapers",
        "prepare_property_workpapers",
        "prepare_investment_workpapers",
    }
    assert [edge["from_node"] for edge in manifest["edges"][3:6]] == [
        "prepare_income_workpapers",
        "prepare_property_workpapers",
        "prepare_investment_workpapers",
    ]
    assert {edge["to_node"] for edge in manifest["edges"][3:6]} == {"merge_tax_workpapers"}
    assert manifest["edges"][6] == {
        "edge_id": "merge_to_audit",
        "from_node": "merge_tax_workpapers",
        "message_type": "tax_workpapers_merged",
        "to_node": "audit_and_manager_review",
    }
    assert manifest["nodes"][-1]["node_id"] == "report_sink"
    assert manifest["edges"][-1] == {
        "edge_id": "packet_to_report",
        "from_node": "write_review_packet",
        "message_type": "blueprint_report",
        "to_node": "report_sink",
    }


def test_personal_income_tax_expert_runtime_branch_step_exits_without_full_packet(tmp_path):
    script = ROOT / "personal_income_tax_expert" / "payloads" / "tax_workflow" / "scripts" / "run_blueprint.py"
    env = os.environ.copy()
    env["MN_WORKFLOW_STEP_ID"] = "prepare_income_workpapers"
    result = subprocess.run(
        [sys.executable, str(script), "--no-run-store", "--run-id", "tax-branch-step"],
        cwd=script.parents[1],
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    decoded = json.loads(result.stdout)

    assert decoded["schema"] == "mn.workflow.step_result.v1"
    assert decoded["agent_id"] == "prepare_income_workpapers"
    assert decoded["workflow_step_id"] == "prepare_income_workpapers"
    assert decoded["status"] == "completed"
    assert "final_artifact" not in decoded


def test_personal_income_tax_expert_runtime_branch_step_infers_agent_id_without_full_packet(tmp_path):
    script = ROOT / "personal_income_tax_expert" / "payloads" / "tax_workflow" / "scripts" / "run_blueprint.py"
    env = os.environ.copy()
    env.pop("MN_WORKFLOW_STEP_ID", None)
    env["MN_AGENT_ID"] = "prepare_income_workpapers"
    result = subprocess.run(
        [sys.executable, str(script), "--no-run-store", "--run-id", "tax-agent-id-step"],
        cwd=script.parents[1],
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    decoded = json.loads(result.stdout)

    assert decoded["schema"] == "mn.workflow.step_result.v1"
    assert decoded["workflow_step_id"] == "prepare_income_workpapers"
    assert decoded["status"] == "completed"
    assert "final_artifact" not in decoded


def test_personal_income_tax_expert_runtime_branch_step_infers_message_destination(tmp_path):
    script = ROOT / "personal_income_tax_expert" / "payloads" / "tax_workflow" / "scripts" / "run_blueprint.py"
    message_file = tmp_path / "message.json"
    message_file.write_text(
        json.dumps(
            {
                "to": "prepare_property_workpapers",
                "type": "tax_intake_ready",
                "payload": {"tax_year": 2025, "filing_status": "single"},
            }
        ),
        encoding="utf-8",
    )
    env = os.environ.copy()
    env.pop("MN_WORKFLOW_STEP_ID", None)
    env.pop("MN_AGENT_ID", None)
    env["MN_MESSAGE_FILE"] = str(message_file)
    result = subprocess.run(
        [sys.executable, str(script), "--no-run-store", "--run-id", "tax-message-step"],
        cwd=script.parents[1],
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    decoded = json.loads(result.stdout)

    assert decoded["schema"] == "mn.workflow.step_result.v1"
    assert decoded["workflow_step_id"] == "prepare_property_workpapers"
    assert decoded["inputs"]["tax_year"] == 2025
    assert decoded["status"] == "completed"
    assert "final_artifact" not in decoded


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
    visual_node = next(node for node in rendered["nodes"] if node["node_id"] == "visual_detector")
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
