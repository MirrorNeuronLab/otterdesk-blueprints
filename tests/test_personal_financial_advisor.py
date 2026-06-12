from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = (
    ROOT
    / "personal_financial_advisor"
    / "payloads"
    / "document_workflow"
    / "scripts"
    / "run_blueprint.py"
)


def _load_runner():
    spec = importlib.util.spec_from_file_location("personal_financial_advisor_runner", RUNNER_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def _write_fixture_folder(path: Path) -> None:
    path.mkdir()
    (path / "paystub.txt").write_text(
        "\n".join(
            [
                "ACME Payroll Paystub",
                "Salary income $5,200.00",
                "Deposit to checking $4,100.00",
            ]
        ),
        encoding="utf-8",
    )
    (path / "checking_statement.txt").write_text(
        "\n".join(
            [
                "Community Bank Statement",
                "Opening balance $2,000.00",
                "Deposit payroll credit $4,100.00",
                "Debit grocery purchase $145.22",
                "Service fee $12.00",
                "Closing balance $5,942.78",
            ]
        ),
        encoding="utf-8",
    )
    (path / "grocery_receipt.txt").write_text(
        "\n".join(
            [
                "Fresh Market Receipt",
                "Merchant Fresh Market",
                "Total paid $145.22",
            ]
        ),
        encoding="utf-8",
    )
    (path / "utility_bill.txt").write_text(
        "\n".join(
            [
                "Utility bill",
                "Amount due $88.40",
                "Due date 2026-07-01",
            ]
        ),
        encoding="utf-8",
    )


def _install_fake_research(monkeypatch, runner) -> None:
    class FakeW3mBrowserConfig:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    def fake_research_topic(query, config=None, source_urls=None, max_sources=3):
        return {
            "query": query,
            "search_url": "https://duckduckgo.com/html/?q=finance",
            "source_count": 1,
            "summary": "Consumer guidance: review fees, due dates, and household budget tradeoffs before acting.",
            "warnings": [],
            "sources": [
                {
                    "url": "https://consumer.gov/managing-your-money",
                    "title": "Managing Your Money",
                    "snippet": "Review bills, fees, and spending before making financial decisions.",
                }
            ],
        }

    monkeypatch.setattr(runner, "W3mBrowserConfig", FakeW3mBrowserConfig)
    monkeypatch.setattr(runner, "research_topic", fake_research_topic)
    monkeypatch.setattr(
        runner,
        "compile_research_context",
        lambda *args, **kwargs: {"enabled": True, "use_model_compression": True, "compressed": True},
    )


def test_personal_financial_advisor_writes_review_report_outputs(tmp_path, monkeypatch):
    runner = _load_runner()
    _install_fake_research(monkeypatch, runner)
    docs = tmp_path / "finance-inbox"
    outputs = tmp_path / "exports"
    _write_fixture_folder(docs)

    result = runner.run_blueprint(
        inputs={
            "document_folder": str(docs),
            "output_folder": str(outputs),
            "monitoring": {"enabled": True, "poll_interval_seconds": 1, "max_cycles": 1},
        },
        runs_root=tmp_path,
        run_id="advisor-unit",
    )

    artifact = result["final_artifact"]
    assert result["blueprint_id"] == "personal_financial_advisor"
    assert artifact["type"] == "personal_financial_advisor_report"
    assert artifact["status"] in {"review_ready", "needs_review"}
    assert artifact["advisor_message"]
    assert artifact["document_summary"]["document_count"] == 4
    assert artifact["document_summary"]["document_types"]["income_document"] >= 1
    assert artifact["income_summary"]["entry_count"] >= 1
    assert artifact["expense_summary"]["entry_count"] >= 1
    assert artifact["risk_register"]
    assert artifact["advisor_recommendations"]
    assert artifact["reminders"]
    assert artifact["research_summary"]
    assert artifact["research_sources"]
    assert artifact["research_warnings"] == []
    assert artifact["context_compression"]["use_model_compression"] is True
    assert artifact["watch_state"]["mode"] == "watch"
    assert artifact["watch_state"]["cycles_completed"] == 1
    assert len(artifact["watch_state"]["processed_files"]) == 4
    assert all("sha256" in item for item in artifact["watch_state"]["processed_files"])
    assert artifact["evidence"]
    assert all("ocr_required" in item and "extraction_method" in item for item in artifact["evidence"])
    assert {item["kind"] for item in artifact["output_files"]} == {"final_artifact_json", "report_markdown"}

    for item in artifact["output_files"]:
        assert Path(item["path"]).exists()

    markdown_path = next(Path(item["path"]) for item in artifact["output_files"] if item["kind"] == "report_markdown")
    markdown_text = markdown_path.read_text(encoding="utf-8")
    assert "# Personal Financial Advisor Report" in markdown_text
    assert "## Risk Reminders" in markdown_text
    assert "## Research Context" in markdown_text
    assert "Managing Your Money" in markdown_text
    assert "review-only report" in markdown_text

    run_artifact = json.loads((tmp_path / "advisor-unit" / "final_artifact.json").read_text(encoding="utf-8"))
    assert run_artifact["type"] == "personal_financial_advisor_report"


def test_personal_financial_advisor_manifest_is_service_without_terminal_sink():
    manifest = json.loads((ROOT / "personal_financial_advisor" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["type"] == "service"

    nodes = manifest["agents"]["nodes"]
    edges = manifest["agents"]["edges"]
    templates = manifest["metadata"]["agent_templates"]["nodes"]
    rendered = manifest["metadata"]["agent_templates"]["rendered"]
    assert "report_sink" not in {node["node_id"] for node in nodes}
    assert "report_sink" not in {node["node_id"] for node in templates}
    assert "report_sink" not in {node["node_id"] for node in rendered}
    assert all(edge["from_node"] != "report_sink" and edge["to_node"] != "report_sink" for edge in edges)
    assert all(not node.get("config", {}).get("terminal_sink") for node in nodes)
    assert all(not node.get("config", {}).get("complete_run") for node in nodes)
    node_by_id = {node["node_id"]: node for node in nodes}
    rendered_by_id = {node["node_id"]: node["rendered_node"] for node in rendered}
    docker_nodes = [
        node["node_id"]
        for node in nodes
        if node["config"]["runner_module"] == "MirrorNeuron.Runner.DockerWorker"
    ]
    assert docker_nodes == ["financial_market_researcher"]

    for node_id, node in node_by_id.items():
        config = node["config"]
        rendered_config = rendered_by_id[node_id]["config"]
        assert config["environment"]["MN_WORKFLOW_STEP_ID"] == node_id
        assert rendered_config["environment"]["MN_WORKFLOW_STEP_ID"] == node_id
        assert "publish_ports" not in config
        if node_id == "financial_market_researcher":
            assert config["runner_module"] == "MirrorNeuron.Runner.DockerWorker"
            assert config["docker_worker_image"] == "document_workflow/docker_worker"
            assert config["image"] == "mirror-neuron/personal-financial-advisor:local"
            assert config["command"] == ["bash", "scripts/run_blueprint_in_docker_worker.sh"]
            assert config["workdir"] == "/mn/job/document_workflow"
            assert config.get("reuse_shared_container") is True
            assert config.get("side_effect") == "network_read"
            assert rendered_config["runner_module"] == "MirrorNeuron.Runner.DockerWorker"
            assert rendered_config["command"] == ["bash", "scripts/run_blueprint_in_docker_worker.sh"]
        else:
            assert config["runner_module"] == "MirrorNeuron.Runner.HostLocal"
            assert config["command"] == ["python3.11", "scripts/run_blueprint.py"]
            assert config["workdir"] == "/sandbox/job/document_workflow"
            assert "docker_worker_image" not in config
            assert "image" not in config
            assert "reuse_shared_container" not in config
            assert rendered_config["runner_module"] == "MirrorNeuron.Runner.HostLocal"
            assert rendered_config["command"] == ["python3.11", "scripts/run_blueprint.py"]

    assert all(
        "mn-skills" not in item.get("source", "")
        for node in nodes
        for item in node["config"].get("upload_paths", [])
    )
    assert "financial_market_researcher" in {step["id"] for step in manifest["workflow"]["steps"]}
    assert "financial_market_researcher_completed" in manifest["contract"]["events"]["types"]
    assert manifest["runtime"]["worker_defaults"]["runner"] == "MirrorNeuron.Runner.HostLocal"
    assert manifest["runtime"]["memory"]["conversation"]["use_model_compression"] is True
    assert manifest["metadata"]["memory_layer"]["conversation"]["use_model_compression"] is True


def test_personal_financial_advisor_watch_mode_stops_after_max_cycle(tmp_path, monkeypatch):
    runner = _load_runner()
    _install_fake_research(monkeypatch, runner)
    docs = tmp_path / "finance-inbox"
    outputs = tmp_path / "exports"
    _write_fixture_folder(docs)

    result = runner.run_blueprint(
        inputs={
            "document_folder": str(docs),
            "output_folder": str(outputs),
            "monitoring": {"enabled": True, "poll_interval_seconds": 1, "max_cycles": 1},
        },
        runs_root=tmp_path,
        run_id="advisor-watch-unit",
    )

    artifact = result["final_artifact"]
    assert artifact["watch_state"]["mode"] == "watch"
    assert artifact["watch_state"]["cycles_completed"] == 1
    assert len(artifact["watch_state"]["processed_files"]) == 4
    assert len(artifact["watch_state"]["new_or_changed_files"]) == 4
    assert (tmp_path / "advisor-watch-unit" / "watch_state.json").exists()

    events = [
        json.loads(line)
        for line in (tmp_path / "advisor-watch-unit" / "events.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert {"watch_cycle_started", "watch_cycle_completed", "financial_market_researcher_completed", "financial_advice_reporter_completed"} <= {
        event["type"] for event in events
    }


def test_personal_financial_advisor_non_research_step_mode_does_not_call_browser(tmp_path, monkeypatch):
    runner = _load_runner()
    docs = tmp_path / "finance-inbox"
    outputs = tmp_path / "exports"
    _write_fixture_folder(docs)

    def forbidden_browser_call(*args, **kwargs):
        raise AssertionError("HostLocal runtime steps must not run browser research")

    monkeypatch.setattr(runner, "financial_market_researcher", forbidden_browser_call)
    monkeypatch.setattr(runner, "research_topic", forbidden_browser_call)
    monkeypatch.setattr(runner, "_load_w3m_browser_skill", forbidden_browser_call)

    inputs = {
        "document_folder": str(docs),
        "output_folder": str(outputs),
        "monitoring": {"enabled": True, "poll_interval_seconds": 1, "max_cycles": 1},
    }
    runner.run_runtime_step(
        "financial_document_reader",
        inputs=inputs,
        runs_root=tmp_path,
        run_id="advisor-step-mode",
    )
    result = runner.run_runtime_step(
        "financial_health_assessor",
        inputs=inputs,
        runs_root=tmp_path,
        run_id="advisor-step-mode",
    )

    assert result["schema"] == "mn.workflow.step_result.v1"
    assert result["workflow_step_id"] == "financial_health_assessor"
    assert result["status"] == "completed"
    assert "final_artifact" not in result
    assert result["outputs"]["risk_register"]

    events = [
        json.loads(line)
        for line in (tmp_path / "advisor-step-mode" / "events.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert "financial_market_researcher_completed" not in {event["type"] for event in events}


def test_personal_financial_advisor_runtime_step_infers_agent_id_without_full_cycle(tmp_path):
    docs = tmp_path / "finance-inbox"
    _write_fixture_folder(docs)
    env = os.environ.copy()
    env["MN_AGENT_ID"] = "financial_folder_watcher"

    result = subprocess.run(
        [
            sys.executable,
            str(RUNNER_PATH),
            "--no-run-store",
            "--run-id",
            "advisor-agent-step",
            "--input-folder",
            str(docs),
            "--watch",
            "--max-cycles",
            "1",
        ],
        cwd=RUNNER_PATH.parents[1],
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    decoded = json.loads(result.stdout)

    assert decoded["schema"] == "mn.workflow.step_result.v1"
    assert decoded["workflow_step_id"] == "financial_folder_watcher"
    assert decoded["outputs"]["watch_state"]["processed_files"]
    assert "final_artifact" not in decoded


def test_personal_financial_advisor_runtime_step_infers_message_destination(tmp_path):
    docs = tmp_path / "finance-inbox"
    _write_fixture_folder(docs)
    message_file = tmp_path / "message.json"
    message_file.write_text(
        json.dumps(
            {
                "to": "financial_folder_watcher",
                "type": "personal_financial_advisor.financial_folder_watcher.ready",
                "payload": {"document_folder": str(docs), "monitoring": {"enabled": True, "max_cycles": 1}},
            }
        ),
        encoding="utf-8",
    )
    env = os.environ.copy()
    env.pop("MN_WORKFLOW_STEP_ID", None)
    env.pop("MN_AGENT_ID", None)
    env["MN_MESSAGE_FILE"] = str(message_file)

    result = subprocess.run(
        [sys.executable, str(RUNNER_PATH), "--no-run-store", "--run-id", "advisor-message-step"],
        cwd=RUNNER_PATH.parents[1],
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    decoded = json.loads(result.stdout)

    assert decoded["schema"] == "mn.workflow.step_result.v1"
    assert decoded["workflow_step_id"] == "financial_folder_watcher"
    assert len(decoded["outputs"]["watch_state"]["processed_files"]) == 4
    assert "final_artifact" not in decoded
