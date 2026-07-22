#!/usr/bin/env python3.11
"""Continuous, review-only discovery service with native-worker dispatch contracts.

Live runs deliberately require configured external scientific adapters.  Fake mode
is retained solely for smoke tests and emits explicit synthetic provenance.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import signal
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from threading import Event
from typing import Any


STOP_REQUESTED = Event()
REQUIRED_ADAPTERS = ("candidate_generator", "folding", "drugclip", "simulation")
FAKE_SMILES = (
    "CC(=O)OC1=CC=CC=C1C(=O)O",
    "CN1C=NC2=C1C(=O)N(C(=O)N2C)C",
    "C1=CC=C(C=C1)S(=O)(=O)N",
    "CCOc1ccc(CC(=O)N(C)O)cc1",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def request_stop(*_: Any) -> None:
    STOP_REQUESTED.set()


def json_dump(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def resolve_output_folder(config: dict[str, Any], run_dir: Path) -> Path:
    """Resolve the user-facing output directory for both local and hosted runs."""
    runtime_output = os.environ.get("MN_JOB_OUTPUT_DIR")
    if runtime_output:
        return Path(os.path.expandvars(runtime_output)).expanduser()

    inputs = config.get("inputs") if isinstance(config.get("inputs"), dict) else {}
    payload = inputs.get("payload") if isinstance(inputs.get("payload"), dict) else {}
    outputs = config.get("outputs") if isinstance(config.get("outputs"), dict) else {}
    configured_output = payload.get("output_folder") or outputs.get("folder_path") or outputs.get("output_folder")
    if configured_output:
        return Path(os.path.expandvars(str(configured_output))).expanduser()
    return run_dir / "outputs"


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def is_fake(config: dict[str, Any]) -> bool:
    execution = config.get("execution") if isinstance(config.get("execution"), dict) else {}
    llm = config.get("llm") if isinstance(config.get("llm"), dict) else {}
    return (
        bool(execution.get("fake_science_adapters"))
        or str(config.get("mode") or "").lower() in {"fake", "mock"}
        or str(llm.get("mode") or "").lower() in {"fake", "mock"}
    )


def validate_live_adapters(config: dict[str, Any]) -> None:
    if is_fake(config):
        return
    missing = [name for name in REQUIRED_ADAPTERS if not _command(config.get(name))]
    if missing:
        raise RuntimeError(
            "Live continuous discovery requires configured native adapter commands for "
            + ", ".join(missing)
            + ". Configure them in config/overwrite.json or the runtime input; fake adapters are only allowed in explicit fake mode."
        )
    distribution = config.get("cluster_distribution") if isinstance(config.get("cluster_distribution"), dict) else {}
    if distribution.get("enabled") and not _command(distribution.get("dispatch_command")):
        raise RuntimeError(
            "Cluster distribution is enabled but no native dispatch_command is configured. "
            "Provide a command that accepts a JSON job specification on stdin and returns a JSON result."
        )


def _command(value: Any) -> list[str]:
    if isinstance(value, dict):
        value = value.get("command")
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _expand_command(command: list[str], values: dict[str, Any]) -> list[str]:
    return [os.path.expandvars(token.format(**values)) for token in command]


def _parse_command_result(process: subprocess.CompletedProcess[str], output_path: Path) -> Any:
    if output_path.exists():
        return json.loads(output_path.read_text(encoding="utf-8"))
    stdout = process.stdout.strip()
    if not stdout:
        raise RuntimeError("adapter produced no JSON stdout or output file")
    return json.loads(stdout)


def run_native_adapter(
    adapter_name: str,
    config: dict[str, Any],
    request: dict[str, Any],
    work_dir: Path,
    pool: str,
) -> Any:
    """Execute one declared scientific adapter or submit it to the cluster dispatcher."""
    service_root = Path(__file__).resolve().parent.parent
    adapter_environment = dict(os.environ)
    bundled_source = service_root.parent
    if not (bundled_source / "biotarget" / "pipeline.py").is_file():
        raise RuntimeError(f"Bundled BioTarget package is missing from the staged payload: {bundled_source}")
    adapter_environment["BIOTARGET_SOURCE_DIR"] = str(bundled_source)
    output_path = work_dir / f"{adapter_name}.json"
    request_path = work_dir / f"{adapter_name}.request.json"
    # BioTarget adapters receive their model and source configuration in the
    # same immutable job envelope that is dispatched across native workers.
    request = {
        **request,
        "biotarget": config.get("biotarget") if isinstance(config.get("biotarget"), dict) else {},
        "drugclip": config.get("drugclip") if isinstance(config.get("drugclip"), dict) else {},
        "service": config.get("service") if isinstance(config.get("service"), dict) else {},
    }
    json_dump(request_path, request)
    distribution = config.get("cluster_distribution") if isinstance(config.get("cluster_distribution"), dict) else {}
    command = _command(config.get(adapter_name))
    values = {
        "input_path": str(request_path),
        "output_path": str(output_path),
        "work_dir": str(work_dir),
        "pool": pool,
        "cycle_id": request.get("cycle_id", ""),
        "target_id": request.get("target", {}).get("protein_id", ""),
        "structure_path": request.get("structure", {}).get("path", ""),
    }
    if distribution.get("enabled"):
        dispatch = _expand_command(_command(distribution.get("dispatch_command")), values)
        job = {"adapter": adapter_name, "pool": pool, "command": _expand_command(command, values), "request_path": str(request_path), "output_path": str(output_path), "request": request}
        process = subprocess.run(dispatch, input=json.dumps(job), text=True, capture_output=True, check=False, cwd=service_root, env=adapter_environment, timeout=int(distribution.get("dispatch_timeout_seconds", 1800)))
        if process.returncode:
            raise RuntimeError(f"cluster dispatch failed for {adapter_name}: {process.stderr.strip()}")
        dispatched = json.loads(process.stdout) if process.stdout.strip() else {}
        if isinstance(dispatched, dict) and dispatched.get("result") is not None:
            return dispatched["result"]
        if output_path.exists():
            return json.loads(output_path.read_text(encoding="utf-8"))
        raise RuntimeError(f"cluster dispatch for {adapter_name} returned no result")
    process = subprocess.run(_expand_command(command, values), text=True, capture_output=True, check=False, cwd=service_root, env=adapter_environment, timeout=int((config.get(adapter_name) or {}).get("timeout_seconds", 1800)))
    if process.returncode:
        stderr = process.stderr.strip()
        stdout = process.stdout.strip()
        diagnostics = stderr
        if stdout:
            diagnostics = f"{diagnostics}\nstdout (tail): {stdout[-4000:]}".strip()
        raise RuntimeError(f"native {adapter_name} adapter failed: {diagnostics}")
    return _parse_command_result(process, output_path)


def fake_candidates(cycle_id: int) -> list[dict[str, Any]]:
    offset = cycle_id % len(FAKE_SMILES)
    return [{"candidate_id": f"fake-{cycle_id}-{index}", "smiles": FAKE_SMILES[(offset + index) % len(FAKE_SMILES)], "provenance": "fake_smoke_test"} for index in range(min(3, len(FAKE_SMILES)))]


def fake_fold(target: dict[str, Any], work_dir: Path) -> dict[str, Any]:
    target_id = str(target.get("protein_id") or target.get("gene") or "TARGET")
    work_dir.mkdir(parents=True, exist_ok=True)
    pdb_path = work_dir / f"{target_id}.pdb"
    pdb_path.write_text("HEADER    SYNTHETIC SMOKE-TEST STRUCTURE\nEND\n", encoding="utf-8")
    return {"target": target, "path": str(pdb_path), "provenance": "fake_smoke_test"}


def fake_score(structure: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    seed = f"{structure.get('path')}:{candidate.get('smiles')}".encode("utf-8")
    score = round((int(hashlib.sha256(seed).hexdigest()[:8], 16) % 10000) / 10000, 4)
    return {"candidate": candidate, "structure": structure, "drugclip_score": score, "provenance": "fake_smoke_test"}


def fake_simulation(screen: dict[str, Any]) -> dict[str, Any]:
    score = float(screen.get("drugclip_score") or 0)
    return {**screen, "simulation_stability": round(0.4 + score * 0.5, 4), "simulation_status": "synthetic_smoke_test"}


def targets_from_config(config: dict[str, Any]) -> list[dict[str, Any]]:
    payload = ((config.get("inputs") or {}).get("payload") or {}) if isinstance(config.get("inputs"), dict) else {}
    targets = payload.get("targets") or payload.get("target_profile", {}).get("targets")
    if isinstance(targets, list) and targets:
        return [item if isinstance(item, dict) else {"protein_id": str(item), "gene": str(item)} for item in targets]
    profile = payload.get("disease_or_target_profile") or payload.get("disease") or "UNSPECIFIED_TARGET"
    return [{"protein_id": str(profile), "gene": str(profile)}]


def design_prompt_from_config(config: dict[str, Any]) -> str:
    payload = ((config.get("inputs") or {}).get("payload") or {}) if isinstance(config.get("inputs"), dict) else {}
    for key in ("design_prompt", "disease_or_target_profile", "disease"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return "the configured therapeutic target"


def _parallel(items: list[Any], max_workers: int, fn: Any) -> list[Any]:
    if not items:
        return []
    results: list[Any] = []
    with ThreadPoolExecutor(max_workers=max(1, min(max_workers, len(items)))) as executor:
        futures = [executor.submit(fn, item) for item in items]
        for future in as_completed(futures):
            results.append(future.result())
    return results


def job_artifact_dir(root: Path, prefix: str, *parts: Any) -> Path:
    """Return a collision-free per-job directory for concurrent adapter calls."""
    readable = "-".join(str(part or "unknown") for part in parts)
    digest = hashlib.sha256(readable.encode("utf-8")).hexdigest()[:12]
    safe = "".join(char if char.isalnum() or char in "-_" else "_" for char in readable)[:72]
    return root / prefix / f"{safe}-{digest}"


def screen_sort_key(item: dict[str, Any]) -> tuple[float, str, str]:
    candidate = item.get("candidate") if isinstance(item.get("candidate"), dict) else {}
    structure = item.get("structure") if isinstance(item.get("structure"), dict) else {}
    target = structure.get("target") if isinstance(structure.get("target"), dict) else {}
    return (
        -float(item.get("drugclip_score", float("-inf"))),
        str(candidate.get("candidate_id") or candidate.get("smiles") or ""),
        str(target.get("protein_id") or target.get("gene") or structure.get("path") or ""),
    )


def simulation_sort_key(item: dict[str, Any]) -> tuple[float, float, str]:
    candidate = item.get("candidate") if isinstance(item.get("candidate"), dict) else {}
    return (
        -float(item.get("simulation_stability", float("-inf"))),
        -float(item.get("drugclip_score", float("-inf"))),
        str(candidate.get("candidate_id") or candidate.get("smiles") or ""),
    )


def run_cycle(config: dict[str, Any], run_dir: Path, cycle_id: int) -> dict[str, Any]:
    cycle_dir = run_dir / "cycles" / f"cycle-{cycle_id:06d}"
    cycle_dir.mkdir(parents=True, exist_ok=True)
    output_folder = resolve_output_folder(config, run_dir)
    pools = ((config.get("cluster_distribution") or {}).get("worker_pools") or {})
    parallelism = ((config.get("service") or {}).get("parallelism") or {})
    targets = targets_from_config(config)
    fake = is_fake(config)
    if fake:
        candidates = fake_candidates(cycle_id)
    else:
        generated = run_native_adapter("candidate_generator", config, {"cycle_id": cycle_id, "targets": targets, "design_prompt": design_prompt_from_config(config)}, cycle_dir / "generation", str(pools.get("generation", "science-generation")))
        candidates = generated.get("candidates") if isinstance(generated, dict) else generated
        if not isinstance(candidates, list) or not candidates:
            raise RuntimeError("candidate_generator returned no candidates")
    json_dump(cycle_dir / "generated_candidates.json", candidates)
    json_dump(
        output_folder / "candidates.json",
        {
            "schema_version": "mn.blueprint.staged_candidates.v1",
            "cycle_id": cycle_id,
            "generated_at": utc_now(),
            "mode": "fake_smoke_test" if fake else "live",
            "candidate_count": len(candidates),
            "candidates": candidates,
            "review_boundary": "Computational hypotheses only; human scientific review is required.",
        },
    )

    def fold_target(target: dict[str, Any]) -> dict[str, Any]:
        if fake:
            return fake_fold(target, cycle_dir / "folding")
        target_id = target.get("protein_id") or target.get("gene") or "target"
        result = run_native_adapter("folding", config, {"cycle_id": cycle_id, "target": target}, job_artifact_dir(cycle_dir, "folding", target_id), str(pools.get("folding", "science-folding")))
        return result if isinstance(result, dict) else {"target": target, "result": result}

    structures = _parallel(targets, int(parallelism.get("folding_workers", 2)), fold_target)
    json_dump(cycle_dir / "folding_results.json", structures)

    def screen_structure(structure: dict[str, Any]) -> list[dict[str, Any]]:
        if fake:
            return [fake_score(structure, candidate) for candidate in candidates]
        target = structure.get("target") if isinstance(structure.get("target"), dict) else {}
        target_id = target.get("protein_id") or target.get("gene") or structure.get("path") or "target"
        result = run_native_adapter(
            "drugclip",
            config,
            {
                "cycle_id": cycle_id,
                "design_prompt": design_prompt_from_config(config),
                "structure": structure,
                "candidates": candidates,
            },
            job_artifact_dir(cycle_dir, "drugclip", target_id),
            str(pools.get("drugclip", "science-drugclip")),
        )
        screens = result.get("screens") if isinstance(result, dict) else None
        if not isinstance(screens, list) or len(screens) != len(candidates):
            raise RuntimeError("DrugClip batch adapter returned incomplete target-candidate scores.")
        return [item for item in screens if isinstance(item, dict)]

    screened_groups = _parallel(structures, int(parallelism.get("drugclip_workers", 4)), screen_structure)
    screens = [screen for group in screened_groups for screen in group]
    screens.sort(key=screen_sort_key)
    top_k = int((config.get("service") or {}).get("simulation_top_k", 16))
    selected = screens[:top_k]
    json_dump(cycle_dir / "drugclip_screening.json", {"all_results": screens, "selected": selected})

    def simulate(screen_result: dict[str, Any]) -> dict[str, Any]:
        if fake:
            return fake_simulation(screen_result)
        structure = screen_result.get("structure") if isinstance(screen_result.get("structure"), dict) else {}
        target = structure.get("target") if isinstance(structure.get("target"), dict) else {}
        target_id = target.get("protein_id") or target.get("gene") or structure.get("path") or "target"
        candidate = screen_result.get("candidate") if isinstance(screen_result.get("candidate"), dict) else {}
        candidate_id = candidate.get("candidate_id") or candidate.get("smiles") or "candidate"
        result = run_native_adapter("simulation", config, {"cycle_id": cycle_id, "design_prompt": design_prompt_from_config(config), "screen": screen_result}, job_artifact_dir(cycle_dir, "simulation", target_id, candidate_id), str(pools.get("simulation", "science-simulation")))
        return result if isinstance(result, dict) else {"screen": screen_result, "result": result}

    simulations = _parallel(selected, int(parallelism.get("simulation_workers", 4)), simulate)
    simulations.sort(key=simulation_sort_key)
    report = {
        "schema_version": "mn.blueprint.continuous_discovery_cycle.v1",
        "cycle_id": cycle_id,
        "started_at": utc_now(),
        "mode": "fake_smoke_test" if fake else "live",
        "target_count": len(targets),
        "candidate_count": len(candidates),
        "screen_count": len(screens),
        "simulation_count": len(simulations),
        "top_candidates": simulations[: min(20, len(simulations))],
        "review_boundary": "Computational hypotheses only; no wet-lab, clinical, regulatory, or external system action is authorized.",
    }
    json_dump(cycle_dir / "simulation_results.json", simulations)
    json_dump(cycle_dir / "cycle_report.json", report)
    json_dump(output_folder / "latest_cycle_report.json", report)
    return report


def run_service(config: dict[str, Any], run_dir: Path) -> dict[str, Any]:
    validate_live_adapters(config)
    service = config.get("service") if isinstance(config.get("service"), dict) else {}
    output_folder = resolve_output_folder(config, run_dir)
    json_dump(
        output_folder / "service_status.json",
        {
            "schema_version": "mn.blueprint.continuous_discovery_status.v1",
            "status": "starting",
            "started_at": utc_now(),
            "run_dir": str(run_dir),
            "output_folder": str(output_folder),
            "artifacts": ["candidates.json", "latest_cycle_report.json", "service_status.json"],
            "review_boundary": "Computational hypotheses only; human scientific review is required.",
        },
    )
    # The native worker wrapper supplies MN_RUN_DIR.  Resolve the documented
    # placeholder here as well so direct/native invocations use the supplied
    # run directory instead of accidentally creating a literal ${MN_RUN_DIR}
    # path in the current working directory.
    stop_file_value = str(service.get("stop_file") or run_dir / "STOP")
    stop_file_value = stop_file_value.replace("${MN_RUN_DIR}", str(run_dir))
    stop_file = Path(os.path.expandvars(stop_file_value)).expanduser()
    max_cycles = service.get("max_cycles")
    if max_cycles is not None:
        max_cycles = int(max_cycles)
    cycle_interval = max(0.1, float(service.get("cycle_interval_seconds", 15)))
    state_path = run_dir / "service_state.json"
    reports: list[dict[str, Any]] = []
    cycle_id = 0
    while not STOP_REQUESTED.is_set() and not stop_file.exists():
        report = run_cycle(config, run_dir, cycle_id)
        reports.append(report)
        state = {"schema_version": "mn.blueprint.continuous_discovery_service.v1", "status": "running", "cycle_id": cycle_id, "updated_at": utc_now(), "stop_file": str(stop_file), "last_report": report}
        json_dump(state_path, state)
        json_dump(
            output_folder / "service_status.json",
            {
                "schema_version": "mn.blueprint.continuous_discovery_status.v1",
                "status": "running",
                "updated_at": utc_now(),
                "run_dir": str(run_dir),
                "output_folder": str(output_folder),
                "completed_cycles": cycle_id + 1,
                "last_cycle_id": cycle_id,
                "artifacts": ["candidates.json", "latest_cycle_report.json", "service_status.json"],
                "review_boundary": "Computational hypotheses only; human scientific review is required.",
            },
        )
        cycle_id += 1
        if max_cycles is not None and cycle_id >= max_cycles:
            break
        STOP_REQUESTED.wait(cycle_interval)
    final = {"schema_version": "mn.blueprint.continuous_discovery_service.v1", "status": "stopped", "stopped_at": utc_now(), "completed_cycles": cycle_id, "stop_reason": "signal" if STOP_REQUESTED.is_set() else "stop_file" if stop_file.exists() else "max_cycles", "reports": reports[-10:]}
    json_dump(state_path, final)
    json_dump(
        output_folder / "service_status.json",
        {
            "schema_version": "mn.blueprint.continuous_discovery_status.v1",
            **final,
            "run_dir": str(run_dir),
            "output_folder": str(output_folder),
            "artifacts": ["candidates.json", "latest_cycle_report.json", "service_status.json"],
            "review_boundary": "Computational hypotheses only; human scientific review is required.",
        },
    )
    return final


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run the continuous native DrugCLIP discovery service.")
    parser.add_argument("--config", required=True, help="Resolved blueprint config JSON file")
    parser.add_argument("--run-dir", required=True, help="Run directory for service artifacts")
    args = parser.parse_args(argv)
    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    result = run_service(load_json(Path(args.config)), Path(args.run_dir))
    print(json.dumps(result))


if __name__ == "__main__":
    main()
