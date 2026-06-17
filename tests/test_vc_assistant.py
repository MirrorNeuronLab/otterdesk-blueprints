from __future__ import annotations

import importlib.util
import json
import threading
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = (
    ROOT
    / "vc_assistant"
    / "payloads"
    / "document_workflow"
    / "scripts"
    / "run_blueprint.py"
)
METHOD_IDS = {
    "berkus_method",
    "scorecard_bill_payne_method",
    "risk_factor_summation_method",
    "venture_capital_method",
    "first_chicago_method",
    "comparables_market_multiple_method",
    "cost_to_duplicate_method",
}


class FakeVCLLM:
    provider = "fake"
    model = "fake-vc-actor"

    def __init__(self) -> None:
        self.calls = 0
        self.fallback_calls = 0
        self.prompts: list[dict[str, str]] = []

    def generate_json(self, *, system_prompt: str, user_prompt: str, fallback: dict):
        self.calls += 1
        self.prompts.append({"system": system_prompt, "user": user_prompt})
        response = dict(fallback)
        response["summary"] = response.get("summary") or "VC actor reviewed the report packet."
        response["provider"] = self.provider
        response["model"] = self.model
        return response


class FailingVCLLM(FakeVCLLM):
    def generate_json(self, *, system_prompt: str, user_prompt: str, fallback: dict):
        self.calls += 1
        self.prompts.append({"system": system_prompt, "user": user_prompt})
        raise RuntimeError("llm endpoint unavailable")


def _load_runner():
    spec = importlib.util.spec_from_file_location("vc_early_runner", RUNNER_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def _write_startup_packets(path: Path) -> None:
    alpha = path / "alpha_ai"
    sparse = path / "sparse_labs"
    alpha.mkdir(parents=True)
    sparse.mkdir(parents=True)
    (alpha / "pitch.txt").write_text(
        "\n".join(
            [
                "Company: Alpha AI",
                "Founder team includes domain experts and engineers.",
                "Market: logistics software with a large buyer segment and active competition.",
                "Product: working MVP, prototype, and enterprise demo.",
                "Traction: $250k ARR, five paying customers, pilot growth, retention evidence.",
                "Strategic partner and distribution channel identified.",
                "Risks: sales cycle dependency and competition.",
            ]
        ),
        encoding="utf-8",
    )
    (sparse / "note.txt").write_text(
        "\n".join(
            [
                "Company: Sparse Labs",
                "Market: early developer tooling idea.",
                "No revenue, cost, prototype, case, or comparable detail yet.",
            ]
        ),
        encoding="utf-8",
    )


def test_manifest_runtime_nodes_carry_default_config_for_service_sandbox():
    manifest = json.loads((ROOT / "vc_assistant" / "manifest.json").read_text(encoding="utf-8"))
    config = json.loads((ROOT / "vc_assistant" / "config" / "default.json").read_text(encoding="utf-8"))
    nodes = [node for node in manifest["agents"]["nodes"] if node["node_id"] != "report_sink"]
    report_sink = next(node for node in manifest["agents"]["nodes"] if node["node_id"] == "report_sink")
    requirements_path = "document_workflow/requirements.txt"
    upload_paths = [
        {"source": "document_workflow", "target": "document_workflow"},
        {"source": "examples/sample_inputs", "target": "vc_assistant/examples/sample_inputs"},
    ]
    assert len(nodes) == 21
    assert report_sink["config"] == {"complete_on_message": True, "terminal_sink": True, "complete_run": True}
    assert config["python_dependencies"]["installer"] == "pip"
    assert config["python_dependencies"]["requirements"] == requirements_path
    assert config["python_dependencies"]["index_url"] == "https://us-central1-python.pkg.dev/mirrorneuron-public-packages/agent-skills/simple/"
    assert config["python_dependencies"]["extra_index_url"] == "https://pypi.org/simple"
    assert config["python_dependencies"]["packages"] == [
        "mirrorneuron-blueprint-support-skill",
        "mirrorneuron-w3m-browser-skill",
        "mirrorneuron-web-browser-skill",
    ]
    assert "examples/sample_inputs/" in manifest["metadata"]["configuration_contract"]["required_files"]
    assert (
        "payloads/document_workflow/vc_assistant/examples/sample_inputs/"
        in manifest["metadata"]["configuration_contract"]["required_files"]
    )
    for node in nodes:
        assert node["config"]["python_environment"] == {"requirements": requirements_path}
        assert node["config"]["upload_paths"] == upload_paths
        environment = node["config"]["environment"]
        assert environment["MN_WORKFLOW_STEP_ID"] == node["node_id"]
        embedded_config = json.loads(environment["MN_BLUEPRINT_CONFIG_JSON"])
        assert embedded_config["inputs"]["payload"]["input_folder"] == "vc_assistant/examples/sample_inputs"
        assert embedded_config["inputs"]["payload"]["output_folder"] == "~/Downloads/vc_assistant"
        assert embedded_config["outputs"]["folder_path"] == "~/Downloads/vc_assistant"
        assert embedded_config["llm"]["model"] == "gemma4:e2b"
        assert embedded_config["research_budget"]["default_actions"] == 100
        assert embedded_config["python_dependencies"] == config["python_dependencies"]
    for template in manifest["metadata"]["agent_templates"]["nodes"]:
        if template["node_id"] == "report_sink":
            assert template["uses"] == "mn-agents.control_join@1.0.0"
            continue
        assert template["with"]["python_environment"] == {"requirements": requirements_path}
        assert template["with"]["upload_paths"] == upload_paths


def test_vc_assistant_runtime_requirements_install_skills_with_pip():
    requirements = (
        ROOT / "vc_assistant" / "payloads" / "document_workflow" / "requirements.txt"
    ).read_text(encoding="utf-8").splitlines()

    assert requirements == [
        "--index-url https://us-central1-python.pkg.dev/mirrorneuron-public-packages/agent-skills/simple/",
        "--extra-index-url https://pypi.org/simple",
        "mirrorneuron-blueprint-support-skill",
        "mirrorneuron-w3m-browser-skill",
        "mirrorneuron-web-browser-skill",
    ]


def test_vc_assistant_runtime_upload_bundle_contains_sample_inputs():
    bundled_sample_root = (
        ROOT
        / "vc_assistant"
        / "payloads"
        / "document_workflow"
        / "vc_assistant"
        / "examples"
        / "sample_inputs"
    )

    assert sorted(path.name for path in bundled_sample_root.iterdir()) == [
        "aurora_ai",
        "boreal_robotics",
        "otterdesk",
    ]
    assert (bundled_sample_root / "aurora_ai" / "pitch_summary.txt").exists()
    assert (bundled_sample_root / "boreal_robotics" / "company_brief.txt").exists()
    assert (bundled_sample_root / "otterdesk" / "pitch_summary.txt").exists()


def test_vc_assistant_runtime_graph_is_linear_and_has_terminal_sink():
    runner = _load_runner()
    manifest = json.loads((ROOT / "vc_assistant" / "manifest.json").read_text(encoding="utf-8"))
    config = json.loads((ROOT / "vc_assistant" / "config" / "default.json").read_text(encoding="utf-8"))
    step_ids = runner.WORKFLOW_STEP_IDS
    handoffs = [f"{source}_to_{target}" for source, target in zip(step_ids, step_ids[1:])]

    assert "type" not in manifest
    assert config["execution_model"]["type"] == "finite_linear_report_factory"
    assert config["execution_model"]["step_count"] == len(step_ids)
    assert config["execution_model"]["terminal_sink"] == "report_sink"
    assert config["agent_handoffs"] == handoffs
    assert manifest["agents"]["edges"] == [
        {"edge_id": edge_id, "from_node": source, "to_node": target, "message_type": f"{source}_completed"}
        for edge_id, source, target in zip(handoffs, step_ids, step_ids[1:])
    ] + [{"edge_id": "batch_index_writer_to_report_sink", "from_node": "batch_index_writer", "to_node": "report_sink", "message_type": "batch_index_writer_completed"}]
    assert manifest["workflow"]["edges"] == [
        {"id": edge_id, "from": source, "to": target, "event": f"{source}_completed", "required": True, "accepts": ["done"]}
        for edge_id, source, target in zip(handoffs, step_ids, step_ids[1:])
    ]
    incoming = {step_id: 0 for step_id in step_ids + ["report_sink"]}
    outgoing = {step_id: 0 for step_id in step_ids + ["report_sink"]}
    for edge in manifest["agents"]["edges"]:
        outgoing[edge["from_node"]] += 1
        incoming[edge["to_node"]] += 1
    assert all(count <= 1 for count in incoming.values())
    assert all(count <= 1 for count in outgoing.values())


def test_vc_agents_are_llm_backed_and_selected_for_actor_reviews():
    runner = _load_runner()
    config = json.loads((ROOT / "vc_assistant" / "config" / "default.json").read_text(encoding="utf-8"))
    agents = config["llm"]["agents"]

    assert len(agents) == 21
    assert set(agents) == set(runner.WORKFLOW_STEP_IDS)
    for actor_id in runner.WORKFLOW_STEP_IDS:
        assert agents[actor_id]["llm_config"] == "primary"
        assert agents[actor_id]["model"] == "gemma4:e2b"

    actor_specs = runner.resolve_actor_specs(config)
    actor_ids = [actor_id for actor_id in runner.WORKFLOW_STEP_IDS if actor_id in actor_specs]
    assert actor_ids == runner.WORKFLOW_STEP_IDS


def test_vc_knowledge_excludes_stale_non_vc_domain_terms():
    runner = _load_runner()
    playbook = (ROOT / "vc_assistant" / "knowledge" / "startup_research_playbook.md").read_text(encoding="utf-8")
    payload_playbook = (ROOT / "vc_assistant" / "payloads" / "document_workflow" / "knowledge" / "startup_research_playbook.md").read_text(encoding="utf-8")
    knowledge = runner.load_vc_knowledge(ROOT / "vc_assistant")
    serialized = json.dumps(knowledge).lower()

    assert payload_playbook == playbook
    assert "Berkus Method" in playbook
    assert "Scorecard / Bill Payne Method" in playbook
    assert "VC Method" in playbook
    for stale_term in ("camera", "video", "surveillance", "footage"):
        assert stale_term not in playbook.lower()
        assert stale_term not in serialized


def test_vc_early_heuristic_filtering_writes_score_only_company_reports(tmp_path):
    runner = _load_runner()
    docs = tmp_path / "startup-docs"
    outputs = tmp_path / "reports"
    _write_startup_packets(docs)
    fake_llm = FakeVCLLM()

    result = runner.run_blueprint(
        inputs={
            "document_folder": str(docs),
            "output_folder": str(outputs),
            "monitoring": {"enabled": True, "poll_interval_seconds": 1, "max_cycles": 1},
        },
        config={"llm": {"mode": "fake"}},
        runs_root=tmp_path,
        run_id="vc-unit",
        llm_client=fake_llm,
    )

    artifact = result["final_artifact"]
    assert result["blueprint_id"] == "vc_assistant"
    assert artifact["type"] == "vc_early_heuristic_analysis_reports"
    assert artifact["report_only"] is True
    assert len(artifact["company_reports"]) == 2
    assert {report["company_slug"] for report in artifact["company_reports"]} == {"alpha-ai", "sparse-labs"}
    assert [report["company_slug"] for report in artifact["company_reports"]] == ["alpha-ai", "sparse-labs"]

    for report in artifact["company_reports"]:
        company_dir = outputs / report["company_slug"]
        assert company_dir.exists()
        assert {
            "analysis.json",
            "analysis.md",
            "method_scores.json",
            "research_sources.json",
            "sources.json",
            "evidence.json",
            "warnings.json",
        } <= {path.name for path in company_dir.iterdir()}
        sources = json.loads((company_dir / "research_sources.json").read_text(encoding="utf-8"))
        assert any(source["skill"] == "w3m_browser_skill" for source in sources)
        assert any("crunchbase.com" in source["url"] or "Crunchbase" in source["query"] for source in sources)
        assert any(source["verification_target"] in {"company_identity_researcher", "crunchbase", "search_results"} for source in sources)
        analysis = json.loads((company_dir / "analysis.json").read_text(encoding="utf-8"))
        method_scores = json.loads((company_dir / "method_scores.json").read_text(encoding="utf-8"))
        assert set(analysis["methods"]) == METHOD_IDS
        assert set(method_scores) == METHOD_IDS
        assert analysis["method_count"] == 7
        assert analysis["evidence_summary"]["composite_score_evidence"]["status"] in {"scored", "insufficient_evidence"}
        assert "result_evidence" in analysis
        for method in analysis["methods"].values():
            assert {"score", "inputs_used", "formula_or_weighting", "assumptions", "source_refs", "evidence_refs", "evidence_summary", "missing_evidence", "warnings"} <= set(method)
            assert method["status"] in {"scored", "insufficient_evidence"}
            assert method["evidence_refs"] or method["missing_evidence"] or method["status"] == "scored"
        markdown = (company_dir / "analysis.md").read_text(encoding="utf-8")
        assert "score-only early screening report" in markdown
        assert "Result Evidence" in markdown
        assert "- Why:" in markdown
        assert "pre-revenue value proxy based on risk reduction" in markdown
        assert "Assumptions:" in markdown

    sparse = json.loads((outputs / "sparse-labs" / "analysis.json").read_text(encoding="utf-8"))
    assert "insufficient_evidence" in {
        method["status"]
        for method in sparse["methods"].values()
    }
    assert (outputs / "company_index.json").exists()
    assert (outputs / "company_index.md").exists()
    assert (outputs / "company_work_queue.json").exists()
    assert (outputs / "research_coverage.json").exists()
    assert (outputs / "method_coverage.json").exists()
    assert (outputs / "run_summary.md").exists()
    assert (outputs / "final_artifact.json").exists()
    assert (outputs / "action_ledger.json").exists()
    assert sorted(path.name for path in (outputs / "company_fact_tables").iterdir()) == ["alpha-ai.json", "sparse-labs.json"]
    assert sorted(path.name for path in (outputs / "research_ledgers").iterdir()) == ["alpha-ai.json", "sparse-labs.json"]
    assert sorted(path.name for path in (outputs / "method_scores").iterdir()) == ["alpha-ai.json", "sparse-labs.json"]
    assert sorted(path.name for path in (outputs / "audit_findings").iterdir()) == ["alpha-ai.json", "sparse-labs.json"]

    serialized = json.dumps(artifact).lower()
    assert "filter_label" not in serialized
    assert "screening_decision" not in serialized
    assert '"pass"' not in serialized
    assert '"watch"' not in serialized
    assert '"reject"' not in serialized

    run_artifact = json.loads((tmp_path / "vc-unit" / "final_artifact.json").read_text(encoding="utf-8"))
    assert run_artifact["method_ids"] == list(runner.METHOD_IDS)
    assert set(run_artifact["workflow_step_ids"]) == set(runner.WORKFLOW_STEP_IDS)
    assert {item["status"] for item in run_artifact["company_work_queue"]} == {"new_or_changed"}
    assert set(run_artifact["actor_findings"]) == set(runner.WORKFLOW_STEP_IDS)
    assert run_artifact["llm_usage"]["provider"] == "fake"
    assert run_artifact["llm_usage"]["model"] == "fake-vc-actor"
    assert run_artifact["llm_usage"]["calls"] == len(runner.WORKFLOW_STEP_IDS)
    assert run_artifact["action_ledger"]["budget"] == 100
    assert run_artifact["action_ledger"]["used"] >= len(runner.WORKFLOW_STEP_IDS)
    assert any(action["action_type"] == "financial_tool" for action in run_artifact["action_ledger"]["actions"])
    assert json.loads((outputs / "final_artifact.json").read_text(encoding="utf-8"))["action_ledger"]["budget"] == 100
    assert json.loads((outputs / "action_ledger.json").read_text(encoding="utf-8"))["budget"] == 100
    assert any(item["kind"] == "final_artifact_json" for item in run_artifact["output_files"])
    assert run_artifact["active_knowledge"]["path"] == "knowledge/startup_research_playbook.md"
    assert run_artifact["active_knowledge"]["sha256"]
    assert set(run_artifact["active_knowledge"]["method_memory_hooks"]) == METHOD_IDS
    assert fake_llm.calls == len(runner.WORKFLOW_STEP_IDS)
    prompt_payload = fake_llm.prompts[0]["user"]
    assert "VC Startup Research And Method Playbook" in prompt_payload
    for expected in (
        "Berkus Method",
        "Scorecard / Bill Payne Method",
        "Risk Factor Summation Method",
        "VC Method",
        "First Chicago Method",
        "Comparable Transactions / Market Multiples",
        "Cost-to-Duplicate Method",
        "method_correctness",
        "evidence_grounding",
        "financial_reasoning_quality",
    ):
        assert expected in prompt_payload
    for stale_term in ("camera", "video", "surveillance", "footage"):
        assert stale_term not in prompt_payload.lower()
    assert (tmp_path / "vc-unit" / "action_ledger.json").exists()

    repeat = runner.run_blueprint(
        inputs={
            "document_folder": str(docs),
            "output_folder": str(outputs),
            "monitoring": {"enabled": True, "poll_interval_seconds": 1, "max_cycles": 1},
        },
        config={"llm": {"mode": "fake"}},
        runs_root=tmp_path,
        run_id="vc-repeat",
        llm_client=FakeVCLLM(),
    )
    assert {item["status"] for item in repeat["final_artifact"]["company_work_queue"]} == {"unchanged_skipped"}
    assert repeat["final_artifact"]["monitor_state"]["processed_company_count"] == 0
    assert repeat["final_artifact"]["monitor_state"]["skipped_company_count"] == 2
    assert {report["processing_status"] for report in repeat["final_artifact"]["company_reports"]} == {"unchanged_skipped"}


def test_actor_review_failure_does_not_fail_report_outputs(tmp_path):
    runner = _load_runner()
    docs = tmp_path / "startup-docs"
    outputs = tmp_path / "reports"
    _write_startup_packets(docs)
    failing_llm = FailingVCLLM()

    result = runner.run_blueprint(
        inputs={
            "document_folder": str(docs),
            "output_folder": str(outputs),
            "monitoring": {"enabled": True, "poll_interval_seconds": 1, "max_cycles": 1},
        },
        config={"llm": {"mode": "fake"}},
        runs_root=tmp_path,
        run_id="vc-llm-fails",
        llm_client=failing_llm,
    )

    artifact = result["final_artifact"]
    assert result["status"] == "completed"
    assert (outputs / "alpha-ai" / "analysis.md").exists()
    assert (outputs / "company_index.json").exists()
    assert artifact["actor_review_warnings"][0]["status"] == "actor_review_unavailable"
    assert artifact["actor_review_warnings"][0]["affected_actor_count"] == len(runner.WORKFLOW_STEP_IDS)
    assert set(artifact["actor_findings"]) == set(runner.WORKFLOW_STEP_IDS)
    assert failing_llm.calls == len(runner.WORKFLOW_STEP_IDS)


def test_runtime_step_entrypoint_runs_report_factory_once(tmp_path):
    runner = _load_runner()
    docs = tmp_path / "startup-docs"
    outputs = tmp_path / "reports"
    _write_startup_packets(docs)

    entry_result = runner.run_runtime_step(
        "startup_folder_watcher",
        inputs={
            "document_folder": str(docs),
            "output_folder": str(outputs),
            "monitoring": {"enabled": True, "poll_interval_seconds": 1, "max_cycles": 1},
        },
        config={"llm": {"mode": "fake"}},
        runs_root=tmp_path,
        run_id="vc-runtime-entry",
        llm_client=FakeVCLLM(),
    )

    assert entry_result["runtime_step_mode"] == "report_factory_entrypoint"
    assert (outputs / "company_index.json").exists()
    assert (outputs / "alpha-ai" / "analysis.json").exists()
    assert (outputs / "sparse-labs" / "analysis.json").exists()

    ack_result = runner.run_runtime_step(
        "company_packet_grouper",
        inputs={
            "document_folder": str(docs),
            "output_folder": str(outputs),
        },
        config={"llm": {"mode": "fake"}},
        runs_root=tmp_path,
        run_id="vc-runtime-ack",
        llm_client=FakeVCLLM(),
    )

    assert ack_result["runtime_step_mode"] == "acknowledged_after_report_factory_entrypoint"
    assert "final_artifact" not in ack_result
    assert (tmp_path / "vc-runtime-ack" / "company_packet_grouper_result.json").exists()


def test_runtime_step_entrypoint_honors_mirror_neuron_run_environment(tmp_path, monkeypatch):
    runner = _load_runner()
    docs = tmp_path / "startup-docs"
    outputs = tmp_path / "reports"
    runtime_runs = tmp_path / "mn-runs"
    _write_startup_packets(docs)
    monkeypatch.setenv("MN_RUN_ID", "vc-runtime-env")
    monkeypatch.setenv("MN_RUNS_ROOT", str(runtime_runs))

    result = runner.run_runtime_step(
        "startup_folder_watcher",
        inputs={
            "document_folder": str(docs),
            "output_folder": str(outputs),
            "monitoring": {"enabled": True, "poll_interval_seconds": 1, "max_cycles": 1},
        },
        config={"llm": {"mode": "fake"}},
        llm_client=FakeVCLLM(),
    )

    run_dir = runtime_runs / "vc-runtime-env"
    assert result["run_id"] == "vc-runtime-env"
    assert (run_dir / "result.json").exists()
    assert (run_dir / "final_artifact.json").exists()
    assert (run_dir / "action_ledger.json").exists()


def test_tilde_output_folder_can_use_runtime_output_home(tmp_path, monkeypatch):
    runner = _load_runner()
    output_home = tmp_path / "host-home"
    monkeypatch.setenv("MN_OUTPUT_HOME", str(output_home))

    assert runner.expand_runtime_path("~/Downloads/vc_assistant") == output_home / "Downloads" / "vc_assistant"


def test_tilde_output_folder_derives_user_home_from_mirror_neuron_runs_root(monkeypatch):
    runner = _load_runner()
    user_home = Path("/Users/vc-test-user")
    for env_name in (
        "MN_OUTPUT_HOME",
        "MN_USER_HOME",
        "OTTERDESK_USER_HOME",
        "MN_RUN_DIR",
        "MN_RUNS_ROOT",
        "MN_HOME",
        "OTTERDESK_RUN_DIR",
        "OTTERDESK_RUNS_ROOT",
    ):
        monkeypatch.delenv(env_name, raising=False)
    monkeypatch.setenv("HOME", "/root")
    monkeypatch.setenv("MN_RUNS_ROOT", str(user_home / ".mn" / "runs"))

    assert runner.expand_runtime_path("~/Downloads/vc_assistant") == user_home / "Downloads" / "vc_assistant"


def test_changed_company_packets_process_in_parallel_with_stable_output_order(tmp_path):
    runner = _load_runner()
    docs = tmp_path / "startup-docs"
    outputs = tmp_path / "reports"
    _write_startup_packets(docs)
    started: set[str] = set()
    lock = threading.Lock()
    two_started = threading.Event()
    original_research = runner.research_company_by_stage

    def fake_research(company, config, run_dir=None):
        with lock:
            started.add(company)
            if len(started) >= 2:
                two_started.set()
        assert two_started.wait(1.0), "changed company packets did not overlap"
        time.sleep(0.02)
        slug = runner.slugify(company)
        return {
            stage: [
                {
                    "company": company,
                    "query": f"{company} {stage}",
                    "url": f"https://example.com/{slug}/{stage}",
                    "title": stage,
                    "snippet": "founder market customer revenue product prototype competitor patent funding investor",
                    "status": "ok",
                    "skill": "w3m_browser_skill",
                    "verification_target": stage,
                    "warning": "",
                    "retrieved_at": runner.utc_now_iso(),
                }
            ]
            for stage in runner.RESEARCH_STAGE_IDS
        }

    runner.research_company_by_stage = fake_research
    try:
        result = runner.run_blueprint(
            inputs={
                "document_folder": str(docs),
                "output_folder": str(outputs),
                "monitoring": {"enabled": True, "poll_interval_seconds": 1, "max_cycles": 1},
            },
            config={"llm": {"mode": "fake"}, "execution": {"max_company_workers": 2}, "scoring": {"max_workers": 7}},
            runs_root=tmp_path,
            run_id="vc-parallel",
            llm_client=FakeVCLLM(),
        )
    finally:
        runner.research_company_by_stage = original_research

    artifact = result["final_artifact"]
    assert len(started) == 2
    assert artifact["parallel_execution"]["max_company_workers"] == 2
    assert artifact["parallel_execution"]["max_scoring_workers"] == 7
    assert artifact["parallel_execution"]["company_processing_order"] == ["alpha-ai", "sparse-labs"]
    assert [report["company_slug"] for report in artifact["company_reports"]] == ["alpha-ai", "sparse-labs"]


def test_research_ledgers_emit_stage_specific_records_without_browser_network(tmp_path):
    runner = _load_runner()
    original_w3m = runner._append_w3m_research
    original_target = runner._append_target_url_research

    def fake_w3m(sources, *, company, plan, internet, run_dir, verification_target="search_result_or_public_source"):
        sources.append(
            {
                "company": company,
                "query": plan["queries"][0],
                "url": f"https://example.com/{runner.slugify(company)}/{verification_target}",
                "title": verification_target,
                "snippet": f"public {verification_target} evidence",
                "status": "ok",
                "skill": "w3m_browser_skill",
                "verification_target": verification_target,
                "warning": "",
                "retrieved_at": runner.utc_now_iso(),
            }
        )

    def fake_target(sources, *, company, plan, internet, run_dir):
        sources.append(
            {
                "company": company,
                "query": plan["queries"][0],
                "url": f"https://www.crunchbase.com/organization/{runner.slugify(company)}",
                "title": "Crunchbase profile",
                "snippet": "public profile source",
                "status": "ok",
                "skill": "w3m_browser_skill",
                "verification_target": "crunchbase",
                "warning": "",
                "retrieved_at": runner.utc_now_iso(),
            }
        )

    runner._append_w3m_research = fake_w3m
    runner._append_target_url_research = fake_target
    try:
        ledger = runner.research_company_by_stage(
            "Example AI",
            {
                "internet_research": {
                    "enabled": True,
                    "max_stage_workers": 5,
                    "default_source_urls": ["https://example.com/reference"],
                    "rendered_browser": {"enabled": False},
                }
            },
            run_dir=tmp_path,
        )
    finally:
        runner._append_w3m_research = original_w3m
        runner._append_target_url_research = original_target

    assert set(ledger) == set(runner.RESEARCH_STAGE_IDS)
    for stage in runner.RESEARCH_STAGE_IDS:
        assert any(source["verification_target"] == stage for source in ledger[stage])
    assert any("funding" in source["query"].lower() for source in ledger["funding_researcher"])
    assert any("competitors" in source["query"].lower() for source in ledger["market_comp_researcher"])
    assert any("customers" in source["query"].lower() for source in ledger["traction_verifier"])
    assert any(source["verification_target"] == "crunchbase" for source in ledger["company_identity_researcher"])
    assert any(source["status"] == "disabled" for source in ledger["rendered_page_researcher"])


def test_scorecard_and_comparables_ignore_non_substantive_defaults():
    runner = _load_runner()
    records = [
        {
            "path": "empty.txt",
            "filename": "empty.txt",
            "company_name": "Empty Co",
            "sha256": "0",
            "suffix": ".txt",
            "text_preview": "Company: Empty Co.",
            "character_count": 18,
            "extraction_method": "embedded_text",
            "ocr_required": False,
            "warnings": [],
        }
    ]
    ledger = {
        stage: [
            {
                "company": "Empty Co",
                "query": f"Empty Co {stage}",
                "url": "research_plan",
                "title": "planned",
                "snippet": "planned public research",
                "status": "planned",
                "skill": "research_planner",
                "verification_target": stage,
                "warning": "",
                "retrieved_at": runner.utc_now_iso(),
            },
            {
                "company": "Empty Co",
                "query": f"Empty Co {stage}",
                "url": "https://example.com/reference",
                "title": "reference",
                "snippet": "market competitor revenue configured reference text",
                "status": "configured_reference",
                "skill": "w3m_browser_skill",
                "verification_target": stage,
                "warning": "",
                "retrieved_at": runner.utc_now_iso(),
            },
        ]
        for stage in runner.RESEARCH_STAGE_IDS
    }

    analysis = runner.build_company_analysis("Empty Co", records, ledger, scoring_workers=7)
    assert analysis["methods"]["scorecard_bill_payne_method"]["status"] == "insufficient_evidence"
    assert analysis["methods"]["scorecard_bill_payne_method"]["score"] is None
    assert analysis["methods"]["comparables_market_multiple_method"]["status"] == "insufficient_evidence"
    assert analysis["methods"]["comparables_market_multiple_method"]["score"] is None
    assert analysis["fact_table"]["raw_counts"]["substantive_research_source_count"] == 0


def test_action_budget_charges_browser_rendered_financial_tool_and_llm(monkeypatch, tmp_path):
    runner = _load_runner()
    budget = runner.ActionBudget(10)

    class DummyConfig:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    monkeypatch.setattr(runner, "_load_w3m_browser_skill", lambda: None)
    monkeypatch.setattr(runner, "W3mBrowserConfig", DummyConfig)
    monkeypatch.setattr(
        runner,
        "research_topic",
        lambda query, browser_config, max_sources, observer=None: {
            "sources": [{"url": "https://example.com/source", "title": "Source", "snippet": "market revenue comparable"}],
            "warnings": [],
        },
    )
    monkeypatch.setattr(
        runner,
        "browse_url",
        lambda url, browser_config, observer=None: {"status": "ok", "url": url, "title": "Profile", "snippet": "funding customer traction"},
    )
    monkeypatch.setattr(runner, "_load_web_browser_skill", lambda: None)
    monkeypatch.setattr(runner, "WebBrowserConfig", DummyConfig)
    monkeypatch.setattr(
        runner,
        "scrape_page",
        lambda url, browser_config: {"status": "ok", "final_url": url, "title": "Rendered", "text": "rendered startup profile", "warnings": []},
    )

    sources = []
    plan = {"queries": ["Example AI funding"], "target_urls": ["https://example.com/profile"], "company_slug": "example-ai"}
    runner._append_w3m_research(sources, company="Example AI", plan=plan, internet={"max_sources_per_company": 1}, run_dir=tmp_path, action_budget=budget)
    runner._append_target_url_research(sources, company="Example AI", plan=plan, internet={"max_target_urls_per_company": 1}, run_dir=tmp_path, action_budget=budget)
    runner._append_rendered_browser_research(
        sources,
        company="Example AI",
        plan=plan,
        internet={"rendered_browser": {"enabled": True, "max_pages_per_company": 1}},
        action_budget=budget,
    )
    runner.append_financial_tool_research(
        "Example AI",
        [{"path": "pitch.txt", "filename": "pitch.txt", "text_preview": "Revenue $100k. Example.com comparable.", "character_count": 35}],
        {"market_comp_researcher": sources},
        action_budget=budget,
    )
    llm = runner.BudgetedLLM(FakeVCLLM(), budget)
    llm.generate_json(system_prompt="actor", user_prompt="{}", fallback={"actor_id": "actor", "summary": "", "findings": [], "risks": []})

    ledger = budget.summary()
    assert ledger["used"] == 5
    assert [action["action_type"] for action in ledger["actions"]] == [
        "browser_search",
        "browser_page",
        "rendered_browser_page",
        "financial_tool",
        "llm_call",
    ]


def test_budget_exhaustion_finishes_with_warnings_and_no_extra_llm_calls(tmp_path):
    runner = _load_runner()
    docs = tmp_path / "startup-docs"
    outputs = tmp_path / "reports"
    _write_startup_packets(docs)
    fake_llm = FakeVCLLM()

    result = runner.run_blueprint(
        inputs={
            "document_folder": str(docs),
            "output_folder": str(outputs),
            "monitoring": {"enabled": True, "poll_interval_seconds": 1, "max_cycles": 1},
        },
        config={"llm": {"mode": "fake"}, "research_budget": {"default_actions": 1}},
        runs_root=tmp_path,
        run_id="vc-budget-exhausted",
        llm_client=fake_llm,
    )

    artifact = result["final_artifact"]
    assert result["status"] == "completed"
    assert artifact["action_ledger"]["budget"] == 1
    assert artifact["action_ledger"]["used"] == 1
    assert artifact["action_ledger"]["exhausted"] is True
    assert any(action["status"] == "budget_exhausted" for action in artifact["action_ledger"]["actions"])
    assert any(warning["status"] == "budget_exhausted" for warning in artifact["research_warnings"])
    assert fake_llm.calls == 0
