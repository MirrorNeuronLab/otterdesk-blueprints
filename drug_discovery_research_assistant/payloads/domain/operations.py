"""Drug-discovery domain bindings that reuse the native stage workers."""

from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from mn_prototype_supervised_service_agent import ServiceContext, SupervisedServiceSpec, create_agent as create_supervised_service
from mn_sdk.blueprint_support import WorkflowStateStore


BLUEPRINT_ID = "drug_discovery_research_assistant"
STATE_FILE = "drug_discovery_state.json"
SCRIPTS = Path(__file__).resolve().parents[1] / "service" / "scripts"


def _inputs(ctx: dict[str, Any]) -> dict[str, Any]:
    payload = dict(((ctx["config"].get("inputs") or {}).get("payload") or {}))
    payload.update(ctx.get("payload") or {})
    return payload


def _state(ctx: dict[str, Any]) -> dict[str, Any]:
    return WorkflowStateStore(Path(ctx["run_dir"])).read(STATE_FILE, {})


def _save(ctx: dict[str, Any], state: dict[str, Any]) -> None:
    WorkflowStateStore(Path(ctx["run_dir"])).write(STATE_FILE, state)


def _stage_config(ctx: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    config = copy.deepcopy(ctx["config"])
    config.setdefault("inputs", {}).setdefault("payload", {}).update(_inputs(ctx))
    if state.get("targets"):
        config["inputs"]["payload"]["targets"] = state["targets"]
    config["inputs"]["payload"]["output_folder"] = str(ctx["output_folder"])
    return config


def _run_script(ctx: dict[str, Any], state: dict[str, Any], script: str, payload: dict[str, Any], *, timeout: int | None = 900) -> dict[str, Any]:
    run_dir = Path(ctx["run_dir"])
    message = run_dir / f"{script}.message.json"
    message.write_text(json.dumps({"body": payload}), encoding="utf-8")
    environment = dict(os.environ)
    bundled_source = Path(__file__).resolve().parents[1]
    if not (bundled_source / "biotarget" / "pipeline.py").is_file():
        raise RuntimeError(f"Bundled BioTarget package is missing from the staged payload: {bundled_source}")
    environment["BIOTARGET_SOURCE_DIR"] = str(bundled_source)
    environment.update({
        "MN_MESSAGE_FILE": str(message),
        "MN_RUN_DIR": str(run_dir),
        "MN_BLUEPRINT_CONFIG_JSON": json.dumps(_stage_config(ctx, state)),
        "MN_SCIENCE_FAKE_MODE": "1" if str((ctx["config"].get("mode") or "")).lower() in {"fake", "mock"} else "0",
    })
    # The continuous service writes its own JSON artifacts and emits the
    # HostLocal beacon protocol on stdout.  Do not capture that output here:
    # swallowing it makes the outer worker look idle while DrugClip is loading
    # or scoring, which causes a false liveness timeout.
    capture_output = script != "run_continuous_service.py"
    completed = subprocess.run(
        [sys.executable, str(SCRIPTS / script)],
        cwd=run_dir,
        env=environment,
        capture_output=capture_output,
        text=True,
        check=False,
        timeout=timeout,
    )
    if completed.returncode:
        stderr = (completed.stderr or "").strip()
        stdout = (completed.stdout or "").strip()
        raise RuntimeError(f"{script} failed: {stderr or stdout}")
    if not capture_output:
        return {}
    for line in reversed(completed.stdout.splitlines()):
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    raise RuntimeError(f"{script} completed without a JSON result")


def discover_targets(ctx: dict[str, Any], **_options: Any) -> dict[str, Any]:
    state = _state(ctx)
    inputs = _inputs(ctx)
    disease = str(inputs.get("disease") or inputs.get("disease_or_target_profile") or "Alzheimer")
    result = _run_script(ctx, state, "stage_a.py", {"disease": disease})
    state.update({"disease": disease, "targets": result.get("targets") or []})
    _save(ctx, state)
    return {"target_count": len(state["targets"])}


def generate_structures(ctx: dict[str, Any], **_options: Any) -> dict[str, Any]:
    state = _state(ctx)
    result = _run_script(ctx, state, "stage_b.py", {"disease": state.get("disease") or "Alzheimer", "targets": state.get("targets") or []})
    state["structures"] = result.get("structures") or []
    _save(ctx, state)
    return {"structure_count": len(state["structures"])}


def run_discovery_service(ctx: dict[str, Any], **_options: Any) -> dict[str, Any]:
    state = _state(ctx)
    service = create_supervised_service(
        SupervisedServiceSpec(
            serve=lambda _service_context: _run_script(ctx, state, "run_continuous_service.py", {}, timeout=None),
        )
    )
    service(context=ServiceContext(config=ctx["config"], run_dir=Path(ctx["run_dir"]), output_folder=Path(ctx["output_folder"])))
    status_path = Path(ctx["run_dir"]) / "service_state.json"
    status = json.loads(status_path.read_text(encoding="utf-8")) if status_path.exists() else {}
    state["service_reports"] = status.get("reports") or []
    _save(ctx, state)
    return {"completed_cycles": status.get("completed_cycles", 0), "service_status": status.get("status")}


def evaluate_binding(ctx: dict[str, Any], **_options: Any) -> dict[str, Any]:
    state = _state(ctx)
    result = _run_script(ctx, state, "stage_d.py", {"reports": state.get("service_reports") or []})
    state["evaluations"] = result.get("evaluations") or []
    _save(ctx, state)
    return {"evaluation_count": len(state["evaluations"])}


def publish_ranking(ctx: dict[str, Any], **_options: Any) -> dict[str, Any]:
    state = _state(ctx)
    result = _run_script(ctx, state, "stage_e.py", {"evaluations": state.get("evaluations") or []})
    artifact = result.get("review_report") or {}
    artifact["type"] = "drug_discovery_research_packet"
    artifact.setdefault("recommended_action", "review_required")
    artifact.setdefault("source_refs", ["service_state.json", "discovery_service_review.json"])
    output = Path(ctx["output_folder"])
    output.mkdir(parents=True, exist_ok=True)
    (output / "final_artifact.json").write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (Path(ctx["run_dir"]) / "final_artifact.json").write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _save(ctx, state)
    return {"final_artifact": artifact, "output_files": [str(output / "final_artifact.json")]}
