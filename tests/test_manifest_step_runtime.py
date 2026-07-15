from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SDK_ROOT = ROOT.parent / "mn-python-sdk"
SKILL_SOURCES = sorted((ROOT.parent / "mn-skills").glob("*/src"))


def _run_handler_workflow(
    blueprint_id: str,
    tmp_path: Path,
    *,
    inputs: dict,
    config: dict,
) -> dict:
    blueprint = ROOT / blueprint_id
    payloads = blueprint / "payloads"
    scripts = payloads
    manifest = json.loads((blueprint / "manifest.json").read_text(encoding="utf-8"))
    message_path = tmp_path / f"{blueprint_id}-message.json"
    message_path.write_text(json.dumps({"kwargs": inputs}), encoding="utf-8")
    result: dict = {}
    for step in manifest["workflow"]["steps"]:
        run = step["run"]
        environment = dict(os.environ)
        environment.update(
            {
                "MN_JOB_ID": f"{blueprint_id}-handler-test",
                "MN_MESSAGE_FILE": str(message_path),
                "MN_WORKFLOW_STEP_ID": step["id"],
                "MN_BLUEPRINT_CONFIG_JSON": json.dumps(config),
                "MN_JOB_OUTPUT_DIR": str(tmp_path / "outputs"),
                "MN_RUNS_ROOT": str(tmp_path / "runs"),
                "MN_WORKDIR": str(tmp_path / "workspace"),
                "PYTHONPATH": os.pathsep.join(
                    value
                    for value in (
                        str(SDK_ROOT),
                        *(str(path) for path in SKILL_SOURCES),
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
                run["handler"],
                "--with-json",
                json.dumps(run.get("with") or {}),
            ],
            cwd=scripts,
            env=environment,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert completed.returncode == 0, completed.stderr
        result = json.loads(completed.stdout)
        assert result["workflow_step_id"] == step["id"]
        message_path.write_text(json.dumps(result), encoding="utf-8")
    return result


@pytest.mark.parametrize(
    ("blueprint_id", "inputs", "config"),
    [
        (
            "vc_assistant",
            {"document_folder": "vc_assistant/examples/sample_inputs", "monitoring": {"max_cycles": 1}},
            {
                "llm": {"mode": "fake", "require_live": False},
                "knowledge_rag": {"enabled": False, "required": False},
                "agentic_research": {"enabled": False},
                "internet_research": {"enabled": False},
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
    result = _run_handler_workflow(
        blueprint_id,
        tmp_path,
        inputs=inputs,
        config=config,
    )

    assert result["status"] == "completed"
    assert isinstance(result.get("final_artifact"), dict)
