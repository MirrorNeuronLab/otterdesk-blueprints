from __future__ import annotations

import json
from pathlib import Path

from blueprint_modernization_support import ROOT, assert_modular_payload, assert_registry_handlers_import, run_payload_script, source_manifest
from mn_sdk import expand_manifest_source
from mn_sdk.submission_preparation import (
    prepare_manifest_for_submission,
    stage_local_input_payloads_for_manifest,
    stage_skill_dependency_payloads_for_manifest,
    stage_upload_path_payloads_for_manifest,
)


def _write_architecture_fixture(root: Path) -> Path:
    package = root / "sample_app"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("")
    (package / "api.py").write_text(
        "from .orders import create_order\n\n\ndef submit_order(customer_id: str, sku: str):\n"
        "    return create_order(customer_id, sku)\n"
    )
    (package / "orders.py").write_text(
        "from .notifications import send_order_confirmation\n\n\ndef create_order(customer_id: str, sku: str):\n"
        "    order = {'customer_id': customer_id, 'sku': sku, 'status': 'created'}\n"
        "    send_order_confirmation(order)\n"
        "    return order\n"
    )
    (package / "notifications.py").write_text(
        "from .orders import create_order\n\n\ndef send_order_confirmation(order):\n"
        "    if order.get('status') == 'retry':\n"
        "        create_order(order['customer_id'], order['sku'])\n"
    )
    return root


def test_software_architecture_advisor_is_air_gapped_and_requires_a_large_local_model():
    manifest = source_manifest("software_architecture_advisor")
    config = json.loads((ROOT / "software_architecture_advisor" / "config" / "default.json").read_text())

    assert manifest["air-gapped"] is True
    assert manifest["contracts"]["inputs"]["input_folder"]["required"] is True
    assert manifest["manifest"]["input_validation"] == {
        "required": ["input_folder"],
        "rules": [],
    }
    assert manifest["requirements"]["memory"]["min_gb"] == 48
    assert manifest["requirements"]["network"]["egress"] == "forbidden"
    assert config["outputs"]["folder_path"] == "~/Downloads/software_architecture_advisor"
    assert config["inputs"]["payload"]["input_folder"] == ""
    assert set(manifest["contracts"]["inputs"]) == {
        "input_folder",
        "analysis_focus",
        "output_folder",
    }
    assert set(config["inputs"]["payload"]) == {
        "input_folder",
        "analysis_focus",
        "output_folder",
    }
    assert "source_acquisition" not in config
    assert config["local_model"]["preinstalled_only"] is True
    assert manifest["llm"]["model"] == "medium"
    assert manifest["workflow"]["workflow_id"] == "software_architecture_advisor_v3"
    assert manifest["workflow"]["execution"]["strategy"] == "serial"
    assert config["llm"]["require_live"] is True
    assert config["llm"]["strict_json"] is True
    assert config["llm"]["context_size"] >= 32768
    assert config["research_budget"]["default_actions"] == 8
    assert config["backpressure"]["llm"]["max_concurrent_calls"] == 1
    for profile in config["llm"]["configs"].values():
        assert "runtime_model" not in profile
        assert profile["model"] == "medium"
        assert profile["timeout_seconds"] == 600
        assert profile["num_retries"] == 2
    assert config["llm"]["configs"]["analysis"]["max_tokens"] == 16000
    assert config["llm"]["configs"]["writing"]["max_tokens"] == 7000
    assert config["llm"]["configs"]["audit"]["max_tokens"] == 5000
    assert config["local_model"]["minimum_host_memory_gb"] == 48
    assert config["llm_analysis"]["token_safety_margin"] == 2048
    assert config["llm_analysis"]["estimated_bytes_per_token"] == 3.0
    assert "max_context_chars" not in config["llm_analysis"]
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


def test_software_architecture_advisor_bundles_no_external_repository_reference():
    blueprint = ROOT / "software_architecture_advisor"
    sample_inputs = blueprint / "examples" / "sample_inputs"

    assert {path.name for path in sample_inputs.iterdir()} == {
        "README.md",
        "SAMPLE_DATASET_MANIFEST.json",
    }


def test_software_architecture_advisor_compacts_prompts_to_the_model_token_budget():
    result = run_payload_script(
        "software_architecture_advisor",
        '''
import json
from domain.model_analysis import _prepare_budgeted_prompt

config = {
    "llm": {
        "context_size": 32768,
        "default_config": "analysis",
        "configs": {"analysis": {"context_size": 32768, "max_tokens": 6000}},
        "agents": {"codebase_mapper": {"llm_config": "analysis"}},
    },
    "llm_analysis": {"token_safety_margin": 2048, "estimated_bytes_per_token": 3.0},
}
context = {
    "packet_kind": "bounded_component_mapping_source_packet",
    "files": [{
        "path": "src/large.py",
        "sha256": "a" * 64,
        "line_count": 5000,
        "excerpt": "value = dependency_call()\\n" * 5000,
        "excerpt_truncated": False,
    }],
    "facts": [{"fact_id": f"F{index:04d}", "paths": ["src/large.py"]} for index in range(12)],
    "packet_limits": {"max_chars": 200000, "max_files": 1, "max_chars_per_file": 200000},
}
fitted, prompt, budget = _prepare_budgeted_prompt(
    config,
    stage="component_mapping",
    task="Map the supplied architecture evidence.",
    system_prompt="Return strict JSON grounded in supplied evidence.",
    context=context,
)
structured_context = {
    "packet_kind": "validated_architecture_evidence",
    "facts": [
        {
            "fact_id": f"F{index:04d}",
            "fact_type": "large_test_fact",
            "paths": ["src/large.py"],
            "value": {"description": "x" * 1000},
        }
        for index in range(160)
    ],
    "candidate_findings": [{"finding_id": "candidate", "fact_ids": ["F0159"]}],
}
structured_fitted, _structured_prompt, structured_budget = _prepare_budgeted_prompt(
    config,
    stage="component_mapping",
    task="Map the supplied architecture evidence.",
    system_prompt="Return strict JSON grounded in supplied evidence.",
    context=structured_context,
)
try:
    _prepare_budgeted_prompt(
        config,
        stage="component_mapping",
        task="Map the supplied architecture evidence.",
        system_prompt="Return strict JSON grounded in supplied evidence.",
        context={"packet_kind": "validated_architecture_evidence", "opaque": "x" * 100000},
    )
except ValueError as exc:
    overflow_error = str(exc)
else:
    overflow_error = ""
print(json.dumps({
    "compacted": budget["prompt_compacted"],
    "within_budget": budget["estimated_input_tokens"] <= budget["input_token_budget"],
    "original_over_budget": budget["original_estimated_input_tokens"] > budget["input_token_budget"],
    "budget_math": budget["input_token_budget"] == 32768 - 6000 - 2048,
    "excerpt_reduced": len(fitted["files"][0]["excerpt"]) < len(context["files"][0]["excerpt"]),
    "facts_preserved": len(fitted["facts"]) == len(context["facts"]),
    "prompt_uses_fitted_context": json.loads(prompt)["bounded_context"] == fitted,
    "structured_compacted": structured_budget["prompt_compacted"],
    "structured_within_budget": structured_budget["estimated_input_tokens"] <= structured_budget["input_token_budget"],
    "referenced_fact_preserved": any(item["fact_id"] == "F0159" for item in structured_fitted["facts"]),
    "optional_facts_reduced": len(structured_fitted["facts"]) < len(structured_context["facts"]),
    "overflow_failed_before_call": "estimated" in overflow_error and "budget" in overflow_error,
}))
''',
    )
    assert result == {
        "compacted": True,
        "within_budget": True,
        "original_over_budget": True,
        "budget_math": True,
        "excerpt_reduced": True,
        "facts_preserved": True,
        "prompt_uses_fitted_context": True,
        "structured_compacted": True,
        "structured_within_budget": True,
        "referenced_fact_preserved": True,
        "optional_facts_reduced": True,
        "overflow_failed_before_call": True,
    }


def test_software_architecture_advisor_keeps_grounded_cross_cutting_items_and_drops_bad_references():
    result = run_payload_script(
        "software_architecture_advisor",
        '''
import json
from domain.mapping import _validate_cross_cutting

valid = {
    "name": "Request flow",
    "analysis": "The API delegates order creation to the orders module.",
    "confidence": "high",
    "paths": ["sample_app/api.py"],
    "fact_ids": ["F0001"],
}
invalid = {
    "name": "Invented flow",
    "analysis": "This cites evidence that was not supplied.",
    "confidence": "high",
    "paths": ["missing.py"],
    "fact_ids": ["F9999"],
}
value = {
    "summary": "Only supplied evidence is retained.",
    "flows": [valid, invalid, "not-an-object"],
    "state_ownership": [],
    "trust_boundaries": [],
    "deployment_interactions": [],
    "test_observations": [],
    "unknowns": ["Runtime behavior was not executed."],
}
print(json.dumps(_validate_cross_cutting(
    value,
    fact_ids={"F0001"},
    paths={"sample_app/api.py"},
)))
''',
    )
    assert result["summary"] == "Only supplied evidence is retained."
    assert result["flows"] == [
        {
            "name": "Request flow",
            "analysis": "The API delegates order creation to the orders module.",
            "confidence": "high",
            "paths": ["sample_app/api.py"],
            "fact_ids": ["F0001"],
        }
    ]
    assert result["unknowns"] == ["Runtime behavior was not executed."]


def test_software_architecture_advisor_keeps_grounded_components_and_drops_bad_references():
    result = run_payload_script(
        "software_architecture_advisor",
        '''
import json
from domain.mapping import _validate_component_map

value = {
    "summary": "Only grounded components and relationships are retained.",
    "components": [
        {
            "component_id": "api",
            "name": "API",
            "responsibility": "Accept requests and delegate application work.",
            "paths": ["sample_app/api.py"],
            "fact_ids": ["F0001"],
        },
        {
            "component_id": "invented",
            "name": "Invented",
            "responsibility": "Not grounded in the packet.",
            "paths": ["missing.py"],
            "fact_ids": ["F9999"],
        },
    ],
    "entrypoints": [
        {"path": "sample_app/api.py", "role": "HTTP entrypoint", "fact_ids": ["F0001"]},
        {"path": "missing.py", "role": "Invented entrypoint", "fact_ids": ["F9999"]},
    ],
    "dependency_directions": [
        {
            "from_component": "api",
            "to_component": "invented",
            "relationship": "Invented relationship",
            "paths": ["missing.py"],
            "fact_ids": ["F9999"],
        }
    ],
    "unknowns": ["Runtime composition was not executed."],
}
print(json.dumps(_validate_component_map(
    value,
    fact_ids={"F0001"},
    paths={"sample_app/api.py"},
)))
''',
    )
    assert [item["component_id"] for item in result["components"]] == ["api"]
    assert [item["path"] for item in result["entrypoints"]] == ["sample_app/api.py"]
    assert result["dependency_directions"] == []
    assert result["unknowns"] == ["Runtime composition was not executed."]

    baseline = run_payload_script(
        "software_architecture_advisor",
        '''
import json
from domain.mapping import _validate_component_map

print(json.dumps(_validate_component_map(
    {
        "summary": "The model synthesis remains useful even when its collection is ungrounded.",
        "components": [{
            "component_id": "invented",
            "name": "Invented",
            "responsibility": "Not grounded.",
            "paths": ["missing.py"],
            "fact_ids": ["F9999"],
        }],
        "entrypoints": [],
        "dependency_directions": [],
        "unknowns": [],
    },
    fact_ids={"F0001"},
    paths={"sample_app/api.py"},
    baseline_components=[{
        "component_id": "repository-root",
        "name": "Repository",
        "responsibility": "Deterministically grounded repository boundary.",
        "paths": ["sample_app/api.py"],
        "fact_ids": ["F0001"],
    }],
    baseline_entrypoints=[{
        "path": "sample_app/api.py",
        "role": "Statically detected entrypoint candidate",
        "fact_ids": ["F0001"],
    }],
)))
''',
    )
    assert [item["component_id"] for item in baseline["components"]] == ["repository-root"]
    assert [item["path"] for item in baseline["entrypoints"]] == ["sample_app/api.py"]


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


def test_software_architecture_advisor_stages_only_bundled_documentation_for_workers():
    blueprint = ROOT / "software_architecture_advisor"
    prepared = prepare_manifest_for_submission(
        blueprint,
        source_manifest("software_architecture_advisor"),
    )
    staged: dict[str, bytes] = {}

    stage_upload_path_payloads_for_manifest(prepared, staged, bundle_dir=blueprint)

    assert "examples/sample_inputs/README.md" in staged
    assert "examples/sample_inputs/SAMPLE_DATASET_MANIFEST.json" in staged
    assert not any("mini_order_service" in path for path in staged)


def test_software_architecture_advisor_stages_the_required_local_source_folder(tmp_path: Path):
    blueprint = ROOT / "software_architecture_advisor"
    source = _write_architecture_fixture(tmp_path / "local-source")
    prepared = prepare_manifest_for_submission(
        blueprint,
        source_manifest("software_architecture_advisor"),
        config_overrides={"inputs": {"payload": {"input_folder": str(source)}}},
    )
    staged: dict[str, bytes] = {}

    summary = stage_local_input_payloads_for_manifest(
        prepared,
        staged,
        bundle_dir=blueprint,
    )

    assert summary["folders"] == [
        {
            "config_path": "inputs.payload.input_folder",
            "payload_path": "mn_local_inputs/software_architecture_advisor_source",
            "runtime_path": "mn_local_inputs/software_architecture_advisor_source",
            "file_count": 4,
        }
    ]
    assert "mn_local_inputs/software_architecture_advisor_source/sample_app/api.py" in staged


def test_software_architecture_advisor_writes_copy_ready_prompts_without_changing_source(tmp_path: Path):
    source = _write_architecture_fixture(tmp_path / "architecture-source")
    result = run_payload_script(
        "software_architecture_advisor",
        f"""
import hashlib
import json
from pathlib import Path
from domain.composition import run_blueprint

source = Path({str(source.resolve())!r})
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
    source = _write_architecture_fixture(tmp_path / "live-architecture-source")
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
        self.final_audit_is_compact = False
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
        elif stage == "final_audit":
            self.final_audit_is_compact = (
                all("output" not in record for record in context["prior_llm_stages"].values())
                and all("body" not in prompt for prompt in context["prompts"])
                and all(prompt["safety_and_reversibility_excerpt"] for prompt in context["prompts"])
            )
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

source = Path({str(source.resolve())!r})
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
    "final_audit_is_compact": llm.final_audit_is_compact,
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
        "final_audit_is_compact": True,
        "raw_source_absent": True,
        "trace_has_no_prompt": True,
    }


def test_software_architecture_advisor_fails_closed_for_unreachable_fallback_missing_response_and_budget(tmp_path: Path):
    source = _write_architecture_fixture(tmp_path / "failure-architecture-source")
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

output = Path({str(tmp_path)!r}) / {mode!r}
llm = FailingLiveLLM({mode!r})
try:
    run_blueprint(
        inputs={{"input_folder": {str(source.resolve())!r}, "output_folder": str(output)}},
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
    source = _write_architecture_fixture(tmp_path / "rejection-architecture-source")
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

output = Path({str(tmp_path)!r}) / "rejected"
llm = RejectingFinalAuditor()
try:
    run_blueprint(
        inputs={{"input_folder": {str(source.resolve())!r}, "output_folder": str(output)}},
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


def test_software_architecture_advisor_requires_a_local_source_folder(tmp_path: Path):
    result = run_payload_script(
        "software_architecture_advisor",
        f"""
import json
from pathlib import Path
from domain.intake import resolve_source
from domain.runtime_services import runtime_context_for_step

context = runtime_context_for_step(
    inputs={{'input_folder': None, 'output_folder': str(Path({str(tmp_path)!r}) / 'output')}},
    config={{'llm': {{'mode': 'fake'}}}},
    runs_root=Path({str(tmp_path)!r}) / 'runs',
    run_id='architecture-advisor-default-input-test',
)
try:
    resolve_source(context)
except ValueError as exc:
    error = str(exc)
else:
    error = None
print(json.dumps({{
    'input_folder_is_empty': not bool(context['payload'].get('input_folder')),
    'error': error,
}}))
""",
    )
    assert result == {
        "input_folder_is_empty": True,
        "error": "input_folder is required and must identify a local source directory.",
    }


def test_software_architecture_advisor_prefers_the_worker_staged_source_path(tmp_path: Path):
    host_source = tmp_path / "host-source"
    worker_source = "mn_local_inputs/software_architecture_advisor_source"
    result = run_payload_script(
        "software_architecture_advisor",
        f"""
import json
from domain.runtime_services import runtime_context_for_step

context = runtime_context_for_step(
    inputs={{'input_folder': {str(host_source)!r}}},
    config={{'inputs': {{'payload': {{'input_folder': {worker_source!r}}}}}}},
    runs_root={str(tmp_path / 'runs')!r},
    run_id='architecture-advisor-staged-input-test',
)
print(json.dumps({{'input_folder': context['payload']['input_folder']}}))
""",
    )
    assert result == {"input_folder": worker_source}


def test_software_architecture_advisor_uses_the_mounted_source_when_invocation_config_restores_host_path(tmp_path: Path):
    host_source = "/Users/homer/Sandbox/Archmind"
    job_input_dir = tmp_path / "job-inputs"
    worker_source = job_input_dir / "mn_local_inputs" / "software_architecture_advisor_source"
    worker_source.mkdir(parents=True)
    result = run_payload_script(
        "software_architecture_advisor",
        f"""
import json
import os
from domain.runtime_services import runtime_context_for_step

os.environ["MN_JOB_INPUT_DIR"] = {str(job_input_dir)!r}
context = runtime_context_for_step(
    inputs={{"input_folder": {host_source!r}}},
    config={{"inputs": {{"payload": {{"input_folder": {host_source!r}}}}}}},
    runs_root={str(tmp_path / 'runs')!r},
    run_id="architecture-advisor-mounted-input-test",
)
print(json.dumps({{"input_folder": context["payload"]["input_folder"]}}))
""",
    )
    assert result == {"input_folder": str(worker_source)}


def test_software_architecture_advisor_mapper_re_resolves_the_source_in_its_own_worker(tmp_path: Path):
    mapper_source = _write_architecture_fixture(tmp_path / "mapper-source")
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
