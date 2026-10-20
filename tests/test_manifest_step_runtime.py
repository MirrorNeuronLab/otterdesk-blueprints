from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from blueprint_modernization_support import blueprint_path
from mn_sdk import expand_manifest_source, is_manifest_source
from mn_sdk.blueprints import blueprint_definition, read_blueprint, resolve_config
from mn_sdk.blueprints.worker_descriptors import resolved_worker_descriptor
from workspace_paths import companion_workspace

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = companion_workspace(ROOT)
SDK_ROOT = WORKSPACE / "mn-python-sdk"
SKILL_SOURCES = sorted((WORKSPACE / "mn-skills").glob("*/src"))
AGENT_SOURCES = sorted((WORKSPACE / "mn-agents").glob("*/src"))


def _mapped_fields(fields, *, inputs, upstream_outputs, flow_output=None):
    """Resolve the data-only source/sink fields for this offline handler smoke.

    This fixture does not schedule Core joins, retries or child workflows. Core
    owns those integration contracts; generated workers must still run here.
    """

    def resolve(value):
        if isinstance(value, dict):
            reference = value.get("$ref")
            if reference in {"run_input", "upstream", "flow_output"}:
                selected = {
                    "run_input": inputs,
                    "upstream": upstream_outputs.get(value.get("step_id")),
                    "flow_output": flow_output,
                }[reference]
                for part in value.get("path", []):
                    selected = (
                        selected.get(part) if isinstance(selected, dict) else None
                    )
                return selected
            return {key: resolve(item) for key, item in value.items()}
        if isinstance(value, list):
            return [resolve(item) for item in value]
        return value

    return resolve(fields)


def _write_software_architecture_source(root: Path) -> Path:
    package = root / "sample_app"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "api.py").write_text(
        "from .orders import create_order\n\n\ndef submit_order(customer_id, sku):\n"
        "    return create_order(customer_id, sku)\n",
        encoding="utf-8",
    )
    (package / "orders.py").write_text(
        "from .notifications import notify\n\n\ndef create_order(customer_id, sku):\n"
        "    order = {'customer_id': customer_id, 'sku': sku}\n"
        "    notify(order)\n"
        "    return order\n",
        encoding="utf-8",
    )
    (package / "notifications.py").write_text(
        "from .orders import create_order\n\n\ndef notify(order):\n"
        "    if order.get('retry'):\n"
        "        create_order(order['customer_id'], order['sku'])\n",
        encoding="utf-8",
    )
    return root


def _run_handler_workflow(
    blueprint_id: str,
    tmp_path: Path,
    *,
    inputs: dict,
    config: dict,
) -> dict:
    blueprint = blueprint_path(blueprint_id)
    payloads = blueprint / "payloads"
    # Native dependencies can write process-local session metadata. Workers
    # execute in their temporary workdir; the source package is read-only input.
    scripts = tmp_path / "workspace"
    scripts.mkdir(parents=True, exist_ok=True)
    original_files = {
        path.relative_to(blueprint) for path in blueprint.rglob("*") if path.is_file()
    }
    package = read_blueprint(blueprint)
    configuration = resolve_config(package, config)
    manifest = blueprint_definition(package, configuration)
    runtime_manifest = (
        expand_manifest_source(manifest, root_dir=blueprint)
        if is_manifest_source(manifest)
        else manifest
    )
    message_path = tmp_path / f"{blueprint_id}-message.json"
    message_path.write_text(json.dumps({"kwargs": inputs}), encoding="utf-8")
    result: dict = {}
    source_registry = manifest["agents"]["registry"]
    descriptor_path = tmp_path / "runtime/manifest.json"
    descriptor_path.parent.mkdir()
    descriptor_path.write_text(
        json.dumps(resolved_worker_descriptor(package, runtime_manifest, configuration))
    )
    if is_manifest_source(manifest):
        assignments = []
        for node in runtime_manifest["agents"]["nodes"]:
            environment = (node.get("config") or {}).get("environment") or {}
            agent_id = environment.get("MN_WORKFLOW_AGENT_ID")
            if not environment.get("MN_WORKFLOW_STEP_HANDLER"):
                continue
            assignments.append(
                {
                    "step_id": environment["MN_WORKFLOW_STEP_ID"],
                    "agent_id": agent_id,
                    "invocation_id": environment["MN_WORKFLOW_INVOCATION_ID"],
                    "needs": [],
                    "definition": {
                        "handler": environment["MN_WORKFLOW_STEP_HANDLER"],
                        "with": json.loads(
                            environment.get("MN_WORKFLOW_STEP_WITH_JSON", "{}")
                        ),
                    },
                }
            )
    else:
        assignments = [
            {
                "step_id": step["id"],
                "agent_id": assignment["agent_id"],
                "invocation_id": f"{step['id']}__{assignment['agent_id']}",
                "needs": assignment.get("needs", []),
            }
            for step in manifest["workflow"]["steps"]
            for assignment in step["run"]["agents"]
        ]

    agent_outputs = {}
    executed_agents = []
    upstream_outputs = {}
    runtime_nodes = {
        node["node_id"]: node for node in runtime_manifest["agents"]["nodes"]
    }
    for index, assignment in enumerate(assignments):
        step_id = assignment["step_id"]
        agent_id = assignment["agent_id"]
        invocation_id = assignment["invocation_id"]
        definition = assignment.get("definition") or source_registry[agent_id]
        start = runtime_nodes.get(f"{step_id}__start", {}).get("config", {})
        step_input = (
            _mapped_fields(
                start["fields"], inputs=inputs, upstream_outputs=upstream_outputs
            )
            if "fields" in start
            else {"kwargs": inputs}
        )
        message_path.write_text(
            json.dumps(
                {
                    "body": {
                        "step_input": step_input,
                        "agent_outputs": {
                            dependency: agent_outputs[dependency]
                            for dependency in assignment.get("needs", [])
                            if dependency in agent_outputs
                        },
                        "artifact_refs": [],
                    }
                }
            ),
            encoding="utf-8",
        )
        environment = dict(os.environ)
        environment.update(
            {
                "MN_JOB_ID": f"{blueprint_id}-handler-test",
                "MN_MESSAGE_FILE": str(message_path),
                "MN_RUN_ID": f"{blueprint_id}-handler-test",
                "MN_RUN_DIR": str(tmp_path / "runs" / f"{blueprint_id}-handler-test"),
                "MN_BLUEPRINT_BUNDLE_DIR": str(blueprint),
                "MN_BLUEPRINT_MANIFEST_PATH": str(descriptor_path),
                "MN_SDK_COMPONENTS_JSON": json.dumps(
                    ["blueprint-blocks"]
                    if "mn_blocks" in manifest.get("metadata", {})
                    else []
                ),
                "MN_WORKFLOW_STEP_ID": step_id,
                "MN_WORKFLOW_AGENT_ID": agent_id,
                "MN_WORKFLOW_INVOCATION_ID": invocation_id,
                "MN_WORKFLOW_IDEMPOTENCY_KEY": f"{blueprint_id}/{invocation_id}",
                "MN_BLUEPRINT_CONFIG_JSON": json.dumps(config),
                "MN_JOB_OUTPUT_DIR": str(tmp_path / "outputs"),
                "MN_RUNS_ROOT": str(tmp_path / "runs"),
                "MN_WORKDIR": str(tmp_path / "workspace"),
                "PYTHONPATH": os.pathsep.join(
                    value
                    for value in (
                        str(payloads),
                        str(SDK_ROOT),
                        *(
                            str(path)
                            for path in sorted((payloads / "skills").glob("*/src"))
                            if path.is_dir()
                        ),
                        *(str(path) for path in SKILL_SOURCES),
                        *(str(path) for path in AGENT_SOURCES),
                        environment.get("PYTHONPATH", ""),
                    )
                    if value
                ),
            }
        )
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "mn_sdk.step_runtime",
                "--handler",
                definition["handler"],
                "--with-json",
                json.dumps(definition.get("with") or {}),
            ],
            cwd=scripts,
            env=environment,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert completed.returncode == 0, completed.stderr
        result = json.loads(
            "\n".join(
                line
                for line in completed.stdout.splitlines()
                if not line.startswith("__MN_EVENT__")
            )
        )
        assert result["workflow_step_id"] == step_id
        agent_outputs[agent_id] = dict(result.get("outputs") or {})
        executed_agents.append(agent_id)
        if (
            index + 1 == len(assignments)
            or assignments[index + 1]["step_id"] != step_id
        ):
            end = runtime_nodes.get(f"{step_id}__end", {}).get("config", {})
            upstream_outputs[step_id] = _mapped_fields(
                end.get("fields", {}),
                inputs=inputs,
                upstream_outputs=upstream_outputs,
                flow_output=agent_outputs[agent_id],
            )
    assert {
        path.relative_to(blueprint)
        for path in blueprint.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    } == {path for path in original_files if "__pycache__" not in path.parts}
    return {
        **dict(result.get("outputs") or {}),
        **{key: value for key, value in result.items() if key != "outputs"},
        "executed_agents": executed_agents,
        "expected_agents": [item["agent_id"] for item in assignments],
        "step_outputs": upstream_outputs,
        "run_dir": str(tmp_path / "runs" / f"{blueprint_id}-handler-test"),
    }


@pytest.mark.parametrize(
    ("blueprint_id", "inputs", "config"),
    [
        (
            "vc_assistant",
            {
                "document_folder": str(
                    ROOT.parent
                    / "mn-blueprints"
                    / "vc_assistant"
                    / "examples"
                    / "sample_inputs"
                    / "aurora_ai"
                ),
                "monitoring": {"max_cycles": 1},
            },
            {
                "source_context": {"enabled": False},
                "text_memory": {"enabled": False},
                "llm": {"mode": "fake", "require_live": False},
                "knowledge_rag": {"enabled": False, "required": False},
                "agentic_research": {"enabled": False},
                "internet_research": {"enabled": False},
            },
        ),
        (
            "procurement_manager",
            {
                "input_folder": str(
                    ROOT / "procurement_manager" / "examples" / "sample_inputs"
                )
            },
            {
                "execution": {"quick_test": True},
                "llm": {"mode": "fake", "require_live": False},
                "knowledge_rag": {"enabled": False, "required": False},
                "internet_research": {"enabled": False},
            },
        ),
        (
            "financial_advisor",
            {
                "document_folder": str(
                    ROOT.parent
                    / "mn-blueprints"
                    / "financial_advisor"
                    / "examples"
                    / "sample_inputs"
                )
            },
            {
                "execution": {"quick_test": True},
                "llm": {"mode": "fake", "require_live": False},
                "knowledge_rag": {"enabled": False, "required": False},
                "internet_research": {"enabled": False},
            },
        ),
        (
            "research_assistant",
            {
                "input_folder": str(
                    ROOT / "research_assistant" / "examples" / "sample_inputs"
                )
            },
            {
                "execution": {"quick_test": True},
                "llm": {"mode": "fake", "require_live": False},
                "knowledge_rag": {"enabled": False, "required": False},
                "internet_research": {"enabled": False},
            },
        ),
        (
            "software_architecture_advisor",
            {
                "input_folder": str(
                    ROOT
                    / "software_architecture_advisor"
                    / "examples"
                    / "sample_inputs"
                ),
            },
            {
                "llm": {"mode": "fake", "require_live": False},
                "analysis": {"max_files": 100, "large_module_line_threshold": 2},
            },
        ),
    ],
)
def test_manifest_handlers_execute_as_message_chained_workflows(
    blueprint_id: str,
    inputs: dict,
    config: dict,
    tmp_path: Path,
):
    if blueprint_id == "software_architecture_advisor":
        pytest.skip(
            "Child DAG scheduling requires Core; compiler, block handoff and domain investigation have separate offline integration tests"
        )
    result = _run_handler_workflow(
        blueprint_id,
        tmp_path,
        inputs=inputs,
        config=config,
    )

    assert result["status"] == "completed"
    assert result["executed_agents"] == result["expected_agents"]
    if blueprint_id == "procurement_manager":
        assessment = result["step_outputs"]["assess_procurement_case"][
            "case_assessment"
        ]
        assert assessment["kind"] == "block_result"
        assert "block_assess_procurement_case_specialist" in result["executed_agents"]
    final_ref = result.get("final_artifact")
    assert isinstance(final_ref, dict)
    assert final_ref["kind"] == "final_artifact"
    final_path = Path(result["run_dir"]) / final_ref["path"]
    assert final_path.exists()
