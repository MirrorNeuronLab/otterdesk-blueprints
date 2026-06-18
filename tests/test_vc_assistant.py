from __future__ import annotations

import importlib.util
import json
import threading
import time
from pathlib import Path

import pytest


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


class ToolCallingVCLLM(FakeVCLLM):
    def __init__(self, decisions: dict[str, list[dict]]) -> None:
        super().__init__()
        self.decisions = {key: list(value) for key, value in decisions.items()}

    def generate_json(self, *, system_prompt: str, user_prompt: str, fallback: dict):
        self.calls += 1
        self.prompts.append({"system": system_prompt, "user": user_prompt})
        keys = [system_prompt, str(fallback.get("actor_id") or "")]
        try:
            prompt = json.loads(user_prompt)
        except json.JSONDecodeError:
            prompt = {}
        if isinstance(prompt, dict):
            keys.append(str(prompt.get("agent_id") or ""))
        queue = []
        for key in keys:
            queue = self.decisions.get(key) or []
            if queue:
                break
        if queue:
            return queue.pop(0)
        return {"thought_summary": "done", "tool_calls": [{"tool": "finish", "reason": "done"}], "stop_reason": "done", "evidence_gaps": []}


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


def test_manifest_runtime_nodes_carry_default_config_for_batch_sandbox():
    manifest = json.loads((ROOT / "vc_assistant" / "manifest.json").read_text(encoding="utf-8"))
    config = json.loads((ROOT / "vc_assistant" / "config" / "default.json").read_text(encoding="utf-8"))
    nodes = [node for node in manifest["agents"]["nodes"] if node["node_id"] != "report_sink"]
    report_sink = next(node for node in manifest["agents"]["nodes"] if node["node_id"] == "report_sink")
    requirements_path = "document_workflow/requirements.txt"
    upload_paths = [
        {"source": "document_workflow", "target": "document_workflow"},
        {"source": "examples/sample_inputs", "target": "vc_assistant/examples/sample_inputs"},
        {"source": "knowledge", "target": "knowledge"},
    ]
    build_context_upload_paths = [
        {
            "base": "skills_root",
            "source": "blueprint_support_skill",
            "target": "document_workflow/docker_worker/build_context/blueprint_support_skill",
        },
        {
            "base": "skills_root",
            "source": "llm_ocr_skill",
            "target": "document_workflow/docker_worker/build_context/llm_ocr_skill",
        },
        {
            "base": "skills_root",
            "source": "rag_skill",
            "target": "document_workflow/docker_worker/build_context/rag_skill",
        },
        {
            "base": "skills_root",
            "source": "w3m_browser_skill",
            "target": "document_workflow/docker_worker/build_context/w3m_browser_skill",
        },
        {
            "base": "skills_root",
            "source": "web_browser_skill",
            "target": "document_workflow/docker_worker/build_context/web_browser_skill",
        },
    ]
    assert len(nodes) == 21
    assert report_sink["config"] == {"complete_on_message": True, "terminal_sink": True, "complete_run": True}
    assert config["python_dependencies"]["installer"] == "pip"
    assert config["python_dependencies"]["requirements"] == requirements_path
    assert config["python_dependencies"]["index_url"] == "https://us-central1-python.pkg.dev/mirrorneuron-public-packages/agent-skills/simple/"
    assert config["python_dependencies"]["extra_index_url"] == "https://pypi.org/simple"
    assert config["python_dependencies"]["packages"] == [
        "mirrorneuron-blueprint-support-skill",
        "mirrorneuron-membrane-python-sdk",
        "mirrorneuron-llm-ocr-skill",
        "mirrorneuron-rag-skill",
        "mirrorneuron-w3m-browser-skill",
        "mirrorneuron-web-browser-skill",
    ]
    assert config["input_skills"]["llm_ocr"] == {
        "skill": "llm_ocr_skill",
        "package": "mirrorneuron-llm-ocr-skill",
        "connector": "docker_model_runner",
        "purpose": "shared local LightOnOCR-2-1B OCR for scanned or low-text PDF startup packets",
        "enabled": True,
        "required": True,
        "backend": "auto",
        "endpoint": "http://host.docker.internal:12434",
        "model": None,
        "quantization": None,
        "min_text_chars": 40,
        "max_pages": None,
        "preload": False,
        "install_policy": "on_first_required_document",
        "remove_policy": "manual",
        "require_hardware_acceleration": True,
        "timeout_seconds": 180,
    }
    assert config["input_skills"]["w3m_browser"]["install_policy"] == "docker_worker_image"
    assert config["input_skills"]["w3m_browser"]["runtime"] == {
        "driver": "docker_worker",
        "install_scope": "shared_job_container",
        "docker_worker_image": "document_workflow/docker_worker",
        "image": "mirror-neuron/vc-assistant:local",
        "network": "mirror-neuron-runtime",
        "node_scope": "vc_python_executor_nodes",
    }
    assert config["skill_runtime"] == {
        "enabled": True,
        "auto_patch": False,
        "driver": "docker_worker",
        "install_scope": "shared_job_container",
        "docker_worker_image": "document_workflow/docker_worker",
        "image": "mirror-neuron/vc-assistant:local",
        "network": "mirror-neuron-runtime",
        "node_scope": "vc_python_executor_nodes",
    }
    assert config["execution"]["max_company_workers"] == 1
    assert config["internet_research"]["max_stage_workers"] == 1
    assert config["backpressure"]["llm"] == {
        "max_concurrent_calls": 1,
        "min_interval_seconds": 1.0,
        "rationale": "Protect local Docker Model Runner from concurrent VC agent calls.",
    }
    assert config["knowledge_rag"]["enabled"] is True
    assert config["knowledge_rag"]["redis_url"] == ""
    assert config["knowledge_rag"]["namespace"] == ""
    assert config["knowledge_rag"]["embedding_provider"] == "docker_model_runner"
    assert config["knowledge_rag"]["embedding_model"] == "hf.co/jinaai/jina-embeddings-v5-text-small-retrieval:Q4_K_M"
    assert config["knowledge_rag"]["embedding_api_base"] == "http://host.docker.internal:12434/engines/v1"
    assert config["knowledge_rag"]["embedding_query_prefix"] == "Query: "
    assert config["knowledge_rag"]["embedding_document_prefix"] == "Document: "
    assert config["knowledge_rag"]["embedding_start_command"] == ""
    assert config["knowledge_rag"]["embedding_healthcheck_enabled"] is True
    assert config["knowledge_rag"]["vector_dim"] == 1024
    assert config["knowledge_rag"]["index_on_startup"] is True
    assert config["knowledge_rag"]["chunk_size"] == 800
    assert config["knowledge_rag"]["chunk_overlap"] == 80
    assert config["research_budget"]["default_actions"] == 160
    assert config["internet_research"]["max_queries"] == 10
    assert config["internet_research"]["max_sources_per_company"] == 10
    assert config["internet_research"]["max_target_urls_per_company"] == 6
    assert config["internet_research"]["rendered_browser"]["max_pages_per_company"] == 3
    assert config["cache_policy"]["enabled"] is True
    assert config["cache_policy"]["force_reprocess"] is False
    assert "force_reprocess" in config["cache_policy"]["force_reprocess_inputs"]
    assert config["agentic_research"]["enabled"] is True
    assert config["agentic_research"]["default_mode"] == "bounded_llm_guided_public_tool_research"
    assert config["agentic_research"]["max_iterations_per_agent"] == 1
    assert config["agentic_research"]["max_tool_calls_per_agent"] == 2
    assert config["actor_review"] == {
        "llm_actor_ids": [
            "research_planner",
            "company_identity_researcher",
            "funding_researcher",
            "market_comp_researcher",
            "traction_verifier",
            "research_reconciler",
            "berkus_scorer",
            "venture_capital_method_scorer",
            "comparables_market_multiple_scorer",
            "score_consistency_auditor",
            "company_report_writer",
            "batch_index_writer",
        ],
        "max_context_chars": 9000,
        "use_context_engine": True,
        "working_memory_persist_to_redis": False,
        "context_token_budget": 5000,
        "context_target_tokens": 1800,
    }
    assert "llm_rag_trace.jsonl" in config["interfaces"]["optional_run_artifacts"]
    assert "llm_rag_trace.jsonl" in config["interfaces"]["channels"]["artifacts"]["optional_artifacts"]
    assert "artifact_quality.json" in config["interfaces"]["outputs"]
    assert "artifact_quality.json" in config["interfaces"]["run_artifacts"]
    assert "artifact_quality.json" in config["interfaces"]["channels"]["artifacts"]["artifacts"]
    assert "run_health.json" in config["interfaces"]["outputs"]
    assert "run_health.json" in config["interfaces"]["run_artifacts"]
    assert "run_health.json" in config["interfaces"]["channels"]["artifacts"]["artifacts"]
    assert "skill_runtime" in config["interfaces"]["config"]
    assert manifest["metadata"]["mn_skill_runtime"]["generated"] is False
    assert manifest["metadata"]["mn_skill_runtime"]["build_context"] == "document_workflow/docker_worker"
    assert manifest["metadata"]["mn_skill_runtime"]["patched_nodes"] == [node["node_id"] for node in nodes]
    dockerfile = (ROOT / "vc_assistant" / "payloads" / "document_workflow" / "docker_worker" / "Dockerfile").read_text(
        encoding="utf-8"
    )
    wrapper = (
        ROOT
        / "vc_assistant"
        / "payloads"
        / "document_workflow"
        / "scripts"
        / "run_blueprint_in_docker_worker.sh"
    ).read_text(encoding="utf-8")
    assert "w3m" in dockerfile
    assert "w3m_browser_skill" in dockerfile
    assert "requirements.txt" in dockerfile
    assert "mn_context_engine_sdk" in dockerfile
    assert "mirrorneuron-membrane-python-sdk" in (
        ROOT / "vc_assistant" / "payloads" / "document_workflow" / "docker_worker" / "requirements.txt"
    ).read_text(encoding="utf-8")
    assert "command -v w3m" in wrapper
    assert "import mn_w3m_browser_skill" in wrapper
    assert "from mn_context_engine_sdk import MemoryItem, WorkingMemory" in wrapper
    assert "examples/sample_inputs/" in manifest["metadata"]["configuration_contract"]["required_files"]
    assert (
        "payloads/document_workflow/vc_assistant/examples/sample_inputs/"
        in manifest["metadata"]["configuration_contract"]["required_files"]
    )
    for node in nodes:
        assert "python_environment" not in node["config"]
        assert node["config"]["runner_module"] == "MirrorNeuron.Runner.DockerWorker"
        assert node["config"]["workdir"] == "/mn/job/document_workflow"
        assert node["config"]["command"] == ["bash", "scripts/run_blueprint_in_docker_worker.sh"]
        assert node["config"]["docker_worker_image"] == "document_workflow/docker_worker"
        assert node["config"]["image"] == "mirror-neuron/vc-assistant:local"
        assert node["config"]["network"] == "mirror-neuron-runtime"
        assert node["config"]["shared_container"] is True
        assert node["config"]["reuse_shared_container"] is True
        assert node["config"]["upload_paths"] == upload_paths
        assert node["config"]["build_context_upload_paths"] == build_context_upload_paths
        environment = node["config"]["environment"]
        assert environment["MN_WORKFLOW_STEP_ID"] == node["node_id"]
        embedded_config = json.loads(environment["MN_BLUEPRINT_CONFIG_JSON"])
        assert embedded_config["inputs"]["payload"]["input_folder"] == "vc_assistant/examples/sample_inputs"
        assert embedded_config["inputs"]["payload"]["output_folder"] == "~/Downloads/vc_assistant"
        assert embedded_config["outputs"]["folder_path"] == "~/Downloads/vc_assistant"
        assert embedded_config["llm"]["model"] == "default"
        assert embedded_config["llm"]["quick_test_uses_fake"] is True
        assert embedded_config["execution"]["quick_test"] is False
        assert embedded_config["research_budget"]["default_actions"] == 160
        assert embedded_config["agentic_research"]["enabled"] is True
        assert embedded_config["agentic_research"]["default_mode"] == "bounded_llm_guided_public_tool_research"
        assert embedded_config["agentic_research"]["agent_ids"] == [
            "research_planner",
            "company_identity_researcher",
            "funding_researcher",
            "market_comp_researcher",
            "traction_verifier",
            "rendered_page_researcher",
        ]
        assert embedded_config["agentic_research"]["max_iterations_per_agent"] == 1
        assert embedded_config["agentic_research"]["max_tool_calls_per_agent"] == 2
        assert embedded_config["agentic_research"]["allowed_tools"] == ["browser_search", "browser_page", "rendered_browser_page", "finish"]
        assert embedded_config["actor_review"] == config["actor_review"]
        assert embedded_config["backpressure"] == config["backpressure"]
        assert embedded_config["knowledge_rag"] == config["knowledge_rag"]
        assert embedded_config["python_dependencies"] == config["python_dependencies"]
        assert embedded_config["input_skills"]["llm_ocr"] == config["input_skills"]["llm_ocr"]
        assert embedded_config["input_skills"]["w3m_browser"] == config["input_skills"]["w3m_browser"]
        assert embedded_config["skill_runtime"] == config["skill_runtime"]
        assert embedded_config["suggested_schedule"] == config["suggested_schedule"]
    for template in manifest["metadata"]["agent_templates"]["nodes"]:
        if template["node_id"] == "report_sink":
            assert template["uses"] == "mn-agents.control_join@1.0.0"
            continue
        assert "python_environment" not in template["with"]
        assert template["with"]["runner_module"] == "MirrorNeuron.Runner.DockerWorker"
        assert template["with"]["workdir"] == "/mn/job/document_workflow"
        assert template["with"]["command"] == ["bash", "scripts/run_blueprint_in_docker_worker.sh"]
        assert template["with"]["docker_worker_image"] == "document_workflow/docker_worker"
        assert template["with"]["image"] == "mirror-neuron/vc-assistant:local"
        assert template["with"]["network"] == "mirror-neuron-runtime"
        assert template["with"]["shared_container"] is True
        assert template["with"]["reuse_shared_container"] is True
        assert template["with"]["upload_paths"] == upload_paths
        assert template["with"]["build_context_upload_paths"] == build_context_upload_paths
        template_config = json.loads(template["with"]["environment"]["MN_BLUEPRINT_CONFIG_JSON"])
        assert template_config["backpressure"] == config["backpressure"]
        assert template_config["knowledge_rag"] == config["knowledge_rag"]
        assert template_config["actor_review"] == config["actor_review"]
        assert template_config["input_skills"]["llm_ocr"] == config["input_skills"]["llm_ocr"]
        assert template_config["input_skills"]["w3m_browser"] == config["input_skills"]["w3m_browser"]
        assert template_config["skill_runtime"] == config["skill_runtime"]
        assert template_config["suggested_schedule"] == config["suggested_schedule"]


def test_explicit_fake_llm_mode_overrides_live_vc_runtime(monkeypatch, tmp_path):
    runner = _load_runner()
    config = json.loads((ROOT / "vc_assistant" / "config" / "default.json").read_text(encoding="utf-8"))

    monkeypatch.setenv("MN_BLUEPRINT_FAKE_LLM", "true")

    assert runner.fake_llm_mode_enabled(config) is True
    assert runner.llm_requires_live(config) is False
    assert runner._configured_llm_env(config) == {
        "MN_BLUEPRINT_LLM_MODE": "fake",
        "MN_LLM_PROVIDER": "fake",
        "MN_LLM_MODEL": "fake-vc-actor",
    }

    limiter = runner.build_llm_call_limiter(config)
    assert limiter.config_summary()["min_interval_seconds"] == 0.0

    knowledge = runner.load_vc_knowledge(ROOT / "vc_assistant")
    rag = runner.prepare_knowledge_rag(
        blueprint_dir=ROOT / "vc_assistant",
        resolved_config=config,
        active_knowledge=knowledge,
        run_dir=tmp_path,
    )
    assert rag["enabled"] is False
    assert rag["status"] == "disabled_for_fake_llm"
    assert runner.knowledge_rag_is_required(rag) is False


def test_actor_llm_init_failure_writes_failed_run(tmp_path, monkeypatch):
    runner = _load_runner()
    docs = tmp_path / "startup-docs"
    outputs = tmp_path / "reports"
    _write_startup_packets(docs)

    def fail_init(config, llm_client):
        raise RuntimeError("actor client init timed out")

    monkeypatch.setattr(runner, "_get_configured_actor_llm", fail_init)

    with pytest.raises(RuntimeError, match="actor client init timed out"):
        runner.run_blueprint(
            inputs={
                "document_folder": str(docs),
                "output_folder": str(outputs),
                "monitoring": {"enabled": True, "poll_interval_seconds": 1, "max_cycles": 1},
            },
            config={
                "knowledge_rag": {"enabled": False, "required": False},
                "backpressure": {"llm": {"max_concurrent_calls": 1, "min_interval_seconds": 0}},
            },
            runs_root=tmp_path,
            run_id="vc-llm-init-failed",
        )

    run_dir = tmp_path / "vc-llm-init-failed"
    run_json = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    assert run_json["status"] == "failed"
    assert "actor client init timed out" in run_json["error"]
    events = (run_dir / "events.jsonl").read_text(encoding="utf-8")
    assert "actor_llm.init" in events
    assert "required_actor_llm_init_failed" in events


def test_vc_assistant_is_daily_batch_folder_scan():
    index = json.loads((ROOT / "index.json").read_text(encoding="utf-8"))
    entry = next(item for item in index if item["id"] == "vc_assistant")
    manifest = json.loads((ROOT / "vc_assistant" / "manifest.json").read_text(encoding="utf-8"))
    config = json.loads((ROOT / "vc_assistant" / "config" / "default.json").read_text(encoding="utf-8"))

    assert entry["type"] == "batch"
    assert "service" not in entry["product"]["runtime_features"][0]
    assert entry["product"]["runtime_features"][0] == "daily scheduled folder scan"
    assert manifest["metadata"]["runtime_features"][0] == "daily scheduled folder scan"
    assert config["monitoring"]["max_cycles"] == 1
    assert config["triggers"]["schedule"] is None
    assert config["suggested_schedule"] == {
        "cron": "0 7 * * *",
        "cadence": "daily",
        "advisory_only": True,
        "note": "Suggested cadence only; runtime decides the actual schedule.",
    }


def test_vc_assistant_runtime_requirements_install_skills_with_pip():
    requirements = (
        ROOT / "vc_assistant" / "payloads" / "document_workflow" / "requirements.txt"
    ).read_text(encoding="utf-8").splitlines()

    assert requirements == [
        "--index-url https://us-central1-python.pkg.dev/mirrorneuron-public-packages/agent-skills/simple/",
        "--extra-index-url https://pypi.org/simple",
        "mirrorneuron-blueprint-support-skill",
        "mirrorneuron-membrane-python-sdk",
        "mirrorneuron-llm-ocr-skill",
        "mirrorneuron-rag-skill",
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


def test_budgeted_llm_serializes_concurrent_model_calls():
    runner = _load_runner()
    active_calls = 0
    max_active_calls = 0
    lock = threading.Lock()

    class SlowVCLLM(FakeVCLLM):
        provider = "docker_model_runner"

        def generate_json(self, *, system_prompt: str, user_prompt: str, fallback: dict):
            nonlocal active_calls, max_active_calls
            with lock:
                active_calls += 1
                max_active_calls = max(max_active_calls, active_calls)
            time.sleep(0.02)
            try:
                return super().generate_json(system_prompt=system_prompt, user_prompt=user_prompt, fallback=fallback)
            finally:
                with lock:
                    active_calls -= 1

    llm = runner.BudgetedLLM(
        SlowVCLLM(),
        runner.ActionBudget(10),
        limiter=runner.LlmCallLimiter(max_concurrent_calls=1, min_interval_seconds=0),
    )
    results: list[dict] = []

    def call_llm(index: int) -> None:
        results.append(
            llm.generate_json(
                system_prompt=f"actor-{index}",
                user_prompt="{}",
                fallback={"actor_id": f"actor-{index}", "summary": ""},
            )
        )

    threads = [threading.Thread(target=call_llm, args=(index,)) for index in range(5)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(results) == 5
    assert max_active_calls == 1


def test_budgeted_llm_writes_metadata_only_trace(tmp_path):
    runner = _load_runner()
    llm = runner.BudgetedLLM(
        FakeVCLLM(),
        runner.ActionBudget(10),
        limiter=runner.LlmCallLimiter(max_concurrent_calls=1, min_interval_seconds=0),
        run_dir=tmp_path,
        heartbeat_seconds=0,
    )

    llm.generate_json(
        system_prompt="secret system prompt",
        user_prompt='{"raw_document_text":"Confidential Startup ARR $250k"}',
        fallback={"actor_id": "research_reconciler", "summary": ""},
    )

    trace_text = (tmp_path / "llm_rag_trace.jsonl").read_text(encoding="utf-8")
    assert "secret system prompt" not in trace_text
    assert "Confidential Startup ARR" not in trace_text
    records = [json.loads(line) for line in trace_text.splitlines()]
    completed = [record for record in records if record["type"] == "observability_operation_completed"]
    assert completed
    payload = completed[-1]["payload"]
    assert payload["phase"] == "llm_call"
    assert payload["agent_id"] == "research_reconciler"
    assert payload["prompt_hash"]
    assert payload["user_prompt_chars"] > 0
    assert payload["response_chars"] > 0
    assert payload["provider"] == "fake"
    assert "elapsed_ms" in payload


def test_observed_operation_emits_heartbeat(tmp_path):
    runner = _load_runner()

    with runner.observed_operation(tmp_path, phase="knowledge_rag", operation="prepare", heartbeat_seconds=0.01):
        time.sleep(0.03)

    records = [json.loads(line) for line in (tmp_path / "llm_rag_trace.jsonl").read_text(encoding="utf-8").splitlines()]
    assert any(record["type"] == "observability_operation_started" for record in records)
    assert any(record["type"] == "observability_operation_heartbeat" for record in records)
    assert any(record["type"] == "observability_operation_completed" for record in records)


def test_rag_retrieval_observation_is_metadata_only(monkeypatch, tmp_path):
    runner = _load_runner()
    monkeypatch.setattr(runner, "_load_rag_skill", lambda: None)

    def fake_retrieve(**kwargs):
        return {
            "enabled": True,
            "status": "ready",
            "query": kwargs["query"],
            "context": "Sensitive RAG context should not be written to trace.",
            "citations": [{"ref": 1, "chunk_id": "chunk-1"}],
            "chunks": [],
        }

    monkeypatch.setattr(runner, "skill_retrieve_knowledge_rag_context", fake_retrieve)
    context = runner.retrieve_knowledge_rag_context(
        knowledge_rag={"enabled": True, "status": "ready"},
        query="Confidential company query",
        stage="research_planner",
        company="SecretCo",
        run_dir=tmp_path,
    )

    assert context["status"] == "ready"
    trace_text = (tmp_path / "llm_rag_trace.jsonl").read_text(encoding="utf-8")
    assert "Confidential company query" not in trace_text
    assert "Sensitive RAG context" not in trace_text
    completed = [json.loads(line) for line in trace_text.splitlines() if "observability_operation_completed" in line][-1]
    payload = completed["payload"]
    assert payload["phase"] == "knowledge_rag"
    assert payload["operation"] == "retrieve"
    assert payload["query_hash"]
    assert payload["query_chars"] == len("Confidential company query")
    assert payload["citation_count"] == 1
    assert payload["context_chars"] == len("Sensitive RAG context should not be written to trace.")


def test_vc_pdf_packets_use_llm_ocr_skill_for_evidence(monkeypatch, tmp_path):
    runner = _load_runner()
    docs = tmp_path / "startup-docs"
    company_dir = docs / "optical_ventures"
    company_dir.mkdir(parents=True)
    pdf_path = company_dir / "pitch.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 synthetic startup packet")
    (company_dir / "memo.txt").write_text("Company: Optical Ventures\nMarket: oncology workflow software.", encoding="utf-8")
    factory_configs = []

    def fake_factory(config):
        factory_configs.append(config)
        return lambda: object()

    def fake_extract_document_folder(folder, **kwargs):
        assert Path(folder) == company_dir
        assert kwargs["min_text_chars"] == 40
        assert kwargs["llm_ocr_client_factory"] is not None
        return [
            {
                "path": str(pdf_path),
                "filename": "pitch.pdf",
                "document_type": "startup_packet",
                "text": "Company: Optical Ventures\nTraction: $900k ARR from seven enterprise pilots.",
                "ocr_required": False,
                "extraction_method": "llm_ocr",
                "warnings": ["low contrast page reviewed"],
                "metadata": {"ocr_model": "LightOnOCR-2-1B"},
            }
        ]

    monkeypatch.setattr(runner, "docker_ocr_client_factory_from_config", fake_factory)
    monkeypatch.setattr(runner, "extract_document_folder", fake_extract_document_folder)

    records = runner.scan_documents(
        docs,
        {"input_skills": {"llm_ocr": {"enabled": True, "required": True, "min_text_chars": 40}}},
    )

    assert sorted(records) == ["Optical Ventures"]
    pdf_record = next(record for record in records["Optical Ventures"] if record["filename"] == "pitch.pdf")
    txt_record = next(record for record in records["Optical Ventures"] if record["filename"] == "memo.txt")
    assert pdf_record["text_preview"].startswith("Company: Optical Ventures")
    assert pdf_record["character_count"] > 40
    assert pdf_record["extraction_method"] == "llm_ocr"
    assert pdf_record["ocr_required"] is False
    assert pdf_record["warnings"] == ["low contrast page reviewed"]
    assert len(pdf_record["sha256"]) == 64
    assert txt_record["extraction_method"] == "embedded_text"
    assert txt_record["ocr_required"] is False
    assert factory_configs == [{"input_skills": {"llm_ocr": {"enabled": True, "required": True, "min_text_chars": 40}}}]


def test_vc_pdf_packets_fail_closed_when_ocr_unavailable(monkeypatch, tmp_path):
    runner = _load_runner()
    docs = tmp_path / "startup-docs"
    docs.mkdir()
    (docs / "pitch.pdf").write_bytes(b"%PDF-1.4 image-only packet")
    monkeypatch.setattr(runner, "extract_document_folder", None)

    with pytest.raises(runner.OcrRequiredError, match="OCR extractor is unavailable"):
        runner.scan_documents(docs, {"input_skills": {"llm_ocr": {"enabled": True, "required": True}}})


def test_vc_ocr_failure_marks_run_failed(monkeypatch, tmp_path):
    runner = _load_runner()
    docs = tmp_path / "startup-docs"
    docs.mkdir()
    (docs / "pitch.pdf").write_bytes(b"%PDF-1.4 image-only packet")
    outputs = tmp_path / "reports"

    monkeypatch.setattr(runner, "prepare_knowledge_rag", lambda **kwargs: {"enabled": False, "status": "disabled"})
    monkeypatch.setattr(runner, "require_ready_rag", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        runner,
        "scan_documents",
        lambda folder, config=None: (_ for _ in ()).throw(runner.OcrRequiredError("PDF OCR did not produce usable text")),
    )

    with pytest.raises(runner.OcrRequiredError, match="PDF OCR did not produce usable text"):
        runner.run_blueprint(
            inputs={"document_folder": str(docs), "output_folder": str(outputs)},
            config={"llm": {"mode": "fake", "require_live": False}, "knowledge_rag": {"enabled": False, "required": False}},
            runs_root=tmp_path,
            run_id="vc-ocr-failed",
            llm_client=FakeVCLLM(),
        )

    run_json = json.loads((tmp_path / "vc-ocr-failed" / "run.json").read_text(encoding="utf-8"))
    events = [
        json.loads(line)
        for line in (tmp_path / "vc-ocr-failed" / "events.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert run_json["status"] == "failed"
    assert run_json["error"] == "PDF OCR did not produce usable text"
    assert any(
        event["type"] == "tool_call_failed"
        and event["payload"]["tool"] == "llm_ocr.extract_document_folder"
        and event["payload"]["status"] == "required_ocr_failed"
        for event in events
    )


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
        assert agents[actor_id]["model"] == "default"

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


def test_adaptive_research_plan_extracts_public_safe_signals():
    runner = _load_runner()
    records = [
        {
            "filename": "packet.md",
            "text_preview": "\n".join(
                [
                    "Company: Example AI",
                    "Website: https://example.ai",
                    "GitHub: https://github.com/example/example-ai",
                    "Docs: https://docs.example.ai/api",
                    "Founder profile: https://www.linkedin.com/company/example-ai",
                    "Pricing is subscription usage based. SOC 2 compliance planned.",
                    "Open source SDK with customer pilots and ARR traction.",
                ]
            ),
        }
    ]

    signals = runner.extract_public_research_signals(records)
    assert signals["github_urls"] == ["https://github.com/example/example-ai"]
    assert "https://docs.example.ai/api" in signals["docs_urls"]
    assert "https://www.linkedin.com/company/example-ai" in signals["profile_urls"]
    assert "pricing" in signals["pricing_terms"]
    assert "soc 2" in signals["regulatory_terms"]

    plan = runner.build_adaptive_research_plan("Example AI", records, {"max_queries": 20, "max_target_urls_per_company": 10, "rendered_browser": {"max_pages_per_company": 5}})
    lane_ids = {lane["lane_id"] for lane in plan["lanes"]}
    assert {"github_research", "technical_product_research", "founder_research", "pricing_business_model_research", "regulatory_risk_research"} <= lane_ids
    assert "https://github.com/example/example-ai" in plan["stage_target_urls"]["market_comp_researcher"]
    assert any("GitHub" in query for query in plan["stage_queries"]["market_comp_researcher"])
    assert "https://www.linkedin.com/company/example-ai" in plan["rendered_target_urls"]
    assert "confidential excerpts" in plan["privacy_policy"]


def test_adaptive_research_routes_known_urls_to_direct_fetches(monkeypatch, tmp_path):
    runner = _load_runner()
    records = [
        {
            "filename": "packet.md",
            "text_preview": "GitHub https://github.com/example/example-ai Docs https://docs.example.ai/api LinkedIn https://www.linkedin.com/company/example-ai",
        }
    ]
    direct_urls = []
    rendered_urls = []

    def fake_w3m(sources, *, company, plan, internet, run_dir, verification_target="search_result_or_public_source"):
        sources.append(runner._source_record(
            company=company,
            query=plan["queries"][0],
            url=f"https://example.com/{verification_target}",
            title=verification_target,
            snippet="public evidence",
            status="ok",
            skill="w3m_browser_skill",
            verification_target=verification_target,
        ))

    def fake_target(sources, *, company, plan, internet, run_dir):
        direct_urls.extend(plan.get("target_urls") or [])
        for url in plan.get("target_urls") or []:
            sources.append(runner._source_record(
                company=company,
                query=plan["queries"][0],
                url=url,
                title=url,
                snippet="direct public page",
                status="ok",
                skill="w3m_browser_skill",
                verification_target="public_profile",
            ))

    def fake_rendered(sources, *, company, plan, internet, action_budget=None):
        rendered_urls.extend(plan.get("target_urls") or [])
        for url in plan.get("target_urls") or []:
            sources.append(runner._source_record(
                company=company,
                query=plan["queries"][0],
                url=url,
                title="Rendered",
                snippet="rendered profile",
                status="ok",
                skill="web_browser_skill",
                verification_target="rendered_public_profile",
            ))

    monkeypatch.setattr(runner, "_append_w3m_research", fake_w3m)
    monkeypatch.setattr(runner, "_append_target_url_research", fake_target)
    monkeypatch.setattr(runner, "_append_rendered_browser_research", fake_rendered)

    ledger = runner.research_company_by_stage(
        "Example AI",
        {"internet_research": {"enabled": True, "max_stage_workers": 1, "rendered_browser": {"enabled": True, "max_pages_per_company": 5}}},
        run_dir=tmp_path,
        records=records,
    )

    assert set(ledger) == set(runner.RESEARCH_STAGE_IDS)
    assert "https://github.com/example/example-ai" in direct_urls
    assert "https://docs.example.ai/api" in direct_urls
    assert "https://www.linkedin.com/company/example-ai" in direct_urls
    assert "https://www.linkedin.com/company/example-ai" in rendered_urls
    assert any(source["source_quality_label"] == "technical_signal" for source in ledger["market_comp_researcher"])


def test_agentic_research_executes_llm_selected_tools(monkeypatch, tmp_path):
    runner = _load_runner()

    class DummyConfig:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    monkeypatch.setattr(runner, "_load_w3m_browser_skill", lambda: None)
    monkeypatch.setattr(runner, "W3mBrowserConfig", DummyConfig)
    monkeypatch.setattr(runner, "research_topic", lambda query, browser_config, max_sources, observer=None: {"sources": [{"url": "https://example.com/search", "title": "Search", "snippet": query}], "warnings": []})
    monkeypatch.setattr(runner, "browse_url", lambda url, browser_config, observer=None: {"status": "ok", "url": url, "title": "Direct", "snippet": "direct page"})
    monkeypatch.setattr(runner, "_load_web_browser_skill", lambda: None)
    monkeypatch.setattr(runner, "WebBrowserConfig", DummyConfig)
    monkeypatch.setattr(runner, "scrape_page", lambda url, browser_config: {"status": "ok", "final_url": url, "title": "Rendered", "text": "rendered page", "warnings": []})

    decisions = {
        "research_planner": [{"thought_summary": "planner done", "tool_calls": [{"tool": "finish", "reason": "planned"}], "stop_reason": "planned", "evidence_gaps": []}],
        "company_identity_researcher": [{"thought_summary": "search identity", "tool_calls": [{"tool": "browser_search", "query": "Example AI company website"}], "stop_reason": "", "evidence_gaps": []}],
        "market_comp_researcher": [{"thought_summary": "inspect github", "tool_calls": [{"tool": "browser_page", "url": "https://github.com/example/example-ai", "query": "Example AI GitHub"}], "stop_reason": "", "evidence_gaps": []}],
        "traction_verifier": [{"thought_summary": "done", "tool_calls": [{"tool": "finish", "reason": "no public traction url"}], "stop_reason": "done", "evidence_gaps": ["public traction proof"]}],
        "rendered_page_researcher": [{"thought_summary": "render profile", "tool_calls": [{"tool": "rendered_browser_page", "url": "https://www.linkedin.com/company/example-ai", "query": "Example AI rendered profile"}], "stop_reason": "", "evidence_gaps": []}],
    }
    llm = runner.BudgetedLLM(ToolCallingVCLLM(decisions), runner.ActionBudget(100))
    records = [{"filename": "packet.md", "text_preview": "GitHub https://github.com/example/example-ai LinkedIn https://www.linkedin.com/company/example-ai"}]
    trace = []

    ledger = runner.research_company_by_stage(
        "Example AI",
        {
            "internet_research": {"enabled": True, "max_stage_workers": 1, "rendered_browser": {"enabled": True, "max_pages_per_company": 5}},
            "agentic_research": {
                "enabled": True,
                "agent_ids": ["research_planner", "company_identity_researcher", "market_comp_researcher", "traction_verifier", "rendered_page_researcher"],
                "max_iterations_per_agent": 20,
                "max_tool_calls_per_agent": 50,
                "allowed_tools": ["browser_search", "browser_page", "rendered_browser_page", "finish"],
            },
        },
        run_dir=tmp_path,
        action_budget=llm._action_budget,
        records=records,
        llm=llm,
        agent_tool_trace=trace,
    )

    assert {item["agent_id"] for item in trace} == {"research_planner", "company_identity_researcher", "market_comp_researcher", "traction_verifier", "rendered_page_researcher"}
    assert "funding_researcher" not in {item["agent_id"] for item in trace}
    assert any(source.get("tool_decision_source") == "llm_agent" and source.get("agent_id") == "market_comp_researcher" for source in ledger["market_comp_researcher"])
    assert any(source.get("skill") == "web_browser_skill" and source.get("agent_id") == "rendered_page_researcher" for source in ledger["rendered_page_researcher"])
    assert all(item["max_iterations"] == 20 for item in trace)
    assert all(item["max_tool_calls"] == 50 for item in trace)


def test_agentic_research_blocks_confidential_tool_queries(tmp_path):
    runner = _load_runner()
    decisions = {
        "market_comp_researcher": [
            {
                "thought_summary": "bad query",
                "tool_calls": [{"tool": "browser_search", "query": "confidential raw document text customer_names private financials"}],
                "stop_reason": "",
                "evidence_gaps": [],
            }
        ]
    }
    llm = runner.BudgetedLLM(ToolCallingVCLLM(decisions), runner.ActionBudget(20))
    plan = runner.build_adaptive_research_plan("Example AI", [], {"max_queries": 20, "rendered_browser": {"max_pages_per_company": 5}})
    trace = []

    stage, sources = runner.run_agentic_research_stage(
        company="Example AI",
        stage="market_comp_researcher",
        plan=plan,
        internet={"blocked_inputs": ["raw_document_text", "customer_names", "private_financials"]},
        run_dir=tmp_path,
        action_budget=llm._action_budget,
        llm=llm,
        agentic={"enabled": True, "agent_ids": ["market_comp_researcher"], "max_iterations_per_agent": 20, "max_tool_calls_per_agent": 50, "allowed_tools": ["browser_search", "browser_page", "rendered_browser_page", "finish"]},
        trace=trace,
    )

    assert stage == "market_comp_researcher"
    assert any(source["status"] == "agent_invalid_tool_call" for source in sources)
    assert trace[0]["validation_failures"]
    assert trace[0]["tool_call_count"] == 0


def test_agentic_research_tool_exceptions_continue_as_failed_sources(monkeypatch, tmp_path):
    runner = _load_runner()
    llm = runner.BudgetedLLM(
        ToolCallingVCLLM(
            {
                "market_comp_researcher": [
                    {
                        "thought_summary": "try public search",
                        "tool_calls": [{"tool": "browser_search", "query": "Example AI market competitors"}],
                        "stop_reason": "",
                        "evidence_gaps": [],
                    }
                ]
            }
        ),
        runner.ActionBudget(20),
    )
    plan = runner.build_adaptive_research_plan("Example AI", [], {"max_queries": 20, "rendered_browser": {"max_pages_per_company": 5}})
    trace = []
    monkeypatch.setattr(runner, "_execute_agent_tool_call", lambda **_: (_ for _ in ()).throw(RuntimeError("browser timeout")))

    stage, sources = runner.run_agentic_research_stage(
        company="Example AI",
        stage="market_comp_researcher",
        plan=plan,
        internet={"blocked_inputs": []},
        run_dir=tmp_path,
        action_budget=llm._action_budget,
        llm=llm,
        agentic={"enabled": True, "agent_ids": ["market_comp_researcher"], "max_iterations_per_agent": 1, "max_tool_calls_per_agent": 2, "allowed_tools": ["browser_search", "browser_page", "rendered_browser_page", "finish"]},
        trace=trace,
    )

    assert stage == "market_comp_researcher"
    assert any(source["status"] == "agent_tool_call_failed" and "browser timeout" in source["warning"] for source in sources)
    assert trace[0]["tool_call_count"] == 1
    trace_text = (tmp_path / "llm_rag_trace.jsonl").read_text(encoding="utf-8")
    assert "browser timeout" in trace_text
    assert "observability_operation_failed" in trace_text


def test_agentic_research_prompt_includes_knowledge_rag_context(monkeypatch, tmp_path):
    runner = _load_runner()
    llm_client = ToolCallingVCLLM(
        {
            "market_comp_researcher": [
                {
                    "thought_summary": "enough knowledge",
                    "tool_calls": [{"tool": "finish", "reason": "rag guidance reviewed"}],
                    "stop_reason": "rag_guidance_reviewed",
                    "evidence_gaps": [],
                }
            ]
        }
    )
    llm = runner.BudgetedLLM(llm_client, runner.ActionBudget(20))
    plan = runner.build_adaptive_research_plan(
        "Example AI",
        [{"filename": "packet.md", "text_preview": "GitHub https://github.com/example/example-ai"}],
        {"max_queries": 20, "rendered_browser": {"max_pages_per_company": 5}},
    )
    monkeypatch.setattr(runner, "_load_rag_skill", lambda: None)
    monkeypatch.setattr(
        runner,
        "skill_retrieve_knowledge_rag_context",
        lambda *, knowledge_rag, query, stage="", company="", **_: {
            "enabled": True,
            "status": "ready",
            "query": query,
            "context": "GitHub playbook context: inspect stars, issues, releases, README, and package hints.",
            "citations": [{"ref": 1, "chunk_id": "chunk-github", "path": "startup_research_playbook.md", "heading": "GitHub Evidence", "score": 0.91}],
            "chunks": [{"chunk_id": "chunk-github"}],
            "stage": stage,
            "company": company,
        },
    )
    trace = []

    stage, _sources = runner.run_agentic_research_stage(
        company="Example AI",
        stage="market_comp_researcher",
        plan=plan,
        internet={"blocked_inputs": []},
        run_dir=tmp_path,
        action_budget=llm._action_budget,
        llm=llm,
        agentic={"enabled": True, "agent_ids": ["market_comp_researcher"], "max_iterations_per_agent": 20, "max_tool_calls_per_agent": 50, "allowed_tools": ["browser_search", "browser_page", "rendered_browser_page", "finish"]},
        trace=trace,
        knowledge_rag={"enabled": True, "status": "ready", "_rag_config": object(), "config": {"max_context_chars": 6000}, "warnings": []},
    )

    assert stage == "market_comp_researcher"
    prompt_payload = llm_client.prompts[0]["user"]
    assert "GitHub playbook context" in prompt_payload
    assert trace[0]["rag_context"]["status"] == "ready"
    assert trace[0]["knowledge_refs"][0]["chunk_id"] == "chunk-github"


def test_knowledge_rag_failure_records_explicit_warning(monkeypatch, tmp_path):
    runner = _load_runner()
    monkeypatch.setattr(runner, "_load_rag_skill", lambda: (_ for _ in ()).throw(RuntimeError("redis unavailable")))

    state = runner.prepare_knowledge_rag(
        blueprint_dir=ROOT / "vc_assistant",
        resolved_config={"knowledge_rag": {"enabled": True}},
        active_knowledge=runner.load_vc_knowledge(ROOT / "vc_assistant"),
        run_dir=tmp_path,
    )

    assert state["status"] == "knowledge_rag_failed"
    assert state["warnings"][0]["status"] == "knowledge_rag_failed"
    assert "no static playbook fallback" in state["warnings"][0]["message"]


def test_actor_review_context_is_compacted_and_bounded():
    runner = _load_runner()
    analyses = []
    for index in range(3):
        methods = {
            method_id: {
                "status": "scored",
                "score": index + 1,
                "memory_hook": "hook",
                "evidence_summary": {"status_reason": "x" * 1000},
                "evidence_refs": [f"doc-{index}"],
                "missing_evidence": ["missing"] * 10,
                "assumptions": ["assumption"] * 10,
                "warnings": ["warning"] * 10,
            }
            for method_id in runner.METHOD_IDS
        }
        analyses.append(
            {
                "company_name": f"Company {index}",
                "company_slug": f"company-{index}",
                "processing_status": "new_or_changed",
                "composite_score": 7,
                "methods": methods,
                "evidence_summary": {"missing_methods": []},
                "audit": {"warnings": ["warn"] * 5},
                "research_reconciliation": {"confirmations": [1], "contradictions": [], "missing_public_evidence": [1]},
                "research_plan": {"lanes": [{"lane_id": "market"}], "github_urls": [], "known_public_urls": ["https://example.com"], "signals": {"market_terms": True}},
            }
        )

    context = runner.build_actor_review_context(
        analyses=analyses,
        company_work_queue=[],
        research_coverage={"companies": []},
        method_coverage={"companies": []},
        processed_company_names=["Company 0"],
        skipped_company_names=[],
        output_files=[{"kind": "analysis", "path": f"/tmp/{index}.json"} for index in range(50)],
        active_knowledge={"id": "knowledge", "content": "very long content", "method_guidance": {}, "judge_rubric": runner.JUDGE_RUBRIC},
        knowledge_rag={"enabled": True, "status": "ready", "config": {"required": True}},
        actor_rag_context={"enabled": True, "status": "ready", "context": "rag context", "citations": [{"ref": 1}]},
        max_context_chars=6000,
    )

    serialized = json.dumps(context, default=str)
    assert context["truncated_for_actor_review"] is True
    assert len(serialized) < 7000
    assert "very long content" not in serialized
    assert context["company_summaries"][0]["method_statuses"]
    assert context["rag_context"]["citation_count"] == 1


def test_actor_review_prompt_context_uses_local_context_engine_without_redis_persistence(monkeypatch, tmp_path):
    runner = _load_runner()
    calls = {}

    class FakeMemoryItem:
        def __init__(self, **kwargs):
            calls["memory_item"] = kwargs
            self.kwargs = kwargs

    class FakeWorkingMemory:
        def __init__(self):
            self.items = []

        def add(self, item):
            self.items.append(item)
            calls["added_item_count"] = len(self.items)

        def to_dict(self):
            return {"items": [item.kwargs for item in self.items]}

    monkeypatch.setattr(runner, "MemoryItem", FakeMemoryItem)
    monkeypatch.setattr(runner, "WorkingMemory", FakeWorkingMemory)

    context = {
        "blueprint_id": "vc_assistant",
        "output_type": "vc_early_heuristic_analysis_reports",
        "report_only": True,
        "decision_boundary": "reports only",
        "company_count": 1,
        "processed_company_names": ["Alpha AI"],
        "skipped_company_names": [],
        "company_summaries": [{"company_name": "Alpha AI", "method_evidence": "very long content" * 1000}],
        "method_coverage": {"companies": [{"company": "Alpha AI", "details": "very long content" * 1000}]},
        "rag_context": {"enabled": True, "status": "ready", "citations": [{"ref": 1}]},
        "output_files": [{"path": "/tmp/alpha/analysis.json", "kind": "analysis"}],
        "privacy_controls": {"local_document_text": "not included"},
        "actor_review_focus": ["review method coverage", "check warnings"],
    }

    prompt_context = runner.prepare_actor_review_prompt_context(
        run_id="vc-compress",
        context=context,
        config={
            "actor_review": {
                "use_context_engine": True,
                "working_memory_persist_to_redis": False,
                "max_context_chars": 6000,
                "context_token_budget": 3000,
                "context_target_tokens": 1200,
            }
        },
        run_dir=tmp_path,
    )

    serialized = json.dumps(prompt_context, default=str)
    assert calls["added_item_count"] == 1
    assert calls["memory_item"]["content"]["validation"]["persistent_storage"] is False
    assert prompt_context["context_compression"]["enabled"] is True
    assert prompt_context["context_compression"]["persisted"] is False
    assert prompt_context["context_compression"]["working_memory_persist_to_redis"] is False
    assert prompt_context["memory_boundary"]["rag_knowledge"] == "persistent Redis-backed knowledge index"
    assert "mn_context_engine_sdk.WorkingMemory" in serialized
    assert len(serialized) < 7000
    trace_text = (tmp_path / "llm_rag_trace.jsonl").read_text(encoding="utf-8")
    assert "compile_actor_review_context" in trace_text
    assert '"persisted": false' in trace_text
    assert "very long content" not in trace_text


def test_vc_early_heuristic_filtering_writes_score_only_company_reports(tmp_path, monkeypatch):
    runner = _load_runner()
    docs = tmp_path / "startup-docs"
    outputs = tmp_path / "reports"
    _write_startup_packets(docs)
    fake_llm = FakeVCLLM()

    def fake_public_rag_state(state):
        return {key: value for key, value in state.items() if not key.startswith("_")}

    def fake_prepare_rag(**kwargs):
        return {
            "enabled": True,
            "status": "ready",
            "_rag_config": object(),
            "knowledge_dir": str(ROOT / "vc_assistant" / "knowledge"),
            "config": {
                "namespace": "test_namespace",
                "index_name": "idx:test_namespace:rag:vc_assistant",
                "key_prefix": "test_namespace:rag:vc_assistant",
                "embedding_provider": "docker_model_runner",
                "embedding_model": "fake-embedding-model",
                "top_k": 5,
                "max_context_chars": 6000,
            },
            "index_summary": {"indexed_count": 3, "deleted_count": 0, "index_name": "idx:test_namespace:rag:vc_assistant"},
            "warnings": [],
        }

    def fake_rag_context(*, knowledge_rag, query, stage="", company="", **kwargs):
        return {
            "enabled": True,
            "status": "ready",
            "query": query,
            "context": (
                "VC Startup Research And Method Playbook. Berkus Method. Scorecard / Bill Payne Method. "
                "Risk Factor Summation Method. VC Method. First Chicago Method. "
                "Comparable Transactions / Market Multiples. Cost-to-Duplicate Method. "
                "Use method_correctness, evidence_grounding, and financial_reasoning_quality."
            ),
            "citations": [{"ref": 1, "chunk_id": "vc-methods", "path": "startup_research_playbook.md", "heading": "VC Methods", "score": 0.95}],
            "chunks": [{"chunk_id": "vc-methods", "path": "startup_research_playbook.md"}],
            "stage": stage,
            "company": company,
        }

    monkeypatch.setattr(runner, "_load_rag_skill", lambda: None)
    monkeypatch.setattr(runner, "skill_prepare_blueprint_knowledge_rag", fake_prepare_rag)
    monkeypatch.setattr(runner, "skill_public_rag_state", fake_public_rag_state)
    monkeypatch.setattr(runner, "skill_retrieve_knowledge_rag_context", fake_rag_context)

    class FakeW3mBrowserConfig:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    def fake_research_topic(query, browser_config, max_sources=3, observer=None):
        if observer is not None:
            observer({"event": "tool_call_completed", "tool": "w3m", "status": "completed", "target": query})
        return {
            "sources": [
                {
                    "url": f"https://www.crunchbase.com/organization/{runner.slugify(query.split()[0])}",
                    "title": f"Crunchbase profile for {query}",
                    "snippet": "Deterministic public research fixture for VC assistant tests.",
                    "status": "ok",
                }
            ][:max_sources],
            "warnings": [],
            "search_url": f"https://duckduckgo.test/?q={query}",
        }

    monkeypatch.setattr(runner, "_load_w3m_browser_skill", lambda: None)
    monkeypatch.setattr(runner, "W3mBrowserConfig", FakeW3mBrowserConfig)
    monkeypatch.setattr(runner, "research_topic", fake_research_topic)
    monkeypatch.setattr(runner, "browse_url", lambda *args, **kwargs: {"status": "ok"})

    result = runner.run_blueprint(
        inputs={
            "document_folder": str(docs),
            "output_folder": str(outputs),
            "monitoring": {"enabled": True, "poll_interval_seconds": 1, "max_cycles": 1},
        },
        config={
            "llm": {"mode": "live", "require_live": False},
            "backpressure": {"llm": {"max_concurrent_calls": 1, "min_interval_seconds": 0}},
        },
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
            "research_plan.json",
            "agent_tool_trace.json",
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
        assert "Research Gaps And Follow-Ups" in markdown
        assert "- Why:" in markdown
        assert "pre-revenue value proxy based on risk reduction" in markdown
        assert "Assumptions:" in markdown
        research_plan = json.loads((company_dir / "research_plan.json").read_text(encoding="utf-8"))
        assert research_plan["adaptive"] is True
        assert research_plan["lanes"]
        assert research_plan["knowledge_rag"]["status"] == "ready"
        assert research_plan["agentic_research"]["enabled"] is True
        assert research_plan["agentic_research"]["max_iterations_per_agent"] == 1
        assert research_plan["agentic_research"]["max_tool_calls_per_agent"] == 2
        agent_trace = json.loads((company_dir / "agent_tool_trace.json").read_text(encoding="utf-8"))
        assert isinstance(agent_trace, list)
        assert all(item["rag_context"]["status"] == "ready" for item in agent_trace)
        assert all(item["knowledge_refs"] for item in agent_trace)

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
    assert (outputs / "artifact_quality.json").exists()
    assert (outputs / "run_health.json").exists()
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
    assert run_artifact["llm_usage"]["calls"] >= len(run_artifact["actor_review"]["llm_actor_ids"])
    assert run_artifact["action_ledger"]["budget"] == 160
    assert run_artifact["action_ledger"]["used"] >= len(run_artifact["actor_review"]["llm_actor_ids"])
    assert any(action["action_type"] == "financial_tool" for action in run_artifact["action_ledger"]["actions"])
    assert run_artifact["cache_policy"]["fresh_run"] is True
    assert run_artifact["cache_policy"]["force_reprocess"] is False
    assert {item["freshness"] for item in run_artifact["cache_policy"]["companies"]} == {"fresh_or_changed"}
    assert all(report["cache_policy"]["decision"] == "process_company_packet" for report in run_artifact["company_reports"])
    assert run_artifact["artifact_quality"]["passes_required_gate"] is True
    assert run_artifact["artifact_quality"]["status"] in {"passed", "warning"}
    assert run_artifact["artifact_quality"]["company_count"] == 2
    assert {
        company["checks"]["output_files"]["status"]
        for company in run_artifact["artifact_quality"]["companies"]
    } == {"passed"}
    assert all(
        company["checks"]["financial_tool"]["source_count"] >= 1
        for company in run_artifact["artifact_quality"]["companies"]
    )
    artifact_quality_text = json.dumps(run_artifact["artifact_quality"])
    assert "VC Startup Research And Method Playbook" not in artifact_quality_text
    assert "raw_document_text" not in artifact_quality_text
    assert json.loads((outputs / "final_artifact.json").read_text(encoding="utf-8"))["action_ledger"]["budget"] == 160
    assert json.loads((outputs / "action_ledger.json").read_text(encoding="utf-8"))["budget"] == 160
    assert json.loads((outputs / "artifact_quality.json").read_text(encoding="utf-8")) == run_artifact["artifact_quality"]
    run_health = json.loads((outputs / "run_health.json").read_text(encoding="utf-8"))
    assert run_health["status"] in {"healthy", "warning"}
    assert run_health["components"]["artifact_quality"]["passes_required_gate"] is True
    assert run_health["components"]["context_engine"]["actor_review_uses_context_engine"] is True
    assert run_health["components"]["context_engine"]["working_memory_persist_to_redis"] is False
    assert run_health["components"]["public_tools"]["tool_operation_count"] >= 1
    assert run_health["components"]["knowledge_rag"]["status"] == "ready"
    assert run_health["privacy"] == "metadata_only_no_prompts_no_raw_rag_context_no_document_text_no_raw_public_pages"
    run_health_text = json.dumps(run_health)
    assert "VC Startup Research And Method Playbook" not in run_health_text
    assert run_artifact["run_health"]["artifact"] == "run_health.json"
    assert run_artifact["run_health"]["status"] == run_health["status"]
    company_index = json.loads((outputs / "company_index.json").read_text(encoding="utf-8"))
    assert company_index["cache_policy"]["fresh_run"] is True
    assert all(item["cache_policy"]["freshness"] == "fresh_or_changed" for item in company_index["companies"])
    run_summary = (outputs / "run_summary.md").read_text(encoding="utf-8")
    assert "## Cache Policy" in run_summary
    assert "fresh_or_changed" in run_summary
    assert any(item["kind"] == "final_artifact_json" for item in run_artifact["output_files"])
    assert run_artifact["active_knowledge"]["path"] == "knowledge/startup_research_playbook.md"
    assert run_artifact["active_knowledge"]["sha256"]
    assert set(run_artifact["active_knowledge"]["method_memory_hooks"]) == METHOD_IDS
    assert run_artifact["knowledge_rag"]["status"] == "ready"
    assert run_artifact["knowledge_rag"]["index_summary"]["indexed_count"] == 3
    assert fake_llm.calls >= len(run_artifact["actor_review"]["llm_actor_ids"])
    assert {
        actor_id
        for actor_id, finding in run_artifact["actor_findings"].items()
        if finding.get("status") == "not_llm_reviewed"
    } == set(runner.WORKFLOW_STEP_IDS) - set(run_artifact["actor_review"]["llm_actor_ids"])
    trace_path = tmp_path / "vc-unit" / "llm_rag_trace.jsonl"
    assert trace_path.exists()
    assert (outputs / "llm_rag_trace.jsonl").exists()
    trace_text = trace_path.read_text(encoding="utf-8")
    assert (outputs / "llm_rag_trace.jsonl").read_text(encoding="utf-8") == trace_text
    assert "VC Startup Research And Method Playbook" not in trace_text
    assert "observability_operation_started" in trace_text
    assert "observability_operation_completed" in trace_text
    assert any(item["kind"] == "llm_rag_trace_jsonl" for item in run_artifact["output_files"])
    assert any(item["kind"] == "artifact_quality_json" for item in run_artifact["output_files"])
    assert any(item["kind"] == "run_health_json" for item in run_artifact["output_files"])
    observability = run_artifact["observability"]
    assert observability["trace_available"] is True
    assert observability["trace_artifact"] == "llm_rag_trace.jsonl"
    assert observability["record_count"] >= 1
    assert observability["llm_call_count"] >= len(run_artifact["actor_review"]["llm_actor_ids"])
    assert observability["tool_operation_count"] >= 1
    assert observability["privacy"] == "metadata_only_no_prompts_no_raw_rag_context_no_document_text"
    observability_text = json.dumps(observability)
    assert "VC Startup Research And Method Playbook" not in observability_text
    assert "raw_document_text" not in observability_text
    transport_artifact = runner.final_artifact_for_transport(run_artifact)
    assert transport_artifact["transport"]["compacted"] is True
    assert "research_sources" not in transport_artifact
    assert "evidence" not in transport_artifact
    assert "actions" not in transport_artifact["action_ledger"]
    assert transport_artifact["company_reports"]
    assert transport_artifact["observability"]["trace_available"] is True
    prompt_payload = next(prompt["user"] for prompt in fake_llm.prompts if "memory_boundary" in prompt["user"])
    assert "rag_context" in prompt_payload
    assert "citation_count" in prompt_payload
    assert "persistent Redis-backed knowledge index" in prompt_payload
    assert "transient local prompt context" in prompt_payload
    assert "VC Startup Research And Method Playbook" not in prompt_payload
    for stale_term in ("camera", "video", "surveillance", "footage"):
        assert stale_term not in prompt_payload.lower()
    assert (tmp_path / "vc-unit" / "action_ledger.json").exists()

    repeat = runner.run_blueprint(
        inputs={
            "document_folder": str(docs),
            "output_folder": str(outputs),
            "monitoring": {"enabled": True, "poll_interval_seconds": 1, "max_cycles": 1},
        },
        config={
            "llm": {"mode": "fake", "require_live": False},
            "internet_research": {"enabled": False},
            "agentic_research": {"enabled": False},
            "backpressure": {"llm": {"max_concurrent_calls": 1, "min_interval_seconds": 0}},
        },
        runs_root=tmp_path,
        run_id="vc-repeat",
        llm_client=FakeVCLLM(),
    )
    assert {item["status"] for item in repeat["final_artifact"]["company_work_queue"]} == {"unchanged_skipped"}
    assert repeat["final_artifact"]["monitor_state"]["processed_company_count"] == 0
    assert repeat["final_artifact"]["monitor_state"]["skipped_company_count"] == 2
    assert {report["processing_status"] for report in repeat["final_artifact"]["company_reports"]} == {"unchanged_skipped"}
    assert repeat["final_artifact"]["cache_policy"]["fresh_run"] is False
    assert {item["freshness"] for item in repeat["final_artifact"]["cache_policy"]["companies"]} == {"unchanged_cached"}
    assert all(report["cache_policy"]["cache_source"] == "watch_state_and_company_artifacts" for report in repeat["final_artifact"]["company_reports"])

    forced = runner.run_blueprint(
        inputs={
            "document_folder": str(docs),
            "output_folder": str(outputs),
            "force_reprocess": True,
            "monitoring": {"enabled": True, "poll_interval_seconds": 1, "max_cycles": 1},
        },
        config={
            "llm": {"mode": "fake", "require_live": False},
            "knowledge_rag": {"enabled": False, "required": False},
            "internet_research": {"enabled": False},
            "agentic_research": {"enabled": False},
            "backpressure": {"llm": {"max_concurrent_calls": 1, "min_interval_seconds": 0}},
        },
        runs_root=tmp_path,
        run_id="vc-force",
        llm_client=FakeVCLLM(),
    )
    assert {item["status"] for item in forced["final_artifact"]["company_work_queue"]} == {"new_or_changed"}
    assert forced["final_artifact"]["cache_policy"]["force_reprocess"] is True
    assert forced["final_artifact"]["cache_policy"]["fresh_run"] is True
    assert {item["freshness"] for item in forced["final_artifact"]["cache_policy"]["companies"]} == {"forced_reprocess"}
    assert {report["processing_status"] for report in forced["final_artifact"]["company_reports"]} == {"new_or_changed"}
    assert {report["cached_from_previous_run"] for report in forced["final_artifact"]["company_reports"]} == {False}


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
        config={
            "llm": {"mode": "fake", "require_live": False},
            "knowledge_rag": {"enabled": False, "required": False},
            "agentic_research": {"enabled": False},
            "internet_research": {"enabled": False},
            "backpressure": {"llm": {"max_concurrent_calls": 1, "min_interval_seconds": 0}},
        },
        runs_root=tmp_path,
        run_id="vc-llm-fails",
        llm_client=failing_llm,
    )

    artifact = result["final_artifact"]
    assert result["status"] == "completed"
    assert (outputs / "alpha-ai" / "analysis.md").exists()
    assert (outputs / "company_index.json").exists()
    assert artifact["actor_review_warnings"][0]["status"] == "actor_review_unavailable"
    assert artifact["actor_review_warnings"][0]["affected_actor_count"] == len(artifact["actor_review"]["llm_actor_ids"])
    assert set(artifact["actor_findings"]) == set(runner.WORKFLOW_STEP_IDS)
    assert failing_llm.calls == len(artifact["actor_review"]["llm_actor_ids"])
    assert any(finding.get("status") == "not_llm_reviewed" for finding in artifact["actor_findings"].values())


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
        config={
            "llm": {"mode": "fake", "require_live": False},
            "knowledge_rag": {"enabled": False, "required": False},
            "internet_research": {"enabled": False},
            "agentic_research": {"enabled": False},
            "backpressure": {"llm": {"max_concurrent_calls": 1, "min_interval_seconds": 0}},
        },
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
        config={
            "llm": {"mode": "fake", "require_live": False},
            "knowledge_rag": {"enabled": False, "required": False},
            "internet_research": {"enabled": False},
            "agentic_research": {"enabled": False},
            "backpressure": {"llm": {"max_concurrent_calls": 1, "min_interval_seconds": 0}},
        },
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
        config={
            "llm": {"mode": "fake", "require_live": False},
            "knowledge_rag": {"enabled": False, "required": False},
            "internet_research": {"enabled": False},
            "agentic_research": {"enabled": False},
            "backpressure": {"llm": {"max_concurrent_calls": 1, "min_interval_seconds": 0}},
        },
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


def test_runtime_managed_output_folder_wins_over_default_payload(monkeypatch, tmp_path):
    runner = _load_runner()
    runtime_output = tmp_path / "shared" / "outputs" / "user"
    payload = {"output_folder": "~/Downloads/vc_assistant"}
    resolved_config = {"outputs": {"folder_path": str(runtime_output)}}
    monkeypatch.setenv("MN_JOB_OUTPUT_DIR", str(runtime_output))

    assert runner.resolve_output_folder(payload, resolved_config, inputs={}) == runtime_output


def test_explicit_output_folder_wins_over_runtime_managed_output(monkeypatch, tmp_path):
    runner = _load_runner()
    runtime_output = tmp_path / "shared" / "outputs" / "user"
    explicit_output = tmp_path / "explicit"
    payload = {"output_folder": "~/Downloads/vc_assistant"}
    resolved_config = {"outputs": {"folder_path": str(runtime_output)}}
    monkeypatch.setenv("MN_JOB_OUTPUT_DIR", str(runtime_output))

    assert runner.resolve_output_folder(payload, resolved_config, inputs={"output_folder": str(explicit_output)}) == explicit_output


def test_changed_company_packets_process_in_parallel_with_stable_output_order(tmp_path):
    runner = _load_runner()
    docs = tmp_path / "startup-docs"
    outputs = tmp_path / "reports"
    _write_startup_packets(docs)
    started: set[str] = set()
    lock = threading.Lock()
    two_started = threading.Event()
    original_research = runner.research_company_by_stage

    def fake_research(company, config, run_dir=None, **kwargs):
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
            config={
                "llm": {"mode": "fake", "require_live": False},
                "knowledge_rag": {"enabled": False, "required": False},
                "backpressure": {"llm": {"max_concurrent_calls": 1, "min_interval_seconds": 0}},
                "execution": {"max_company_workers": 2},
                "scoring": {"max_workers": 7},
            },
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
        config={
            "llm": {"mode": "fake", "require_live": False},
            "knowledge_rag": {"enabled": False, "required": False},
            "backpressure": {"llm": {"max_concurrent_calls": 1, "min_interval_seconds": 0}},
            "research_budget": {"default_actions": 1},
        },
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
    assert fake_llm.calls <= 1
