from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .config import default_config
from .constants import (
    BLUEPRINT_CATEGORIES,
    CONFIG_SECTIONS,
    INPUT_ADAPTERS,
    OUTPUT_ADAPTERS,
    RUN_ARTIFACTS,
    STANDARD_VERSION,
)
from .metadata import infer_category
from .utils import human_label


def scaffold_blueprint(
    blueprint_id: str,
    *,
    target_root: str | Path = ".",
    category: str | None = None,
    description: str | None = None,
    force: bool = False,
) -> dict[str, Any]:
    if not re.match(r"^[a-z][a-z0-9_]*$", blueprint_id):
        raise ValueError("blueprint_id must be lowercase snake_case")
    category = category or infer_category(blueprint_id)
    if category not in BLUEPRINT_CATEGORIES:
        raise ValueError(f"category must be one of {', '.join(BLUEPRINT_CATEGORIES)}")
    if not blueprint_id.startswith(f"{category}_"):
        raise ValueError(f"blueprint_id should start with {category}_")

    root = Path(target_root).expanduser()
    blueprint_dir = root / blueprint_id
    if blueprint_dir.exists() and not force:
        raise FileExistsError(f"{blueprint_dir} already exists; pass force=True to overwrite scaffold files")

    description = description or f"Scaffolded {category} blueprint ready for domain-specific simulation and agent logic."
    config = default_config(blueprint_id)
    config["metadata"] = {
        "category": category,
        "target_users": "Define the target users for this workflow.",
        "problem_solved": description,
        "customizable_for": "Replace mock inputs, tune simulation logic, and connect production systems.",
    }
    config["outputs"]["artifact_contract"] = "Structured recommendation, report, or workflow result."
    config["inputs"]["payload"] = {"steps": 3, "seed": 42}
    config["simulation"]["type"] = "Scaffolded placeholder simulation."
    config["llm"]["agent_role"] = "Scaffolded reasoning agent"
    config["llm"]["responsibilities"] = ["observe input state", "choose next action", "write a structured recommendation"]

    files = {
        blueprint_dir / "config" / "default.json": json.dumps(config, indent=2, sort_keys=True) + "\n",
        blueprint_dir / "manifest.json": json.dumps(_scaffold_manifest(blueprint_id, category, description), indent=2, sort_keys=True) + "\n",
        blueprint_dir / "README.md": _scaffold_readme(blueprint_id, category, description),
        blueprint_dir / "payloads" / "simulation_loop" / "scripts" / "run_blueprint.py": _scaffold_runner(blueprint_id),
        blueprint_dir / "tests" / "test_blueprint_smoke.py": _scaffold_test(blueprint_id),
    }
    for path, text in files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and not force:
            raise FileExistsError(f"{path} already exists; pass force=True to overwrite scaffold files")
        path.write_text(text)

    return {
        "blueprint_id": blueprint_id,
        "name": config["identity"]["name"],
        "category": category,
        "path": str(blueprint_dir),
        "files": [str(path) for path in sorted(files)],
        "next_steps": [
            "Edit config/default.json with domain inputs and simulation parameters.",
            "Replace the scaffolded run_blueprint.py logic with the real observe-decide-act loop.",
            "Run the smoke test and then connect real input adapters.",
        ],
    }


def _scaffold_manifest(blueprint_id: str, category: str, description: str) -> dict[str, Any]:
    return {
        "manifest_version": "1.0",
        "description": description,
        "graph_id": f"{blueprint_id}_v1",
        "job_name": blueprint_id.replace("_", "-"),
        "name": human_label(blueprint_id),
        "entrypoints": ["simulation_loop"],
        "initial_inputs": {"simulation_loop": [{"steps": 3, "seed": 42}]},
        "nodes": [
            {
                "node_id": "simulation_loop",
                "type": "generic",
                "role": "root_coordinator",
                "agent_type": "executor",
                "config": {
                    "command": ["python3", "scripts/run_blueprint.py"],
                    "upload_as": "simulation_loop",
                    "upload_path": "simulation_loop",
                    "workdir": "/sandbox/job/simulation_loop",
                    "output_message_type": "blueprint_report",
                },
            },
            {
                "node_id": "report_sink",
                "type": "reduce",
                "role": "result_sink",
                "agent_type": "aggregator",
                "config": {"complete_on_message": True},
            },
        ],
        "edges": [
            {
                "edge_id": "simulation_to_report",
                "from_node": "simulation_loop",
                "to_node": "report_sink",
                "message_type": "blueprint_report",
            }
        ],
        "metadata": {
            "blueprint_id": blueprint_id,
            "name": human_label(blueprint_id),
            "category": category,
            "description": description,
            "target_user": "Define the target user.",
            "problem_solved": description,
            "runtime_features": ["standard config", "mock inputs", "run store", "shared CLI"],
            "standard": {
                "version": STANDARD_VERSION,
                "config_path": "config/default.json",
                "default_input_adapter": "mock",
                "real_input_adapters": list(INPUT_ADAPTERS[1:]),
                "output_adapter": "local_run_store",
                "run_store": "~/.mn/runs/<run_id>/",
                "execution_model": "load metadata -> resolve config -> load inputs -> simulate/decide loop -> emit events -> write final artifact",
            },
            "interfaces": {
                "identity": ["blueprint_id", "name", "run_id"],
                "config": list(CONFIG_SECTIONS),
                "input_adapters": list(INPUT_ADAPTERS),
                "output_adapters": list(OUTPUT_ADAPTERS),
                "outputs": list(RUN_ARTIFACTS),
            },
        },
    }


def _scaffold_readme(blueprint_id: str, category: str, description: str) -> str:
    title = human_label(blueprint_id)
    return f"""# {title}

`Blueprint ID:` `{blueprint_id}`  
`Category:` {category}

## One-line value proposition

{description}

## What it is

This scaffold is a reusable MirrorNeuron blueprint starting point. It runs with mock inputs, writes standard run artifacts, and gives developers a clean place to add domain-specific simulation, agent decisions, and final reports.

## Who this is for

Define the {category} user persona this workflow serves.

## Why it matters

Real deployments need more than a one-shot LLM prompt. A production-grade blueprint should define identity, configuration, inputs, simulation logic, agent reasoning, outputs, logs, and tests before real data is connected.

## How it works

1. Loads `config/default.json`.
2. Resolves mock or adapter-provided inputs.
3. Creates a standard run context and run directory.
4. Emits placeholder simulation and LLM-decision events.
5. Writes `result.json` and `final_artifact.json`.

## How to run

```bash
python3 payloads/simulation_loop/scripts/run_blueprint.py --mock-llm --steps 3
```

Set up local defaults:

```bash
python3 payloads/simulation_loop/scripts/run_blueprint.py --setup
```

Monitor runs:

```bash
python3 payloads/simulation_loop/scripts/run_blueprint.py --list-runs
python3 payloads/simulation_loop/scripts/run_blueprint.py --show-run <run_id>
```

## How to customize

1. Replace the mock payload in `config/default.json`.
2. Tune the simulation logic in `payloads/simulation_loop/scripts/run_blueprint.py`.
3. Adjust the LLM agent role, responsibilities, and final artifact shape.
4. Connect real input adapters and production output systems.

## Runtime features demonstrated

- Standard blueprint identity
- Config-driven execution
- Mock-to-real input adapters
- Local run store
- Shared CLI setup and monitoring

## Limitations

This is a scaffold, not a finished solution. Validate the simulation and agent policy before using it for real decisions.
"""


def _scaffold_runner(blueprint_id: str) -> str:
    return f'''from __future__ import annotations

import sys
from pathlib import Path


search_roots = [*Path(__file__).resolve().parents, Path.cwd(), *Path.cwd().parents]
for parent in search_roots:
    skill_src = parent / "mn-skills" / "blueprint_support_skill" / "src"
    if skill_src.exists() and str(skill_src) not in sys.path:
        sys.path.insert(0, str(skill_src))

from mn_blueprint_support import architecture_contract, create_runtime_context, load_config, resolve_input_overrides, run_blueprint_cli, utc_now_iso


BLUEPRINT_ID = "{blueprint_id}"


def run_blueprint(
    blueprint_id: str = BLUEPRINT_ID,
    *,
    inputs: dict | None = None,
    config: dict | None = None,
    config_path: str | Path | None = None,
    config_json: str | None = None,
    run_id: str | None = None,
    runs_root: str | Path | None = None,
    input_adapter: str | None = None,
    input_file: str | Path | None = None,
    write_run_store: bool | None = None,
) -> dict:
    default_config_path = Path(__file__).resolve().parents[3] / "config" / "default.json"
    resolved_config = load_config(
        blueprint_id,
        default_config_path=default_config_path,
        config=config,
        config_path=config_path,
        config_json=config_json,
        run_id=run_id,
        runs_root=runs_root,
        input_adapter=input_adapter,
        input_file=input_file,
        write_run_store=write_run_store,
    )
    adapter_inputs, input_source = resolve_input_overrides(resolved_config)
    runtime_inputs = {{**adapter_inputs, **(inputs or {{}})}}
    context = create_runtime_context(blueprint_id, resolved_config, runtime_inputs, input_source)
    started_at = utc_now_iso()
    context.start()
    try:
        context.event("simulation_step_started", {{"step": 0, "state_before": runtime_inputs}})
        decision = {{
            "action": "replace_scaffold_logic",
            "confidence": 0.5,
            "rationale": "Scaffold runner executed. Replace this placeholder with real simulation and LLM decision logic.",
            "parameters": {{"input_keys": sorted(runtime_inputs)}},
        }}
        context.event("llm_decision", {{"step": 0, "decision": decision}})
        context.event("simulation_state_updated", {{"step": 0, "state_after": runtime_inputs}})
        result = {{
            "identity": {{"blueprint_id": blueprint_id, "name": context.name, "run_id": context.run_id}},
            "blueprint": blueprint_id,
            "name": context.name,
            "run": {{
                "run_id": context.run_id,
                "run_dir": str(context.run_dir) if context.run_dir else None,
                "started_at": started_at,
                "ended_at": utc_now_iso(),
                "status": "completed",
            }},
            "architecture": architecture_contract(resolved_config, input_source),
            "inputs": runtime_inputs,
            "timeline": [{{"step": 0, "decision": decision, "state_after": runtime_inputs}}],
            "final_artifact": {{
                "type": "scaffold report",
                "recommended_action": "replace_scaffold_logic",
                "next_steps": [
                    "Edit config/default.json.",
                    "Replace scaffold simulation logic.",
                    "Add domain-specific tests.",
                ],
            }},
        }}
        context.finish(result)
        return result
    except Exception as error:
        context.fail(error)
        raise


def main(argv: list[str] | None = None) -> None:
    run_blueprint_cli(run_blueprint, argv, default_blueprint_id=BLUEPRINT_ID)


if __name__ == "__main__":
    main()
'''


def _scaffold_test(blueprint_id: str) -> str:
    return f'''import importlib.util
from pathlib import Path


def test_scaffolded_blueprint_runs(tmp_path):
    runner_path = Path(__file__).resolve().parents[1] / "payloads" / "simulation_loop" / "scripts" / "run_blueprint.py"
    spec = importlib.util.spec_from_file_location("scaffold_runner", runner_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    result = module.run_blueprint("{blueprint_id}", inputs={{"steps": 1}}, runs_root=tmp_path)

    assert result["identity"]["blueprint_id"] == "{blueprint_id}"
    assert result["final_artifact"]["recommended_action"] == "replace_scaffold_logic"
    assert (tmp_path / result["identity"]["run_id"] / "run.json").exists()
'''
