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


def test_otterdesk_nodes_use_shared_agent_templates_and_render():
    for manifest_path in _manifest_paths():
        manifest = json.loads(manifest_path.read_text())
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


def test_personal_income_tax_expert_runs_as_single_runtime_executor():
    manifest = json.loads((ROOT / "personal_income_tax_expert" / "manifest.json").read_text())
    executor_nodes = [
        node for node in manifest["nodes"] if node["uses"].startswith("mn-agents.data_python_executor@")
    ]

    assert manifest["entrypoints"] == ["tax_workflow_runner"]
    assert [node["node_id"] for node in executor_nodes] == ["tax_workflow_runner"]
    assert manifest["nodes"][-1]["node_id"] == "report_sink"
    assert manifest["edges"] == [
        {
            "edge_id": "tax_workflow_to_report",
            "from_node": "tax_workflow_runner",
            "message_type": "blueprint_report",
            "to_node": "report_sink",
        }
    ]


def test_video_watch_openshell_policy_is_generated_by_shared_helper(tmp_path):
    blueprint_dir = ROOT / "video_watch_assistant"
    config = json.loads((blueprint_dir / "config" / "default.json").read_text())
    manifest = json.loads((blueprint_dir / "manifest.json").read_text())
    network = config["openshell_network"]
    assert manifest["metadata"]["openshell_network"] == network

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
    assert dashboard["video_preview_bridge"]["enabled"] is False
    assert dashboard["video_preview_bridge"]["auto_start"] is False
    assert dashboard["video_preview_bridge"]["cleanup_script"] == "scripts/post-launch.sh"

    manifest_web_ui = manifest["metadata"]["web_ui"]
    assert manifest_web_ui["browser_video_source"] == "disabled"
    assert manifest_web_ui["browser_publish_source"] == "disabled"
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
