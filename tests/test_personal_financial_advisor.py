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
ACTOR_IDS = [
    "financial_folder_watcher",
    "financial_document_reader",
    "financial_activity_classifier",
    "financial_health_assessor",
    "financial_market_researcher",
    "financial_advice_reporter",
]


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


class FakeActorLLM:
    provider = "fake"
    model = "fake-default-llm"

    def __init__(self) -> None:
        self.calls = 0
        self.fallback_calls = 0
        self.prompts: list[dict[str, str]] = []

    def generate_json(self, *, system_prompt: str, user_prompt: str, fallback: dict):
        self.calls += 1
        self.prompts.append({"system": system_prompt, "user": user_prompt})
        response = dict(fallback)
        if "search_queries" in response:
            response["search_queries"] = ["official consumer guidance avoiding bank fees"]
            response["research_focus"] = ["fees", "cash_flow"]
            response["rationale"] = "Search public consumer-finance guidance from generic risk categories."
        if "selected_urls" in response:
            response["selected_urls"] = response["selected_urls"][:1]
        if "findings" in response:
            response["summary"] = "Consumer guidance: review fees, due dates, and household budget tradeoffs before acting."
            response["findings"] = [
                {
                    "topic": "fees",
                    "finding": "Review bank fees and due dates before changing household plans.",
                    "source_url": "https://consumer.gov/managing-your-money",
                }
            ]
        if "advisor_message" in response:
            response["advisor_message"] = response["advisor_message"] or "Review the source-grounded report before taking action."
        response["provider"] = self.provider
        response["model"] = self.model
        return response


def _install_fake_actor_runtime(monkeypatch, runner) -> tuple[FakeActorLLM, list[str]]:
    class FakeW3mBrowserConfig:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    browse_calls: list[str] = []

    def fake_build_search_url(query, config=None):
        return f"https://duckduckgo.com/html/?q={str(query).replace(' ', '+')}"

    def fake_browse_url(url, config=None, observer=None):
        browse_calls.append(url)
        if observer:
            observer(
                "tool_call_started",
                {
                    "category": "tool",
                    "tool_name": "w3m",
                    "target": url,
                    "status": "started",
                    "message": f"Browsing {url}",
                },
            )
        if "duckduckgo.com" in url:
            result = {
                "status": "ok",
                "url": url,
                "title": "DuckDuckGo",
                "text": "\n".join(
                    [
                        "Search results",
                        "https://consumer.gov/managing-your-money",
                        "https://www.consumerfinance.gov/consumer-tools/bank-accounts/",
                    ]
                ),
                "snippet": "Public consumer finance search results.",
            }
        else:
            result = {
                "status": "ok",
                "url": url,
                "title": "Managing Your Money",
                "text": "Managing Your Money\nReview bills, fees, and spending before making financial decisions.",
                "snippet": "Review bills, fees, and spending before making financial decisions.",
            }
        if observer:
            observer(
                "tool_call_completed",
                {
                    "category": "tool",
                    "tool_name": "w3m",
                    "target": url,
                    "status": "completed",
                    "message": f"Browsed {url}",
                    "result_summary": result["snippet"],
                    "details": {"title": result["title"]},
                },
            )
        return result

    monkeypatch.setattr(runner, "W3mBrowserConfig", FakeW3mBrowserConfig)
    monkeypatch.setattr(runner, "build_search_url", fake_build_search_url)
    monkeypatch.setattr(runner, "browse_url", fake_browse_url)
    monkeypatch.setattr(runner, "research_topic", lambda *args, **kwargs: {})
    monkeypatch.setattr(runner, "_load_w3m_browser_skill", lambda: None)
    monkeypatch.setattr(
        runner,
        "compile_research_context",
        lambda *args, **kwargs: {"enabled": True, "use_model_compression": True, "compressed": True},
    )
    return FakeActorLLM(), browse_calls


def test_personal_financial_advisor_writes_review_report_outputs(tmp_path, monkeypatch):
    runner = _load_runner()
    fake_llm, browse_calls = _install_fake_actor_runtime(monkeypatch, runner)
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
        llm_client=fake_llm,
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
    assert artifact["research_plan"]["search_queries"]
    assert artifact["research_findings"]
    assert artifact["research_sources"]
    assert artifact["research_warnings"] == []
    assert set(artifact["actor_findings"]) == set(ACTOR_IDS)
    assert artifact["llm_usage"]["calls"] >= len(ACTOR_IDS)
    assert any("duckduckgo.com" in url for url in browse_calls)
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
    assert "## Actor Findings" in markdown_text
    assert "### Research Findings" in markdown_text
    assert "Managing Your Money" in markdown_text
    assert "review-only report" in markdown_text

    run_artifact = json.loads((tmp_path / "advisor-unit" / "final_artifact.json").read_text(encoding="utf-8"))
    assert run_artifact["type"] == "personal_financial_advisor_report"
    run_events = [
        json.loads(line)
        for line in (tmp_path / "advisor-unit" / "events.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    tool_events = [event for event in run_events if event["type"] in {"tool_call_started", "tool_call_completed"}]
    assert tool_events
    assert any("duckduckgo.com" in (event["payload"].get("target") or "") for event in tool_events)
    assert any(event["payload"].get("target") == "https://consumer.gov/managing-your-money" for event in tool_events)
    assert all(event["payload"].get("category") == "tool" for event in tool_events)
    serialized_events = json.dumps(run_events)
    for private_text in ["ACME", "Fresh Market", "Community Bank", "$5,200.00", "$145.22"]:
        assert private_text not in serialized_events


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
    assert {step["id"] for step in manifest["workflow"]["steps"]} == set(ACTOR_IDS)
    assert set(node_by_id) == set(ACTOR_IDS)
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
            build_context_uploads = config["build_context_upload_paths"]
            assert {item["source"] for item in build_context_uploads} == {
                "blueprint_support_skill",
                "llm_ocr_skill",
                "w3m_browser_skill",
            }
            assert all(item["base"] == "skills_root" for item in build_context_uploads)
            assert all(
                item["target"].startswith("document_workflow/docker_worker/build_context/")
                for item in build_context_uploads
            )
            assert rendered_config["runner_module"] == "MirrorNeuron.Runner.DockerWorker"
            assert rendered_config["command"] == ["bash", "scripts/run_blueprint_in_docker_worker.sh"]
            assert rendered_config["build_context_upload_paths"] == build_context_uploads
        else:
            assert config["runner_module"] == "MirrorNeuron.Runner.HostLocal"
            assert config["command"] == ["python3.11", "scripts/run_blueprint.py"]
            assert config["workdir"] == "/sandbox/job/document_workflow"
            assert "docker_worker_image" not in config
            assert "image" not in config
            assert "reuse_shared_container" not in config
            assert "build_context_upload_paths" not in config
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
    llm_agents = manifest["metadata"]["llm"]["agents"]
    assert set(llm_agents) == set(ACTOR_IDS)
    assert all(config["model"] == "default" for config in llm_agents.values())


def test_personal_financial_advisor_watch_mode_stops_after_max_cycle(tmp_path, monkeypatch):
    runner = _load_runner()
    fake_llm, _browse_calls = _install_fake_actor_runtime(monkeypatch, runner)
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
        llm_client=fake_llm,
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
        llm_client=FakeActorLLM(),
    )
    result = runner.run_runtime_step(
        "financial_health_assessor",
        inputs=inputs,
        runs_root=tmp_path,
        run_id="advisor-step-mode",
        llm_client=FakeActorLLM(),
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


def test_financial_market_researcher_uses_llm_guided_w3m_without_private_queries(tmp_path, monkeypatch):
    runner = _load_runner()
    fake_llm, browse_calls = _install_fake_actor_runtime(monkeypatch, runner)
    docs = tmp_path / "finance-inbox"
    outputs = tmp_path / "exports"
    _write_fixture_folder(docs)
    inputs = {
        "document_folder": str(docs),
        "output_folder": str(outputs),
        "monitoring": {"enabled": True, "poll_interval_seconds": 1, "max_cycles": 1},
    }

    runner.run_runtime_step("financial_document_reader", inputs=inputs, runs_root=tmp_path, run_id="advisor-research-step", llm_client=fake_llm)
    runner.run_runtime_step("financial_activity_classifier", inputs=inputs, runs_root=tmp_path, run_id="advisor-research-step", llm_client=fake_llm)
    runner.run_runtime_step("financial_health_assessor", inputs=inputs, runs_root=tmp_path, run_id="advisor-research-step", llm_client=fake_llm)
    result = runner.run_runtime_step("financial_market_researcher", inputs=inputs, runs_root=tmp_path, run_id="advisor-research-step", llm_client=fake_llm)

    assert result["schema"] == "mn.workflow.step_result.v1"
    assert result["workflow_step_id"] == "financial_market_researcher"
    assert result["outputs"]["research_plan"]["search_queries"]
    assert result["outputs"]["research_findings"]
    assert result["outputs"]["research_sources"]
    assert any("duckduckgo.com" in url for url in browse_calls)
    assert any(url == "https://consumer.gov/managing-your-money" for url in browse_calls)

    research_prompts = [
        prompt["user"]
        for prompt in fake_llm.prompts
        if "financial_market_researcher" in prompt["user"]
    ]
    assert research_prompts
    joined = "\n".join(research_prompts)
    for private_text in ["ACME", "Fresh Market", "Community Bank", "$5,200.00", "$145.22"]:
        assert private_text not in joined
    events = [
        json.loads(line)
        for line in (tmp_path / "advisor-research-step" / "events.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert any(event["type"] == "tool_call_completed" and event["payload"].get("target") == "https://consumer.gov/managing-your-money" for event in events)


def test_personal_financial_advisor_runtime_step_infers_agent_id_without_full_cycle(tmp_path):
    docs = tmp_path / "finance-inbox"
    _write_fixture_folder(docs)
    env = os.environ.copy()
    env["MN_AGENT_ID"] = "financial_folder_watcher"
    env["MN_BLUEPRINT_LLM_MODE"] = "fake"

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
    env["MN_BLUEPRINT_LLM_MODE"] = "fake"

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
