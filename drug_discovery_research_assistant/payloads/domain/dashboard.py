"""Safe dashboard projection for the continuous discovery workflow."""

from __future__ import annotations

import html
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any


TERMINAL_FAILURE_EVENTS = {
    "workflow_step_failed": "Failed",
    "blueprint_phase_failed": "Failed",
}
TERMINAL_SUCCESS_EVENTS = {
    "workflow_step_completed": "Complete",
    "blueprint_phase_completed": "Complete",
}
RUNNING_EVENTS = {
    "workflow_step_attempt_started": "Running",
    "workflow_step_started": "Running",
    "blueprint_phase_started": "Running",
}


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _items(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def workflow_steps(config: Mapping[str, Any]) -> list[dict[str, str]]:
    web_ui = _mapping(config.get("web_ui"))
    steps = []
    for item in _items(web_ui.get("workflow_steps")):
        step_id = str(item.get("id") or "").strip()
        if not step_id:
            continue
        label = str(item.get("label") or step_id.replace("_", " ").title()).strip()
        steps.append({"id": step_id, "label": label})
    return steps


def cycle_steps(config: Mapping[str, Any]) -> list[dict[str, str]]:
    service = _mapping(config.get("service"))
    steps = []
    for item in _items(service.get("cycle_steps")):
        step_id = str(item.get("id") or "").strip()
        if not step_id:
            continue
        label = str(item.get("label") or step_id.replace("_", " ").title()).strip()
        steps.append({"id": step_id, "label": label})
    return steps


def workflow_metric_keys(config: Mapping[str, Any]) -> list[str]:
    return [
        f"Step {index} — {step['label']}"
        for index, step in enumerate(workflow_steps(config), start=1)
    ]


def cycle_metric_keys(config: Mapping[str, Any]) -> list[str]:
    return [f"Cycle — {step['label']}" for step in cycle_steps(config)]


def _event_step_id(
    event: Mapping[str, Any], known_step_ids: set[str]
) -> str:
    payload = _mapping(event.get("payload"))
    candidates = (
        event.get("step_id"),
        event.get("step"),
        event.get("logical_step_id"),
        event.get("node_id"),
        payload.get("step_id"),
        payload.get("step"),
        payload.get("logical_step_id"),
        payload.get("node_id"),
    )
    for candidate in candidates:
        value = str(candidate or "").strip()
        if value in known_step_ids:
            return value
        for step_id in known_step_ids:
            if value.startswith(f"{step_id}__"):
                return step_id
    return ""


def _workflow_statuses(
    *,
    config: Mapping[str, Any],
    workflow_state: Mapping[str, Any],
    service_state: Mapping[str, Any],
    final_artifact: Mapping[str, Any],
    events: list[Mapping[str, Any]],
) -> dict[str, str]:
    steps = workflow_steps(config)
    statuses = {step["id"]: "Waiting" for step in steps}
    known = set(statuses)
    for event in events:
        step_id = _event_step_id(event, known)
        if not step_id:
            continue
        event_type = str(event.get("type") or "")
        if event_type in RUNNING_EVENTS:
            statuses[step_id] = RUNNING_EVENTS[event_type]
        elif event_type in TERMINAL_SUCCESS_EVENTS:
            statuses[step_id] = TERMINAL_SUCCESS_EVENTS[event_type]
        elif event_type in TERMINAL_FAILURE_EVENTS:
            statuses[step_id] = TERMINAL_FAILURE_EVENTS[event_type]
        elif event_type == "workflow_step_partial":
            statuses[step_id] = "Partial"
        elif event_type == "workflow_step_skipped":
            statuses[step_id] = "Skipped"

    durable_completion = {
        "target_discovery": "targets" in workflow_state,
        "structure_generation": "structures" in workflow_state,
        "binding_evaluation": "evaluations" in workflow_state,
        "ranking_reporting": bool(final_artifact),
    }
    service_status = str(service_state.get("status") or "").lower()
    if "candidate_generation" in statuses:
        if service_status in {"starting", "running"}:
            statuses["candidate_generation"] = "Running"
        elif service_status == "failed":
            statuses["candidate_generation"] = "Failed"
        elif service_status == "stopped":
            durable_completion["candidate_generation"] = True
    for step_id, complete in durable_completion.items():
        if complete and statuses.get(step_id) != "Failed":
            statuses[step_id] = "Complete"
    return statuses


def _cycle_statuses(
    config: Mapping[str, Any], cycle_progress: Mapping[str, Any]
) -> tuple[list[dict[str, str]], dict[str, str]]:
    progress_steps: list[dict[str, str]] = []
    for item in _items(cycle_progress.get("steps")):
        step_id = str(item.get("id") or "").strip()
        if not step_id:
            continue
        progress_steps.append(
            {
                "id": step_id,
                "label": str(
                    item.get("label") or step_id.replace("_", " ").title()
                ).strip(),
                "status": str(item.get("status") or "Waiting").strip(),
            }
        )
    configured_steps = cycle_steps(config)
    steps = configured_steps or progress_steps
    progress_status = {step["id"]: step["status"] for step in progress_steps}
    statuses = {
        step["id"]: progress_status.get(step["id"], "Waiting") for step in steps
    }
    return steps, statuses


def _public_events(
    events: list[Mapping[str, Any]],
    *,
    workflow_labels: Mapping[str, str],
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    known = set(workflow_labels)
    for event in events[-50:]:
        step_id = _event_step_id(event, known)
        event_type = str(event.get("type") or "Runtime event")
        summary = (
            f"{workflow_labels[step_id]}: {event_type.replace('_', ' ')}"
            if step_id
            else event_type.replace("_", " ")
        )
        rows.append(
            {
                "type": event_type.replace("_", " ").title(),
                "summary": " ".join(summary.split())[:500],
                "timestamp": str(event.get("timestamp") or event.get("ts") or "")[
                    :80
                ],
            }
        )
    return rows


def _molecule_state(value: Mapping[str, Any]) -> dict[str, Any]:
    status = str(value.get("status") or "waiting").strip().lower()
    if status not in {"ready", "waiting", "unavailable", "disabled"}:
        status = "unavailable"
    try:
        cycle = max(int(value.get("cycle_id") or 0), 0) + 1
    except (TypeError, ValueError):
        cycle = 1
    result: dict[str, Any] = {
        "status": status,
        "cycle": cycle,
    }
    if status == "ready":
        result.update(
            {
                "candidate_id": str(value.get("candidate_id") or "Leading candidate")[
                    :160
                ],
                "smiles": str(value.get("smiles") or "")[:2048],
                "renderer": str(value.get("renderer") or "2d_svg")[:80],
                "image_url": (
                    "/artifacts/leading_candidate.svg?cycle="
                    f"{cycle - 1}"
                ),
            }
        )
        for key in (
            "drugclip_score",
            "simulation_stability",
            "gnina_affinity",
            "toxicity_penalty",
        ):
            metric = value.get(key)
            if isinstance(metric, (int, float)):
                result[key] = metric
    elif status == "unavailable":
        result["detail"] = str(
            value.get("detail") or "The leading candidate could not be rendered."
        )[:300]
    return result


def discovery_dashboard_state(
    *,
    run_id: str,
    config: Mapping[str, Any],
    workflow_state: Mapping[str, Any],
    service_state: Mapping[str, Any],
    cycle_progress: Mapping[str, Any],
    molecule_preview: Mapping[str, Any],
    final_artifact: Mapping[str, Any],
    events: list[Mapping[str, Any]],
) -> dict[str, Any]:
    """Project durable run state into bounded, job-scoped UI data."""
    steps = workflow_steps(config)
    workflow_status = _workflow_statuses(
        config=config,
        workflow_state=workflow_state,
        service_state=service_state,
        final_artifact=final_artifact,
        events=events,
    )
    cycle_step_specs, cycle_status = _cycle_statuses(config, cycle_progress)
    failed = [
        label
        for label, status in (
            [(step["label"], workflow_status.get(step["id"], "Waiting")) for step in steps]
            + [
                (step["label"], cycle_status.get(step["id"], "Waiting"))
                for step in cycle_step_specs
            ]
        )
        if status == "Failed"
    ]
    running = [
        step["label"]
        for step in steps
        if workflow_status.get(step["id"]) == "Running"
    ]
    if failed:
        overall = "Needs attention"
    elif final_artifact:
        overall = "Review packet ready"
    elif running:
        overall = running[-1]
    elif any(value == "Complete" for value in workflow_status.values()):
        overall = "Advancing workflow"
    else:
        overall = "Waiting to start"

    mode = str(cycle_progress.get("mode") or config.get("mode") or "live").lower()
    mode_label = (
        "Synthetic smoke test"
        if mode in {"fake", "mock", "fake_smoke_test"}
        else "Live"
    )
    metrics: dict[str, Any] = {
        "Overall status": overall,
        "Mode": mode_label,
        "Run": run_id,
    }
    for index, step in enumerate(steps, start=1):
        metrics[f"Step {index} — {step['label']}"] = workflow_status.get(
            step["id"], "Waiting"
        )
    for step in cycle_step_specs:
        metrics[f"Cycle — {step['label']}"] = cycle_status.get(
            step["id"], "Waiting"
        )

    last_report = _mapping(service_state.get("last_report"))
    counts = _mapping(cycle_progress.get("counts"))
    metrics.update(
        {
            "Current cycle": (
                int(cycle_progress.get("cycle_id") or 0) + 1
                if cycle_progress
                else "Waiting"
            ),
            "Completed cycles": int(service_state.get("completed_cycles") or 0),
            "Targets": int(
                counts.get("targets")
                or last_report.get("target_count")
                or len(_items(workflow_state.get("targets")))
            ),
            "Candidates": int(
                counts.get("candidates") or last_report.get("candidate_count") or 0
            ),
            "DrugCLIP screens": int(
                counts.get("screens") or last_report.get("screen_count") or 0
            ),
            "Simulations": int(
                counts.get("simulations")
                or last_report.get("simulation_count")
                or 0
            ),
            "Last update": str(
                cycle_progress.get("updated_at")
                or service_state.get("updated_at")
                or service_state.get("stopped_at")
                or "Waiting"
            )[:80],
        }
    )
    warning = (
        f"Failed phase: {failed[0]}. Inspect the run logs before retrying."
        if failed
        else (
            "This run uses synthetic science adapters and is not scientific evidence."
            if mode_label == "Synthetic smoke test"
            else "Computational hypotheses only; human scientific review is required."
        )
    )
    labels = {step["id"]: step["label"] for step in steps}
    public_events = _public_events(events, workflow_labels=labels)
    active_cycle = next(
        (
            step
            for step in cycle_step_specs
            if cycle_status.get(step["id"]) in {"Running", "Failed"}
        ),
        None,
    )
    if active_cycle:
        public_events.append(
            {
                "type": "Cycle Progress",
                "summary": (
                    f"Cycle {int(cycle_progress.get('cycle_id') or 0) + 1}: "
                    f"{active_cycle['label']} is "
                    f"{cycle_status[active_cycle['id']].lower()}."
                ),
                "timestamp": str(cycle_progress.get("updated_at") or "")[:80],
            }
        )
    return {
        "metrics": metrics,
        "molecule": _molecule_state(molecule_preview),
        "warning": warning,
        "events": public_events[-50:],
    }


def _read_json_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _read_event_tail(path: Path, *, limit: int = 100) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines()[-limit:]:
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                rows.append(value)
    except OSError:
        return []
    return rows


def render_static_dashboard(state: Mapping[str, Any]) -> str:
    """Render a self-contained, script-free result page for the runtime proxy."""

    metrics = _mapping(state.get("metrics"))
    molecule = _mapping(state.get("molecule"))
    events = _items(state.get("events"))
    metric_rows = "".join(
        "<tr><th>" + html.escape(str(key)) + "</th><td>"
        + html.escape(str(value)) + "</td></tr>"
        for key, value in metrics.items()
    )
    score_rows = "".join(
        "<tr><th>" + html.escape(label) + "</th><td>"
        + html.escape(str(molecule.get(key, "—"))) + "</td></tr>"
        for key, label in (
            ("drugclip_score", "DrugCLIP"),
            ("simulation_stability", "Stability"),
            ("gnina_affinity", "GNINA affinity"),
            ("toxicity_penalty", "Toxicity penalty"),
        )
    )
    event_rows = "".join(
        "<li><strong>" + html.escape(str(event.get("type") or "Event"))
        + "</strong> — " + html.escape(str(event.get("summary") or ""))
        + " <time>" + html.escape(str(event.get("timestamp") or ""))
        + "</time></li>"
        for event in events[-50:]
    )
    molecule_markup = (
        '<img src="leading_candidate.svg" alt="Two-dimensional structure of the leading computational candidate">'
        if molecule.get("status") == "ready"
        else "<p>The leading molecule preview is unavailable.</p>"
    )
    warning = html.escape(str(state.get("warning") or ""))
    candidate_id = html.escape(str(molecule.get("candidate_id") or "Awaiting ranking"))
    smiles = html.escape(str(molecule.get("smiles") or "—"))
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Drug Discovery Research Assistant</title><style>
body{{margin:0;background:#eef2ec;color:#15241f;font:14px/1.5 system-ui,sans-serif}}main{{max-width:1180px;margin:auto;padding:28px 20px}}h1{{font-size:32px}}section{{background:#fff;border:1px solid #d9e1dc;border-radius:16px;padding:20px;margin:16px 0}}.grid{{display:grid;grid-template-columns:1fr 1fr;gap:16px}}table{{width:100%;border-collapse:collapse}}th,td{{padding:9px;border-bottom:1px solid #edf1ee;text-align:left;vertical-align:top}}th{{color:#64746e}}img{{display:block;width:100%;height:360px;object-fit:contain;background:#f8faf6}}code{{overflow-wrap:anywhere}}.warning{{background:#fff0d7;border-color:#ead0a5}}time{{color:#64746e}}@media(max-width:760px){{.grid{{grid-template-columns:1fr}}}}
</style></head><body><main><h1>Drug Discovery Research Assistant</h1>
<section class="warning"><strong>Scientific review boundary</strong><p>{warning}</p></section>
<div class="grid"><section><h2>Leading candidate</h2>{molecule_markup}<h3>{candidate_id}</h3><code>{smiles}</code><table>{score_rows}</table></section>
<section><h2>Run and workflow</h2><table>{metric_rows}</table></section></div>
<section><h2>Recent progress</h2><ol>{event_rows or '<li>No recorded events.</li>'}</ol></section>
</main></body></html>\n"""


def publish_static_dashboard(ctx: Mapping[str, Any]) -> dict[str, Any]:
    """Write the optional result UI; callers decide whether failures are fatal."""

    run_dir = Path(str(ctx["run_dir"]))
    output_dir = Path(str(ctx["output_folder"]))
    config = _mapping(ctx.get("config"))
    state = discovery_dashboard_state(
        run_id=str(ctx.get("run_id") or run_dir.name),
        config=config,
        workflow_state=_read_json_object(
            run_dir / "workflow_state" / "drug_discovery_state.json"
        ),
        service_state=_read_json_object(run_dir / "service_state.json"),
        cycle_progress=_read_json_object(run_dir / "cycle_progress.json"),
        molecule_preview=_read_json_object(run_dir / "leading_candidate.json"),
        final_artifact=_read_json_object(run_dir / "final_artifact.json"),
        events=_read_event_tail(run_dir / "events.jsonl"),
    )
    rendered = render_static_dashboard(state)
    handle: dict[str, Any] = {}
    for root in (run_dir, output_dir):
        web_dir = root / "web"
        web_dir.mkdir(parents=True, exist_ok=True)
        page = web_dir / "index.html"
        page.write_text(rendered, encoding="utf-8")
        source_svg = run_dir / "leading_candidate.svg"
        if source_svg.is_file():
            (web_dir / "leading_candidate.svg").write_bytes(source_svg.read_bytes())
        current = {
            "kind": "output",
            "adapter": "static_html",
            "url": page.resolve().as_uri(),
            "title": "Drug Discovery Research Assistant",
            "path": str(page),
            "metadata": {"renderer": "static_html", "optional": True},
        }
        (root / "web_ui.json").write_text(
            json.dumps(current, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        if root == run_dir:
            handle = current
    return handle
