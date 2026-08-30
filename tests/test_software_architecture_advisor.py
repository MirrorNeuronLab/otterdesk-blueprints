from __future__ import annotations

import json
from pathlib import Path

from blueprint_modernization_support import ROOT, assert_modular_payload, assert_registry_handlers_import, run_payload_script, source_manifest
from mn_sdk import expand_manifest_source
from mn_sdk.submission_preparation import (
    prepare_manifest_for_submission,
    stage_skill_dependency_payloads_for_manifest,
    stage_upload_path_payloads_for_manifest,
)


def test_software_architecture_advisor_is_air_gapped_and_requires_a_large_local_model():
    manifest = source_manifest("software_architecture_advisor")
    config = json.loads((ROOT / "software_architecture_advisor" / "config" / "default.json").read_text())

    assert manifest["air-gapped"] is True
    assert manifest["requirements"]["memory"]["min_gb"] == 48
    assert manifest["requirements"]["network"]["egress"] == "forbidden"
    assert config["source_acquisition"]["mode"] == "platform_pre_staged_github_snapshot"
    assert config["source_acquisition"]["staging_wait_seconds"] == 180
    assert config["source_acquisition"]["staging_poll_interval_seconds"] == 2
    assert config["outputs"]["folder_path"] == "~/Downloads/software_architecture_advisor"
    assert config["local_model"]["preinstalled_only"] is True
    assert manifest["llm"]["model"] == "default"
    assert manifest["workflow"]["workflow_id"] == "software_architecture_advisor_v3"
    assert manifest["workflow"]["execution"]["strategy"] == "serial"
    assert config["llm"]["require_live"] is True
    assert config["llm"]["strict_json"] is True
    assert config["llm"]["context_size"] >= 32768
    assert config["research_budget"]["default_actions"] == 8
    assert config["backpressure"]["llm"]["max_concurrent_calls"] == 1
    for profile in config["llm"]["configs"].values():
        assert "runtime_model" not in profile
        assert profile["model"] == "default"
        assert profile["timeout_seconds"] == 600
        assert profile["num_retries"] == 2
        assert 5000 <= profile["max_tokens"] <= 7000
    assert config["local_model"]["minimum_host_memory_gb"] == 48
    assert config["local_inputs"] == {
        "folders": [
            {
                "config_path": "inputs.payload.input_folder",
                "payload_path": "mn_local_inputs/software_architecture_advisor_source",
                "runtime_path": "mn_local_inputs/software_architecture_advisor_source",
                "allowed_extensions": [".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".go", ".rs", ".c", ".h", ".cpp", ".hpp", ".cs", ".rb", ".php", ".swift", ".kt", ".kts", ".md", ".txt", ".json", ".yaml", ".yml", ".toml", ".xml", ".gradle", ".properties", ".lock", ".sh", ".sql", ".tf", ".hcl", ".graphql"],
                "allowed_file_names": ["Dockerfile", "Makefile", "Procfile", "Jenkinsfile", "Gemfile", "Rakefile", "go.mod", "go.sum", "Cargo.toml", "Cargo.lock"],
                "linked_config_paths": ["inputs.payload.input_folder"],
            }
        ]
    }


def test_software_architecture_advisor_keeps_its_default_github_reference_in_sample_inputs():
    blueprint = ROOT / "software_architecture_advisor"
    config = json.loads((blueprint / "config" / "default.json").read_text())
    reference = blueprint / "examples" / "sample_inputs" / "ARCHMIND_GITHUB_REPOSITORY.txt"

    assert reference.read_text().strip() == "https://github.com/homerquan/Archmind"
    assert config["inputs"]["payload"]["input_folder"] == ""
    assert config["source_acquisition"]["default_repository_reference_file"] == "@/examples/sample_inputs/ARCHMIND_GITHUB_REPOSITORY.txt"


def test_software_architecture_advisor_payload_is_modular_and_handlers_resolve():
    assert_modular_payload("software_architecture_advisor")
    assert_registry_handlers_import("software_architecture_advisor")


def test_software_architecture_advisor_declares_explicit_draft_audit_publish_phases():
    manifest = source_manifest("software_architecture_advisor")
    steps = manifest["workflow"]["steps"]

    assert [item["id"] for item in steps] == [
        "resolve_software_source",
        "map_architecture_evidence",
        "assess_architecture_improvements",
        "author_implementation_prompts",
        "draft_architecture_report",
        "audit_architecture_advice",
        "publish_architecture_advice",
    ]
    assert steps[-3]["needs"] == ["author_implementation_prompts"]
    assert steps[-2]["needs"] == ["draft_architecture_report"]
    assert steps[-1]["needs"] == ["audit_architecture_advice"]
    assert manifest["agents"]["registry"]["architecture_artifact_publisher"]["handler"] == "agents.architecture_artifact_publisher"


def test_software_architecture_advisor_includes_a_docker_worker_build_context():
    payloads = ROOT / "software_architecture_advisor" / "payloads"
    dockerfile = ROOT / "software_architecture_advisor" / "payloads" / "docker_worker" / "Dockerfile"

    text = dockerfile.read_text()
    assert "COPY requirements.txt" in text
    assert "COPY local-requirements.txt" in text
    assert "mirrorneuron: skill-dependencies" in text
    assert (payloads / "prompts" / "architecture-review-system.md").is_file()
    assert (payloads / "knowledge" / "static-analysis-limits.md").is_file()

    manifest = expand_manifest_source(source_manifest("software_architecture_advisor"), root_dir=ROOT / "software_architecture_advisor")
    workers = [
        node for node in manifest["agents"]["nodes"]
        if (node.get("config") or {}).get("runner_module") == "MirrorNeuron.Runner.DockerWorker"
    ]
    assert workers
    payload_upload_sources = {
        str(item["source"])
        for node in workers
        for item in node["config"].get("upload_paths") or []
        if isinstance(item, dict) and item.get("source") in {
            "agents", "domain", "examples", "knowledge", "prompts", "runtime", "steps"
        }
    }
    assert payload_upload_sources == {
        "agents", "domain", "examples", "knowledge", "prompts", "runtime", "steps"
    }
    assert all(
        ((ROOT / "software_architecture_advisor" if source == "examples" else payloads) / source).is_dir()
        for source in payload_upload_sources
    )


def test_software_architecture_advisor_stages_its_owned_graph_skill_into_the_docker_image(monkeypatch):
    blueprint = ROOT / "software_architecture_advisor"
    # Exercise the same development-localization path used by `mn blueprint
    # run`. Payload-owned private skills must survive it and reach DockerWorker.
    monkeypatch.setenv("MN_USE_LOCAL_SKILLS", "1")
    prepared = prepare_manifest_for_submission(
        blueprint,
        source_manifest("software_architecture_advisor"),
    )
    staged: dict[str, bytes] = {}
    stage_skill_dependency_payloads_for_manifest(prepared, staged, bundle_dir=blueprint)

    local_requirements = staged["docker_worker/local-requirements.txt"].decode()
    assert "/tmp/mn-skill-runtime/local/software_architecture_graph_skill" in local_requirements
    assert (
        "docker_worker/__mn_skill_dependencies/local/software_architecture_graph_skill/pyproject.toml"
        in staged
    )


def test_software_architecture_advisor_stages_the_bundled_default_source_for_workers():
    blueprint = ROOT / "software_architecture_advisor"
    prepared = prepare_manifest_for_submission(
        blueprint,
        source_manifest("software_architecture_advisor"),
    )
    staged: dict[str, bytes] = {}

    stage_upload_path_payloads_for_manifest(prepared, staged, bundle_dir=blueprint)

    assert "examples/sample_inputs/mini_order_service/api.py" in staged


def test_software_architecture_advisor_writes_copy_ready_prompts_without_changing_source(tmp_path: Path):
    result = run_payload_script(
        "software_architecture_advisor",
        f"""
import hashlib
import json
from pathlib import Path
from domain.composition import run_blueprint

root = Path({str((ROOT / 'software_architecture_advisor').resolve())!r})
source = root / 'examples' / 'sample_inputs'
before = {{str(path.relative_to(source)): hashlib.sha256(path.read_bytes()).hexdigest() for path in source.rglob('*') if path.is_file()}}
output = Path({str(tmp_path)!r}) / 'output'
result = run_blueprint(
    inputs={{'input_folder': str(source), 'output_folder': str(output)}},
    config={{'analysis': {{'large_module_line_threshold': 2, 'max_files': 100}}, 'llm': {{'mode': 'fake'}}}},
    runs_root=output / 'runs',
    run_id='architecture-advisor-test',
)
after = {{str(path.relative_to(source)): hashlib.sha256(path.read_bytes()).hexdigest() for path in source.rglob('*') if path.is_file()}}
artifact = result['final_artifact']
print(json.dumps({{
    'status': result['status'],
    'cycle_count': artifact['evidence']['metrics']['cycle_count'],
    'source_unchanged': before == after,
    'prompt_count': len(artifact['improvement_prompts']),
    'fact_count_positive': artifact['evidence']['fact_database']['fact_count'] > 0,
    'symbol_count_positive': artifact['evidence']['metrics']['symbol_count'] > 0,
    'source_bodies_not_persisted': all('text' not in item for item in artifact['evidence']['inventory']['files']),
    'high_findings_triangulated': all(item['severity'] not in ('high', 'critical') or len(item['evidence']['signal_types']) >= 2 for item in artifact['evidence']['findings']),
    'counter_evidence_recorded': all(item['counter_evidence_considered'] for item in artifact['evidence']['findings']),
    'options_recorded': all(len(item['alternative_options']) >= 2 for item in artifact['evidence']['findings']),
    'prompt_file': (output / 'improvement_prompts.md').is_file(),
    'report_file': (output / 'architecture_report.md').is_file(),
    'fact_file': (output / 'evidence' / 'architecture_facts.json').is_file(),
    'repository_map': (output / 'architecture-report' / '01-repository-map.md').is_file(),
    'standalone_prompt_count': len(list((output / 'codex-prompts').glob('*.md'))),
    'schema_version': artifact['schema_version'],
    'llm_stage_count': artifact['llm_analysis']['completed_stage_count'],
    'llm_stage_order': list(artifact['llm_analysis']['stages']),
    'llm_analysis_file': (output / 'evidence' / 'llm_analysis.json').is_file(),
    'llm_trace_file': (output / 'llm_trace.jsonl').is_file(),
    'network': artifact['review_boundary']['network'],
}}))
""",
    )
    assert result == {
        "status": "completed",
        "cycle_count": 1,
        "source_unchanged": True,
        "prompt_count": 1,
        "fact_count_positive": True,
        "symbol_count_positive": True,
        "source_bodies_not_persisted": True,
        "high_findings_triangulated": True,
        "counter_evidence_recorded": True,
        "options_recorded": True,
        "prompt_file": True,
        "report_file": True,
        "fact_file": True,
        "repository_map": True,
        "standalone_prompt_count": 1,
        "schema_version": "mn.blueprint.software_architecture_advisor.v3",
        "llm_stage_count": 8,
        "llm_stage_order": [
            "source_intake", "component_mapping", "cross_cutting_mapping",
            "finding_synthesis", "adversarial_review", "prompt_authoring",
            "report_synthesis", "final_audit",
        ],
        "llm_analysis_file": True,
        "llm_trace_file": True,
        "network": "forbidden",
    }


def test_software_architecture_advisor_runs_eight_live_scripted_passes_and_uses_their_outputs(tmp_path: Path):
    result = run_payload_script(
        "software_architecture_advisor",
        f'''
import json
from pathlib import Path
from domain.composition import run_blueprint

class ScriptedLiveLLM:
    provider = "scripted-live"
    model = "scripted-large-local"
    def __init__(self):
        self.calls = self.fallback_calls = 0
        self.input_tokens = self.output_tokens = self.total_tokens = self.estimated_tokens = 0
        self.last_usage = {{}}
        self.stages = []
        self.packet_kinds = []
    def generate_json(self, *, system_prompt, user_prompt, fallback, validator=None, validation_retries=0):
        payload = json.loads(user_prompt)
        stage = payload["stage"]
        assert payload["required_output_contract"]["required_fields"]
        assert payload["structured_output_rules"]
        assert "required_output_shape" not in payload
        self.stages.append(stage)
        context = payload["bounded_context"]
        self.packet_kinds.append(context.get("packet_kind"))
        value = json.loads(json.dumps(fallback))
        if stage == "source_intake":
            value["summary"] = "Scripted intake identified repository-specific investigation priorities."
        elif stage == "component_mapping":
            value["summary"] = "Scripted component reconstruction explains repository ownership."
            value["components"][0]["responsibility"] = "Scripted component responsibility grounded in supplied paths."
        elif stage == "cross_cutting_mapping":
            value["summary"] = "Scripted cross-cutting analysis preserves runtime uncertainty."
        elif stage == "finding_synthesis":
            for item in value["deterministic_finding_rationales"]:
                item["rationale"] = "Scripted rationale grounded in the cited architecture facts."
            facts = context["facts"]
            by_path = {{}}
            for fact in facts:
                for path in fact.get("paths") or []:
                    by_path.setdefault(path, []).append(fact)
            selected_path = next((path for path, items in by_path.items() if len({{item.get('evidence_type') for item in items}}) >= 2), "")
            if selected_path:
                selected = []
                seen_types = set()
                for fact in by_path[selected_path]:
                    if fact.get("evidence_type") not in seen_types:
                        selected.append(fact["fact_id"])
                        seen_types.add(fact.get("evidence_type"))
                    if len(selected) == 2:
                        break
                value["grounded_findings"] = [{{
                    "finding_id": "scripted-grounded-boundary",
                    "title": "Clarify a scripted evidence-grounded boundary",
                    "category": "module_boundary",
                    "severity": "high",
                    "summary": "Independent static signals identify a boundary worth validating.",
                    "interpretation": "The cited path may combine responsibilities, subject to current-checkout verification.",
                    "why_it_matters": "A confirmed ownership seam can reduce change propagation.",
                    "fact_ids": selected,
                    "paths": [selected_path],
                    "recommendation": "Validate ownership and introduce the smallest explicit seam if the evidence holds.",
                    "alternative_options": [
                        {{"option_id": "A", "title": "Harden in place", "direction": "Add boundary tests first.", "tradeoffs": "Lowest migration risk.", "recommended": True}},
                        {{"option_id": "B", "title": "Extract one responsibility", "direction": "Move one cohesive responsibility.", "tradeoffs": "More structural change.", "recommended": False}},
                    ],
                    "counter_evidence_considered": ["Documentation", "direct tests", "runtime evidence"],
                    "migration_risk": "medium",
                    "migration_sequence": ["Validate evidence", "Add characterization tests", "Introduce one seam"],
                    "test_strategy": ["Protect the current public behavior", "Add a boundary regression test"],
                    "rollback_considerations": "Retain the original entrypoint until callers are verified.",
                    "stop_conditions": ["Stop if the cited path no longer exists", "Stop if tests contradict the hypothesis"],
                }}]
        elif stage == "adversarial_review":
            value["summary"] = "Scripted adversarial review challenged every candidate."
        elif stage == "prompt_authoring":
            for item in value["prompts"]:
                item["objective"] = "Scripted objective: " + item["objective"]
        elif stage == "report_synthesis":
            for name, section in value["sections"].items():
                section["text"] = "Scripted " + name.replace("_", " ") + " narrative grounded in cited facts."
        self.calls += 1
        self.input_tokens += 120
        self.output_tokens += 60
        self.total_tokens += 180
        self.last_usage = {{
            "input_tokens": 120, "output_tokens": 60, "total_tokens": 180,
            "estimated": False, "source": "scripted_provider", "provider_response_count": 1,
            "structured_output_retries": 0, "fallback": False,
        }}
        validated = validator(value) if validator else value
        if validated is None:
            raise ValueError("scripted response failed validator")
        return validated

root = Path({str((ROOT / 'software_architecture_advisor').resolve())!r})
source = root / "examples" / "sample_inputs"
output = Path({str(tmp_path)!r}) / "live-output"
llm = ScriptedLiveLLM()
result = run_blueprint(
    inputs={{"input_folder": str(source), "output_folder": str(output)}},
    config={{"analysis": {{"large_module_line_threshold": 2, "max_files": 100}}, "llm": {{"mode": "live", "require_live": True, "strict_json": True}}}},
    runs_root=output / "runs",
    run_id="architecture-advisor-scripted-live",
    llm_client=llm,
)
artifact = result["final_artifact"]
all_durable = "\\n".join(path.read_text(encoding="utf-8", errors="replace") for base in (output, output / "runs") for path in base.rglob("*") if path.is_file())
print(json.dumps({{
    "stages": llm.stages,
    "packet_kinds": llm.packet_kinds,
    "calls": artifact["llm_analysis"]["aggregate_usage"]["calls"],
    "fallback_calls": artifact["llm_analysis"]["aggregate_usage"]["fallback_calls"],
    "provider_responses": artifact["llm_analysis"]["aggregate_usage"]["provider_response_count"],
    "input_tokens": artifact["llm_analysis"]["aggregate_usage"]["input_tokens"],
    "output_tokens": artifact["llm_analysis"]["aggregate_usage"]["output_tokens"],
    "has_grounded_finding": any(item["origin"] == "llm_grounded" for item in artifact["evidence"]["findings"]),
    "finding_influenced": any(item.get("llm_rationale", "").startswith("Scripted rationale") for item in artifact["evidence"]["findings"]),
    "prompt_influenced": "Scripted objective" in (output / "improvement_prompts.md").read_text(),
    "report_influenced": "Scripted executive summary narrative" in (output / "architecture_report.md").read_text(),
    "raw_source_absent": 'order = {{"customer_id": customer_id, "sku": sku, "status": "created"}}' not in all_durable,
    "trace_has_no_prompt": '\"user_prompt\":' not in (output / "llm_trace.jsonl").read_text() and '\"bounded_context\":' not in (output / "llm_trace.jsonl").read_text(),
}}))
''',
    )
    assert result == {
        "stages": [
            "source_intake", "component_mapping", "cross_cutting_mapping",
            "finding_synthesis", "adversarial_review", "prompt_authoring",
            "report_synthesis", "final_audit",
        ],
        "packet_kinds": [
            "bounded_source_intake_source_packet",
            "bounded_component_mapping_source_packet",
            "bounded_cross_cutting_mapping_source_packet",
            "validated_architecture_evidence",
            "validated_architecture_evidence",
            "validated_architecture_evidence",
            "validated_architecture_evidence",
            "validated_architecture_evidence",
        ],
        "calls": 8,
        "fallback_calls": 0,
        "provider_responses": 8,
        "input_tokens": 960,
        "output_tokens": 480,
        "has_grounded_finding": True,
        "finding_influenced": True,
        "prompt_influenced": True,
        "report_influenced": True,
        "raw_source_absent": True,
        "trace_has_no_prompt": True,
    }


def test_software_architecture_advisor_fails_closed_for_unreachable_fallback_missing_response_and_budget(tmp_path: Path):
    for mode in ("unreachable", "fallback", "no_response", "budget"):
        result = run_payload_script(
            "software_architecture_advisor",
            f'''
import json
from pathlib import Path
from domain.composition import run_blueprint

class FailingLiveLLM:
    provider = "scripted-live"
    model = "scripted-large-local"
    def __init__(self, mode):
        self.mode = mode
        self.calls = self.fallback_calls = 0
        self.input_tokens = self.output_tokens = self.total_tokens = self.estimated_tokens = 0
        self.last_usage = {{}}
    def generate_json(self, *, system_prompt, user_prompt, fallback, validator=None, validation_retries=0):
        if self.mode == "unreachable":
            raise ConnectionError("node-local gateway unreachable")
        self.calls += 1
        self.input_tokens += 10
        self.output_tokens += 5
        self.total_tokens += 15
        is_fallback = self.mode == "fallback"
        self.fallback_calls += int(is_fallback)
        self.last_usage = {{
            "input_tokens": 10, "output_tokens": 5, "total_tokens": 15,
            "estimated": False, "source": "scripted_provider",
            "provider_response_count": 0 if self.mode == "no_response" else 1,
            "fallback": is_fallback,
        }}
        return validator(fallback) if validator else dict(fallback)

root = Path({str((ROOT / 'software_architecture_advisor').resolve())!r})
output = Path({str(tmp_path)!r}) / {mode!r}
llm = FailingLiveLLM({mode!r})
try:
    run_blueprint(
        inputs={{"input_folder": str(root / "examples" / "sample_inputs"), "output_folder": str(output)}},
        config={{"llm": {{"mode": "live", "require_live": True}}, "research_budget": {{"default_actions": {0 if mode == 'budget' else 8}}}}},
        runs_root=output / "runs",
        run_id="architecture-advisor-fail-closed-{mode}",
        llm_client=llm,
    )
except Exception as exc:
    print(json.dumps({{"failed": True, "error": str(exc), "calls": llm.calls, "published": (output / "architecture_assessment.json").exists()}}))
else:
    print(json.dumps({{"failed": False, "error": "", "calls": llm.calls, "published": True}}))
''',
        )
        assert result["failed"] is True
        assert result["published"] is False
        if mode == "budget":
            assert result["calls"] == 0
            assert "budget" in result["error"].lower()
        elif mode == "fallback":
            assert "fallback" in result["error"].lower()
        elif mode == "no_response":
            assert "provider response" in result["error"].lower()
        else:
            assert "unreachable" in result["error"].lower()


def test_software_architecture_advisor_final_model_rejection_prevents_publication(tmp_path: Path):
    result = run_payload_script(
        "software_architecture_advisor",
        f'''
import json
from pathlib import Path
from domain.composition import run_blueprint

class RejectingFinalAuditor:
    provider = "scripted-live"
    model = "scripted-large-local"
    def __init__(self):
        self.calls = self.fallback_calls = 0
        self.input_tokens = self.output_tokens = self.total_tokens = self.estimated_tokens = 0
        self.last_usage = {{}}
    def generate_json(self, *, system_prompt, user_prompt, fallback, validator=None, validation_retries=0):
        payload = json.loads(user_prompt)
        value = json.loads(json.dumps(fallback))
        if payload["stage"] == "final_audit":
            value["verdict"] = "reject"
            value["summary"] = "The scripted auditor rejected publication."
            value["required_revisions"] = ["Resolve the rejected package before publication."]
            value["checks"][0]["status"] = "reject"
        self.calls += 1
        self.input_tokens += 20
        self.output_tokens += 10
        self.total_tokens += 30
        self.last_usage = {{"input_tokens": 20, "output_tokens": 10, "total_tokens": 30, "estimated": False, "source": "scripted_provider", "provider_response_count": 1, "fallback": False}}
        return validator(value) if validator else value

root = Path({str((ROOT / 'software_architecture_advisor').resolve())!r})
output = Path({str(tmp_path)!r}) / "rejected"
llm = RejectingFinalAuditor()
try:
    run_blueprint(
        inputs={{"input_folder": str(root / "examples" / "sample_inputs"), "output_folder": str(output)}},
        config={{"analysis": {{"large_module_line_threshold": 2}}, "llm": {{"mode": "live", "require_live": True}}}},
        runs_root=output / "runs",
        run_id="architecture-advisor-final-reject",
        llm_client=llm,
    )
except Exception as exc:
    print(json.dumps({{"failed": True, "calls": llm.calls, "published": (output / "architecture_assessment.json").exists(), "error": str(exc)}}))
else:
    print(json.dumps({{"failed": False, "calls": llm.calls, "published": True, "error": ""}}))
''',
    )
    assert result["failed"] is True
    assert result["calls"] == 8
    assert result["published"] is False
    assert "model_final_audit_approved" in result["error"]


def test_software_architecture_advisor_builds_deep_static_evidence_without_executing_repo(tmp_path: Path):
    result = run_payload_script(
        "software_architecture_advisor",
        f"""
import json
from pathlib import Path
from mn_software_architecture_graph_skill import build_architecture_graph, build_deep_evidence, build_inventory, compact_inventory

repo = Path({str(tmp_path / 'deep-repo')!r})
(repo / 'tests').mkdir(parents=True)
(repo / 'app.py').write_text('''from fastapi import FastAPI\nimport redis\nimport subprocess\n\napp = FastAPI()\n\n@app.post("/jobs")\ndef submit_job(command: str):\n    redis.Redis().set("job", command)\n    return subprocess.run([command], check=False)\n''')
(repo / 'tests' / 'test_app.py').write_text('''from app import submit_job\n\ndef test_submit_job_contract():\n    assert callable(submit_job)\n''')
(repo / 'Dockerfile').write_text('FROM python:3.11-slim\\n')
(repo / 'pyproject.toml').write_text('[project]\\nname = "deep-fixture"\\nversion = "1.0.0"\\n')
(repo / 'git_history.json').write_text(json.dumps({{'file_churn': [{{'path': 'app.py', 'commits': 12}}]}}))
inventory = build_inventory(repo, {{'supported_extensions': ['.py']}})
graph = build_architecture_graph(inventory)
evidence = build_deep_evidence(repo, inventory, graph)
facts = evidence['facts']['facts']
print(json.dumps({{
    'frameworks': evidence['repository_profile']['frameworks'],
    'state_technologies': [item['technology'] for item in evidence['state_model']['stores']],
    'trust_candidates': len(evidence['trust_model']['candidate_crossings']),
    'history_available': evidence['history']['available'],
    'test_file_count': evidence['test_architecture']['test_file_count'],
    'app_directly_tested': any(item['source_module'] == 'app' for item in evidence['test_architecture']['direct_test_links']),
    'symbol_count_positive': evidence['symbol_index']['symbol_count'] > 0,
    'has_fact_ids': bool(facts) and all(item['fact_id'].startswith('F') for item in facts),
    'source_bodies_compacted': all('text' not in item for item in compact_inventory(inventory)['files']),
}}))
""",
    )
    assert result == {
        "frameworks": ["fastapi"],
        "state_technologies": ["redis"],
        "trust_candidates": 1,
        "history_available": True,
        "test_file_count": 1,
        "app_directly_tested": True,
        "symbol_count_positive": True,
        "has_fact_ids": True,
        "source_bodies_compacted": True,
    }


def test_software_architecture_advisor_uses_the_staged_sample_when_optional_inputs_are_null(tmp_path: Path):
    result = run_payload_script(
        "software_architecture_advisor",
        f"""
import json
from pathlib import Path
from domain.runtime_services import runtime_context_for_step

root = Path({str((ROOT / 'software_architecture_advisor').resolve())!r})
context = runtime_context_for_step(
    inputs={{'input_folder': None, 'github_repo_url': None, 'output_folder': str(Path({str(tmp_path)!r}) / 'output')}},
    config={{'llm': {{'mode': 'fake'}}}},
    runs_root=Path({str(tmp_path)!r}) / 'runs',
    run_id='architecture-advisor-default-input-test',
)
source = Path(context['payload']['input_folder'])
print(json.dumps({{
    'source_is_staged_sample': source == root / 'examples' / 'sample_inputs',
    'source_exists': source.is_dir(),
    'github_repo_url': context['payload'].get('github_repo_url'),
}}))
""",
    )
    assert result == {
        "source_is_staged_sample": True,
        "source_exists": True,
        "github_repo_url": None,
    }


def test_software_architecture_advisor_prefers_the_launch_staged_source_path(tmp_path: Path):
    staged = tmp_path / "staged-source"
    staged.mkdir()
    result = run_payload_script(
        "software_architecture_advisor",
        f"""
import json
from domain.runtime_services import runtime_context_for_step

context = runtime_context_for_step(
    inputs={{'input_folder': None, 'github_repo_url': None}},
    config={{'inputs': {{'payload': {{'input_folder': {str(staged)!r}}}}}}},
    runs_root={str(tmp_path / 'runs')!r},
    run_id='architecture-advisor-staged-input-test',
)
print(json.dumps({{'input_folder': context['payload']['input_folder']}}))
""",
    )
    assert result == {"input_folder": str(staged)}


def test_software_architecture_advisor_waits_only_for_a_platform_staged_source(tmp_path: Path):
    staged = tmp_path / ".mn" / "shared" / "submissions" / "job-123" / "inputs" / "source"
    ordinary_missing = tmp_path / "missing-local-source"
    result = run_payload_script(
        "software_architecture_advisor",
        f"""
import json
from pathlib import Path
from domain.intake import wait_for_platform_staged_directory

staged = Path({str(staged)!r})
waited = []
def stage_source(seconds):
    waited.append(seconds)
    staged.mkdir(parents=True, exist_ok=True)

ready = wait_for_platform_staged_directory(
    str(staged),
    maximum_wait_seconds=1,
    polling_seconds=0.1,
    sleeper=stage_source,
)
ordinary = wait_for_platform_staged_directory(
    {str(ordinary_missing)!r},
    maximum_wait_seconds=1,
    polling_seconds=0.1,
    sleeper=lambda _seconds: (_ for _ in ()).throw(RuntimeError('must not wait')),
)
print(json.dumps({{
    'staged_source_ready': ready == staged,
    'waited_for_platform_source': len(waited) == 1,
    'ordinary_source_unchanged': ordinary == Path({str(ordinary_missing)!r}).resolve(),
    'ordinary_source_missing': not ordinary.exists(),
}}))
""",
    )
    assert result == {
        "staged_source_ready": True,
        "waited_for_platform_source": True,
        "ordinary_source_unchanged": True,
        "ordinary_source_missing": True,
    }


def test_software_architecture_advisor_mapper_re_resolves_the_source_in_its_own_worker(tmp_path: Path):
    mapper_source = ROOT / "software_architecture_advisor" / "examples" / "sample_inputs"
    stale_source = tmp_path / "intake-worker" / "examples" / "sample_inputs"

    result = run_payload_script(
        "software_architecture_advisor",
        f"""
import json
from pathlib import Path
from domain.runtime_services import runtime_context_for_step
from domain.state import source_root_for_context

context = runtime_context_for_step(
    inputs={{"input_folder": {str(mapper_source)!r}}},
    config={{"analysis": {{"max_files": 100}}, "llm": {{"mode": "fake"}}}},
    runs_root={str(tmp_path / 'runs')!r},
    run_id="mapper-source-workspace-test",
)
print(json.dumps({{
    "source_root": str(source_root_for_context(context)),
    "stale_source_is_missing": not Path({str(stale_source)!r}).exists(),
}}))
""",
    )

    assert result == {
        "source_root": str(mapper_source.resolve()),
        "stale_source_is_missing": True,
    }
