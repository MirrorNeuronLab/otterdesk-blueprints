"""Native BioTarget stage bindings for the discovery specialist agents."""

from __future__ import annotations

import copy
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from mn_sdk.blueprint_support import WorkflowStateStore

from .conversation_sources import publish_inputs, publish_results

STATE_FILE = "drug_discovery_state.json"
SCRIPTS = Path(__file__).resolve().parents[1] / "service" / "scripts"


def read_discovery_state(ctx: dict[str, Any]) -> dict[str, Any]:
    return WorkflowStateStore(Path(ctx["run_dir"])).read(STATE_FILE, {})


def write_discovery_state(ctx: dict[str, Any], state: dict[str, Any]) -> None:
    WorkflowStateStore(Path(ctx["run_dir"])).write(STATE_FILE, state)
    publish_results(ctx, state)


def _resolved_inputs(ctx: dict[str, Any]) -> dict[str, Any]:
    payload = dict((ctx["config"].get("inputs") or {}).get("payload") or {})
    # Optional run_input mappings use None when absent. They must not erase
    # configured research inputs; explicit empty lists still clear a selection.
    payload.update({key: value for key, value in (ctx.get("payload") or {}).items()
                    if value is not None})
    return payload


def _stage_config(ctx: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    config = copy.deepcopy(ctx["config"])
    config.setdefault("inputs", {}).setdefault("payload", {}).update(
        _resolved_inputs(ctx)
    )
    if state.get("targets"):
        config["inputs"]["payload"]["targets"] = state["targets"]
    config["inputs"]["payload"]["output_folder"] = str(ctx["output_folder"])
    return config


def run_stage_script(
    ctx: dict[str, Any],
    state: dict[str, Any],
    script: str,
    payload: dict[str, Any],
    *,
    timeout: int | None = 900,
) -> dict[str, Any]:
    """Run one bundled native stage with the resolved worker configuration."""
    run_dir = Path(ctx["run_dir"])
    message = run_dir / f"{script}.message.json"
    message.write_text(json.dumps({"body": payload}), encoding="utf-8")
    environment = dict(os.environ)
    bundled_source = Path(__file__).resolve().parents[1]
    if not (bundled_source / "biotarget" / "pipeline.py").is_file():
        raise RuntimeError(
            "Bundled BioTarget package is missing from the staged payload: "
            f"{bundled_source}"
        )
    environment["BIOTARGET_SOURCE_DIR"] = str(bundled_source)
    environment.update(
        {
            "MN_MESSAGE_FILE": str(message),
            "MN_RUN_DIR": str(run_dir),
            "MN_BLUEPRINT_CONFIG_JSON": json.dumps(_stage_config(ctx, state)),
            "MN_SCIENCE_FAKE_MODE": "1"
            if str(ctx["config"].get("mode") or "").lower()
            in {"fake", "mock"}
            else "0",
        }
    )
    # The continuous service emits the DockerWorker liveness beacon on stdout.
    # Capturing it would make a model-loading service look idle to the runtime.
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
    state = read_discovery_state(ctx)
    inputs = _resolved_inputs(ctx)
    publish_inputs(ctx, inputs)
    targets = inputs.get("targets")
    if targets is not None and not isinstance(targets, list):
        raise ValueError("Protein targets must be a list of UniProt identifiers")
    if targets:
        selected = []
        for target in targets:
            protein_id = target.get("protein_id") if isinstance(target, dict) else None
            if not isinstance(protein_id, str) or not re.fullmatch(r"[A-Z][A-Z0-9]{5}(?:[A-Z0-9]{4})?(?:-[1-9][0-9]*)?", protein_id):
                raise ValueError("Each provided target requires a UniProt protein_id")
            gene = target.get("gene")
            if not isinstance(gene, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", gene):
                raise ValueError("Each provided target requires a gene symbol without path characters")
            selected.append({key: target[key] for key in ("protein_id", "gene") if key in target})
        state.update({"targets": selected, "disease": inputs.get("disease") or "",
                      "target_source": "provided_protein_targets"})
    else:
        disease = inputs.get("disease")
        if not isinstance(disease, str) or not disease.strip():
            raise ValueError("Provide protein targets or a disease name for target discovery")
        result = run_stage_script(ctx, state, "stage_a.py", {"disease": disease.strip()})
        state.update({"disease": disease.strip(), "targets": result.get("targets") or [],
                      "target_source": "open_targets_disease_associations"})
    write_discovery_state(ctx, state)
    return {"target_count": len(state["targets"])}


def generate_structures(ctx: dict[str, Any], **_options: Any) -> dict[str, Any]:
    state = read_discovery_state(ctx)
    result = run_stage_script(
        ctx,
        state,
        "stage_b.py",
        {
            "disease": state.get("disease") or "",
            "targets": state.get("targets") or [],
        },
    )
    state["structures"] = result.get("structures") or []
    write_discovery_state(ctx, state)
    return {"structure_count": len(state["structures"])}


def evaluate_binding(ctx: dict[str, Any], **_options: Any) -> dict[str, Any]:
    state = read_discovery_state(ctx)
    result = run_stage_script(
        ctx,
        state,
        "stage_d.py",
        {"reports": state.get("service_reports") or []},
    )
    state["evaluations"] = result.get("evaluations") or []
    write_discovery_state(ctx, state)
    return {"evaluation_count": len(state["evaluations"])}
