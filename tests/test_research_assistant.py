from __future__ import annotations

import json

from mn_sdk.bundle_io import load_bundle_payloads

from blueprint_modernization_support import (
    ROOT,
    assert_modular_payload,
    assert_registry_handlers_import,
    expanded_manifest,
    run_payload_script,
    source_manifest,
)


EXPECTED_STEPS = [
    "frame_research_problem",
    "build_research_evidence",
    "develop_and_challenge_hypotheses",
    "verify_and_publish_research_packet",
]


def test_research_default_request_matches_the_bundled_sample_and_staging_contract():
    blueprint = ROOT / "research_assistant"
    config = json.loads((blueprint / "config" / "default.json").read_text())
    sample_request = json.loads(
        (blueprint / "examples" / "sample_inputs" / "sample_research_request.json").read_text()
    )
    default_inputs = config["inputs"]["payload"]

    for key in (
        "research_goal",
        "research_domain",
        "research_question",
        "scope",
        "success_criteria",
        "constraints",
    ):
        assert default_inputs[key] == sample_request[key]

    assert [item["statement"] for item in default_inputs["seed_hypotheses"]] == sample_request["seed_hypotheses"]
    assert all(item.get("prediction") for item in default_inputs["seed_hypotheses"])
    assert all(item.get("experiment", {}).get("procedure") for item in default_inputs["seed_hypotheses"])

    assert default_inputs["input_folder"] == "@/examples/sample_inputs"
    assert config["state"]["input_folder"] == "@/examples/sample_inputs"
    assert config["local_inputs"]["folders"] == [
        {
            "config_path": "inputs.payload.input_folder",
            "payload_path": "runtime/mn_local_inputs/research_assistant_documents",
            "runtime_path": "mn_local_inputs/research_assistant_documents",
            "allowed_extensions": [
                ".pdf",
                ".png",
                ".jpg",
                ".jpeg",
                ".tif",
                ".tiff",
                ".bmp",
                ".webp",
                ".txt",
                ".json",
                ".csv",
                ".md",
            ],
            "linked_config_paths": [
                "inputs.payload.input_folder",
                "state.input_folder",
            ],
        }
    ]


def test_research_manifest_has_one_isolated_autonomous_specialist():
    source = source_manifest("research_assistant")
    expanded = expanded_manifest("research_assistant")
    assert source["llm"]["require_live"] is True
    assert source["llm"]["context_size"] == 8192
    assert source["llm"]["parameter_count_b"] == 31.58
    assert source["llm"]["quantization"] == "MOSTLY_Q4_K_M"
    assert source["llm"]["model"] == "default"
    assert source["llm"]["provider"] == "docker_model_runner"
    assert source["llm"]["configs"]["primary"]["timeout_seconds"] == 180
    assert source["llm"]["configs"]["primary"]["max_tokens"] == 4096
    assert source["llm"]["structured_output_options"] == {
        "chat_template_kwargs": {"enable_thinking": False}
    }
    assert "runtime" not in source
    assert source["requirements"]["gpu"] == {
        "enforcement": "hard",
        "memory_operator": ">=",
        "min_count": 1,
        "min_memory_mb": 49152,
    }
    assert "vendor" not in source["requirements"]["gpu"]
    assert [step["id"] for step in source["workflow"]["steps"]] == EXPECTED_STEPS
    autonomous_workers = [
        node
        for node in expanded["agents"]["nodes"]
        if node["node_id"] == "develop_and_challenge_hypotheses__autonomous_researcher"
    ]
    assert [node["node_id"] for node in autonomous_workers] == [
        "develop_and_challenge_hypotheses__autonomous_researcher"
    ]
    assert autonomous_workers[0]["config"]["runner_module"] == "MirrorNeuron.Runner.DockerWorker"
    assert autonomous_workers[0]["config"]["docker_worker_image"] == "docker_worker"
    assert autonomous_workers[0]["config"]["workdir"] == "/mn/job/runtime"
    assert not any(
        (node.get("config") or {}).get("runner_module") == "MirrorNeuron.Runner.OpenShell"
        for node in expanded["agents"]["nodes"]
    )

    source_node = next(
        node
        for node in expanded["agents"]["nodes"]
        if node["node_id"] == "frame_research_problem__start"
    )
    assert set(source_node["config"]["fields"]) == set(source["contracts"]["inputs"])


def test_research_workers_ship_build_contexts_and_domain_handlers():
    blueprint = ROOT / "research_assistant"
    expanded = expanded_manifest("research_assistant")
    executable_nodes = [
        node
        for node in expanded["agents"]["nodes"]
        if (node.get("config") or {}).get("runner_module") == "MirrorNeuron.Runner.DockerWorker"
    ]
    docker_workers = [
        node
        for node in executable_nodes
        if node["config"]["runner_module"] == "MirrorNeuron.Runner.DockerWorker"
    ]

    assert docker_workers
    assert {
        node["config"]["docker_worker_image"]
        for node in docker_workers
    } == {"docker_worker"}
    assert all(
        {"source": "domain", "target": "domain"}
        in node["config"]["upload_paths"]
        for node in executable_nodes
    )
    assert all(
        {
            "source": "examples/sample_inputs",
            "target": "research_assistant/examples/sample_inputs",
        }
        in node["config"]["upload_paths"]
        for node in executable_nodes
    )

    payloads = load_bundle_payloads(blueprint)
    assert "docker_worker/Dockerfile" in payloads
    assert not any(path.startswith("openshell_worker/") for path in payloads)
    assert "openshell-policy.yaml" not in payloads


def test_research_payload_is_modular_and_handlers_resolve():
    assert_modular_payload("research_assistant")
    assert_registry_handlers_import("research_assistant")


def test_research_structured_llm_preserves_runtime_route_and_disables_hidden_thinking():
    result = run_payload_script(
        "research_assistant",
        """
import json
from domain import llm_services

class RuntimeSelectedClient:
    provider = "litellm"
    model = "default"
    api_base = "http://runtime-selected.example/v1"
    api_key = "not-needed"
    backend = "llama.cpp"
    context_size = 8192
    timeout_seconds = 180
    max_tokens = 4096
    num_retries = 2
    retry_backoff_seconds = 1.0
    strict = False

captured = []
def request(purpose, model, path, payload, **kwargs):
    captured.append({
        "purpose": purpose,
        "model": model,
        "path": path,
        "payload": payload,
        "provider": kwargs["provider"],
        "api_base": kwargs["api_base"],
    })
    return {
        "choices": [{"message": {"content": '{"finding":"grounded"}'}}],
        "usage": {"prompt_tokens": 12, "completion_tokens": 7, "total_tokens": 19},
    }

llm_services.runtime_model_json_request = request
client = llm_services.StructuredResearchLlmClient(
    RuntimeSelectedClient(),
    {"chat_template_kwargs": {"enable_thinking": False}},
)
response = client.generate_json(
    system_prompt="Analyze supplied evidence.",
    user_prompt='{"source_ref":"SRC-1"}',
    fallback={"finding": "fallback"},
)
print(json.dumps({
    "response": response,
    "request": captured[0],
    "calls": client.calls,
    "fallback_calls": client.fallback_calls,
    "usage": client.last_usage,
}))
""",
    )
    assert result["response"]["finding"] == "grounded"
    assert result["response"]["provider"] == "litellm"
    assert result["response"]["model"] == "default"
    assert result["request"]["model"] == "default"
    assert result["request"]["provider"] == "litellm"
    assert result["request"]["api_base"] == "http://runtime-selected.example/v1"
    assert result["request"]["payload"]["chat_template_kwargs"] == {
        "enable_thinking": False
    }
    assert result["request"]["payload"]["response_format"] == {
        "type": "json_object"
    }
    assert result["calls"] == 1
    assert result["fallback_calls"] == 0
    assert result["usage"]["provider_response_count"] == 1


def test_research_assistant_normalizes_unified_browser_results_as_evidence():
    result = run_payload_script(
        "research_assistant",
        """
import json
from domain import evidence

class BrowserConfig:
    def __init__(self, **values):
        self.values = values

calls = []

def browse(url, config=None, depth=None, output_format=None):
    return {"status": "ok", "final_url": url, "text": "unused"}

def research_topic(query, config=None, depth=None, max_sources=None, output_format=None):
    calls.append({"depth": depth, "output_format": output_format})
    return {
        "sources": [{
            "status": "ok",
            "final_url": "https://example.com/research",
            "title": "Public research",
            "text": "Source-grounded public evidence",
        }],
        "warnings": [],
    }

evidence._load_web_browser_skill = lambda: (BrowserConfig, browse, research_topic)
sources, warnings = evidence.research_public_sources(
    ["robotics simulation reproducibility evidence"],
    {"internet_research": {"enabled": True}},
)
print(json.dumps({
    "statuses": [item["status"] for item in sources],
    "skills": [item["skill"] for item in sources],
    "urls": [item["url"] for item in sources],
    "calls": calls,
    "warnings": warnings,
}))
""",
    )
    assert result == {
        "statuses": ["observed"],
        "skills": ["web_browser_skill"],
        "urls": ["https://example.com/research"],
        "calls": [{"depth": "standard", "output_format": "plain_text"}],
        "warnings": [],
    }


def test_research_assistant_preserves_configured_inputs_and_accepts_ocr_records(tmp_path):
    result = run_payload_script(
        "research_assistant",
        f"""
import json
from pathlib import Path
from domain import inputs as input_module
from domain.state import _inputs

configured = {{
    "research_goal": "Evaluate robotics simulation infrastructure",
    "research_domain": "robotics",
    "constraints": {{"review_only": True}},
    "seed_hypotheses": [{{
        "statement": "Pinned environments reduce setup time.",
        "prediction": "Median setup time falls by at least 20%.",
    }}],
}}
resolved = _inputs({{
    "config": {{"inputs": {{"payload": configured}}}},
    "payload": {{"research_goal": "", "research_domain": "", "constraints": {{}}}},
}})
overridden = _inputs({{
    "config": {{"inputs": {{"payload": configured}}}},
    "payload": {{"research_goal": "Compare simulator reproducibility"}},
}})

class Record:
    def to_dict(self):
        return {{
            "text": "Extracted roadmap evidence",
            "extraction_method": "embedded_text",
            "warnings": [],
        }}

folder = Path({str(tmp_path)!r}) / "inputs"
folder.mkdir()
(folder / "roadmap.pdf").write_bytes(b"sample")
input_module.extract_document = lambda **_kwargs: Record()
documents, warnings = input_module.load_input_documents(folder, {{}})
print(json.dumps({{
    "resolved": resolved,
    "overridden_goal": overridden["research_goal"],
    "document_text": documents[0]["text"],
    "document_method": documents[0]["extraction_method"],
    "structured_seed": resolved["seed_hypotheses"][0],
    "warnings": warnings,
}}))
""",
    )
    assert result["resolved"]["research_goal"] == "Evaluate robotics simulation infrastructure"
    assert result["resolved"]["research_domain"] == "robotics"
    assert result["resolved"]["constraints"] == {"review_only": True}
    assert result["overridden_goal"] == "Compare simulator reproducibility"
    assert result["document_text"] == "Extracted roadmap evidence"
    assert result["document_method"] == "embedded_text"
    assert result["structured_seed"]["statement"] == "Pinned environments reduce setup time."
    assert result["structured_seed"]["prediction"] == "Median setup time falls by at least 20%."
    assert result["warnings"] == []


def test_research_assistant_normalizes_structured_rag_citations():
    result = run_payload_script(
        "research_assistant",
        """
import json
from domain import knowledge

knowledge.build_rag_context = lambda *_args, **_kwargs: {
    "context": "retrieved context",
    "citations": [
        {"path": "knowledge/methods.md", "chunk_id": "chunk-1"},
        {"source_ref": "local:notes.md", "chunk_id": "chunk-2"},
    ],
    "chunks": [{"chunk_id": "chunk-1"}],
    "backend": "milvus_lite",
    "embedding_model": "test-embedding",
}
result = knowledge.retrieve_research_rag_context(
    "test query",
    {"status": "ready", "_rag_config": object()},
    {"content": "", "title": "Knowledge"},
    [{"source_ref": "local:notes.md", "name": "notes.md", "text": "notes"}],
)
print(json.dumps(result))
""",
    )
    assert result["citations"] == ["knowledge/methods.md", "local:notes.md"]
    assert result["backend"] == "milvus_lite"


def test_research_assistant_feeds_tool_observations_back_into_final_synthesis(tmp_path):
    result = run_payload_script(
        "research_assistant",
        f"""
import json
from pathlib import Path
from domain.autonomous import run_autonomous_research

class LLM:
    def __init__(self):
        self.calls = 0
        self.prompts = {{}}

    def generate_json(self, system_prompt, user_prompt, fallback):
        self.calls += 1
        phase = system_prompt.split("Research phase: ", 1)[1].split(".", 1)[0]
        self.prompts[phase] = user_prompt
        if phase == "source_analysis":
            return {{
                "source_assessments": [{{
                    "source_ref": "local:notes.md",
                    "relevant_observations": ["Container onboarding evidence is available."],
                    "limitations": ["Single local source."],
                    "use_in_synthesis": "candidate_context_only",
                }}],
                "cross_source_agreements": [],
                "cross_source_tensions": [],
                "evidence_gaps": ["Matched setup-time measurements"],
            }}
        if phase == "question_decomposition":
            return {{
                "subquestions": [{{
                    "subquestion_id": "Q1",
                    "question": "Do pinned containers reduce setup time?",
                    "decision_relevance": "Determines whether to run a matched trial.",
                    "evidence_needed": ["local:notes.md"],
                }}],
                "key_definitions": [],
                "assumptions_to_test": [],
                "stop_conditions": [],
            }}
        if phase == "competing_hypothesis_generation":
            return {{
                "recommended_action": "review_research_packet",
                "confidence": "medium",
                "rationale": "Bounded test synthesis",
                "candidate_hypotheses": [{{
                    "statement": "Initial candidate",
                    "prediction": "Matched trials reduce median setup time by at least 20%.",
                    "evidence_support": ["local:notes.md"],
                    "counterargument": "Documentation quality could explain the difference.",
                    "disconfirming_observation": "The reduction is below 20% after matching experience.",
                }}],
            }}
        if phase == "gap_and_probe_planning":
            return {{
                "tool_requests": [{{"tool": "document_extract", "arguments": {{"query": "container"}}}}],
                "generated_python": "",
            }}
        if phase == "evidence_and_probe_revision":
            return {{
                "recommended_action": "review_research_packet",
                "confidence": "medium",
                "rationale": "Revised after checking the requested document passage.",
                "candidate_hypotheses": [{{
                    "statement": "Revised after document observation",
                    "prediction": "Matched trials reduce median setup time by at least 20%.",
                    "evidence_support": ["local:notes.md"],
                    "counterargument": "Documentation quality could explain the difference.",
                    "disconfirming_observation": "The reduction is below 20% after matching experience.",
                }}],
            }}
        if phase == "experiment_design":
            return {{"experiments": [{{
                "hypothesis_id": "H1",
                "objective": "Test the setup-time prediction.",
                "unit_of_analysis": "One independent developer setup.",
                "baseline": "Unpinned environment.",
                "intervention": "Pinned container.",
                "primary_outcome": "Median setup time in minutes.",
                "measurements": ["elapsed minutes", "experience level"],
                "procedure": ["Pre-register", "Match users", "Run baseline", "Run intervention"],
                "decision_rule": "Advance only for at least 20% reduction.",
                "analysis_plan": "Compare medians and dispersion.",
                "stop_conditions": ["Measurement integrity fails."],
            }}]}}
        if phase == "meta_review_and_ranking":
            return {{
                "ranking": [{{
                    "hypothesis_id": "H1",
                    "rank": 1,
                    "priority_score": 85,
                    "rationale": "Traceable and falsifiable.",
                }}],
                "recommended_action": "review_research_packet",
                "confidence": "medium",
                "rationale": "The candidate is ready for review-only testing.",
                "unresolved_gaps": ["No matched trial has been run."],
            }}
        if phase == "executive_synthesis":
            return {{
                "executive_summary": "Pinned containers merit a matched, review-only onboarding trial.",
                "key_findings": ["The local source supports testing, not validation."],
                "decision_implications": ["Run the matched setup-time protocol before adoption."],
                "caveats": ["No matched trial has been run."],
            }}
        return dict(fallback)

llm = LLM()
documents = [{{
    "source_ref": "local:notes.md",
    "name": "notes.md",
    "status": "extracted",
    "text": "Container onboarding evidence and setup-time protocol.",
}}]
recommendation, autonomous, warnings = run_autonomous_research(
    llm,
    {{"research_goal": "Improve onboarding", "constraints": {{"review_only": True}}}},
    {{"source_refs": ["local:notes.md"], "usable_evidence_present": True}},
    {{"context": "local methods"}},
    {{"recommended_action": "review_research_packet", "confidence": "medium", "rationale": "review"}},
    {{
        "execution": {{"quick_test": True}},
        "agentic_research": {{
            "allowed_tools": ["document_extract"],
            "max_total_tool_calls": 3,
            "allow_generated_code": False,
            "generated_code": {{"workspace": "generated", "timeout_seconds": 2, "max_output_chars": 2000, "max_memory_mb": 64}},
        }},
    }},
    documents,
    [],
    workspace=Path({str(tmp_path)!r}),
)
print(json.dumps({{
    "calls": llm.calls,
    "source_prompt_has_document": "Container onboarding evidence" in llm.prompts["source_analysis"],
    "revision_prompt_has_observation": "tool_observations" in llm.prompts["evidence_and_probe_revision"] and "Container onboarding evidence" in llm.prompts["evidence_and_probe_revision"],
    "phases": [item["phase"] for item in autonomous["research_phase_trace"]],
    "statement": recommendation["candidate_hypotheses"][0]["statement"],
    "synthesis_passes": autonomous["synthesis_passes"],
    "tool_status": autonomous["tool_observations"][0]["status"],
    "warnings": warnings,
}}))
""",
    )
    assert result == {
        "calls": 9,
        "source_prompt_has_document": True,
        "revision_prompt_has_observation": True,
        "phases": [
            "source_analysis",
            "question_decomposition",
            "competing_hypothesis_generation",
            "adversarial_review_H1",
            "gap_and_probe_planning",
            "evidence_and_probe_revision",
            "experiment_design",
            "meta_review_and_ranking",
            "executive_synthesis",
        ],
        "statement": "Revised after document observation",
        "synthesis_passes": 9,
        "tool_status": "completed",
        "warnings": [],
    }


def test_research_sample_audits_falsifiable_hypotheses(tmp_path):
    result = run_payload_script(
        "research_assistant",
        f"""
import json
from pathlib import Path
from domain.composition import run_blueprint

root = Path({str((ROOT / 'research_assistant').resolve())!r})
out = Path({str(tmp_path)!r}) / "output"
run = run_blueprint(
    inputs={{"input_folder": str(root / "examples" / "sample_inputs"), "output_folder": str(out)}},
    config={{"execution": {{"quick_test": True}}}},
    runs_root=out / "runs",
    run_id="research-quality",
)
artifact = run["final_artifact"]
hypothesis = artifact["hypothesis_ledger"][0]
second_hypothesis = artifact["hypothesis_ledger"][1]
experiment = artifact["experiment_concepts"][0]
dataset_profile = next(item for item in artifact["evidence"]["deterministic"]["document_profiles"] if item.get("suffix") == ".csv")
source_refs = set(artifact["source_refs"])
brief = (out / "research_brief.md").read_text()
serialized_artifact = json.dumps(artifact)
print(json.dumps({{
    "run_status": run["status"],
    "packet_status": artifact["status"],
    "audit_status": artifact["packet_audit"]["status"],
    "all_checks_pass": all(item["passed"] for item in artifact["packet_audit"]["checks"]),
    "has_prediction": bool(hypothesis["prediction"]),
    "has_counterargument": bool(hypothesis["counterargument"]),
    "has_disconfirmation": bool(hypothesis["disconfirming_observation"]),
    "sample_goal_is_robotics": "robotics simulation infrastructure" in artifact["research_goal"].lower(),
    "sample_hypothesis_is_specific": "ROS 2" in hypothesis["statement"] and "25%" in hypothesis["prediction"],
    "hypothesis_refs_are_valid": set(hypothesis["evidence_support"]) <= source_refs,
    "hypothesis_refs_are_specific": "local:research_notes.md" in hypothesis["evidence_support"] and "local:baseline_measurements.csv" not in hypothesis["evidence_support"],
    "baseline_supports_measurement_hypothesis": "local:baseline_measurements.csv" in second_hypothesis["evidence_support"],
    "experiment_is_complete": len(experiment["procedure"]) >= 5 and "elapsed minutes" in experiment["primary_outcome"] and bool(experiment["stop_conditions"]),
    "generation_mode": artifact["generation_provenance"]["mode"],
    "model_procedure_calls": artifact["generation_provenance"]["llm_calls"],
    "research_phase_count": artifact["generation_provenance"]["research_phase_count"],
    "dataset_is_profiled": dataset_profile["row_count"] == 12 and "episode_success_rate" in dataset_profile["numeric_summary"],
    "internal_paths_redacted": all("path" not in item for item in artifact["evidence"]["documents"]) and "/Users/" not in serialized_artifact and "/root/" not in serialized_artifact,
    "brief_has_procedure": "## Generation Notes" in brief and "## Evidence Reviewed" in brief and "## Dataset Profiles" in brief and "## Research Decomposition" in brief and "## Source Analysis" in brief and "#### Independent Adversarial Review" in brief and "## Specialist Reviews" in brief and "#### Test Procedure" in brief and "`episode_success_rate`" in brief,
    "quality_checks_pass": all(item["passed"] for item in artifact["artifact_quality"]["quality_checks"]),
    "rag_status": artifact["knowledge_rag"]["status"],
    "trace_count": len(artifact["autonomous_research"]["session"]["trace"]),
    "run_artifact_exists": (out / "runs" / "research-quality" / "final_artifact.json").exists(),
    "brief_exists": (out / "research_brief.md").exists(),
}}))
""",
    )
    assert result == {
        "run_status": "completed",
        "packet_status": "review_ready",
        "audit_status": "passed",
        "all_checks_pass": True,
        "has_prediction": True,
        "has_counterargument": True,
        "has_disconfirmation": True,
        "sample_goal_is_robotics": True,
        "sample_hypothesis_is_specific": True,
        "hypothesis_refs_are_valid": True,
        "hypothesis_refs_are_specific": True,
        "baseline_supports_measurement_hypothesis": True,
        "experiment_is_complete": True,
        "generation_mode": "deterministic_fallback",
        "model_procedure_calls": 16,
        "research_phase_count": 11,
        "dataset_is_profiled": True,
        "internal_paths_redacted": True,
        "brief_has_procedure": True,
        "quality_checks_pass": True,
        "rag_status": "skipped_quick_test",
        "trace_count": 3,
        "run_artifact_exists": True,
        "brief_exists": True,
    }
