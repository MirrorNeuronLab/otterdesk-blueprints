#!/usr/bin/env python3.11
"""Serve a job-scoped, read-only discovery progress dashboard."""

from __future__ import annotations

import importlib.util
import json
import os
import signal
import threading
import urllib.parse
from collections import deque
from pathlib import Path
from typing import Any, Callable

from mn_web_ui_skill import (
    JsonRenderApplication,
    JsonRenderServer,
    write_service_artifacts,
)


SCRIPT_DIR = Path(__file__).resolve().parent
WEB_UI_NODE_ID = "drug_discovery_web_ui"
WEB_UI_SERVICE_NAME = "drug-discovery-progress"


def _load_dashboard_module() -> Any:
    for ancestor in (SCRIPT_DIR, *SCRIPT_DIR.parents):
        module_path = ancestor / "domain" / "dashboard.py"
        if not module_path.is_file():
            continue
        spec = importlib.util.spec_from_file_location(
            "drug_discovery_dashboard", module_path
        )
        if spec is None or spec.loader is None:
            break
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    raise RuntimeError("drug discovery dashboard projection is unavailable")


dashboard = _load_dashboard_module()


def load_config() -> dict[str, Any]:
    try:
        value = json.loads(os.environ.get("MN_BLUEPRINT_CONFIG_JSON", "{}"))
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def configured_run_id() -> str:
    return str(
        os.environ.get("MN_RUN_ID") or os.environ.get("MN_JOB_ID") or "run"
    ).strip()


def configured_run_dir() -> Path:
    explicit = str(os.environ.get("MN_RUN_DIR") or "").strip()
    if explicit:
        return Path(explicit).expanduser()
    root = str(os.environ.get("MN_RUNS_ROOT") or "").strip()
    run_id = configured_run_id()
    return Path(root).expanduser() / run_id if root else Path.cwd() / "runs" / run_id


def configured_job_data_dir(job_id: str) -> Path:
    value = str(os.environ.get("MN_JOB_DATA_DIR") or "").strip()
    if not value:
        raise RuntimeError(
            "Drug Discovery Web UI requires the job-scoped MN_JOB_DATA_DIR contract"
        )
    path = Path(value).expanduser().resolve()
    if path.name != job_id:
        raise RuntimeError("MN_JOB_DATA_DIR must identify the direct directory for MN_JOB_ID")
    return path


def _service_config(config: dict[str, Any]) -> dict[str, Any]:
    web_ui = config.get("web_ui")
    web_ui = web_ui if isinstance(web_ui, dict) else {}
    service = web_ui.get("service")
    return service if isinstance(service, dict) else {}


def validate_public_url(value: Any) -> str:
    url = str(value or "").strip().rstrip("/")
    if not url:
        return ""
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("web_ui.service.public_url must be an absolute HTTP(S) URL")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("web_ui.service.public_url must not contain credentials")
    return url


def public_service_url(host: str, port: int, configured_url: str = "") -> str:
    explicit = validate_public_url(configured_url)
    if explicit:
        return explicit
    runtime_url = validate_public_url(
        os.environ.get("MN_BLUEPRINT_WEB_UI_BASE_URL") or ""
    )
    if runtime_url:
        return runtime_url
    wildcard = host in {"0.0.0.0", "::", "[::]"}
    advertised = str(
        os.environ.get("MN_BLUEPRINT_WEB_UI_PUBLIC_HOST")
        or os.environ.get("MN_NETWORK_ADVERTISE_HOST")
        or ""
    ).strip()
    display_host = advertised if wildcard and advertised else "127.0.0.1" if wildcard else host
    return f"http://{display_host}:{port}"


def build_ui_spec(config: dict[str, Any]) -> dict[str, Any]:
    workflow_keys = dashboard.workflow_metric_keys(config)
    cycle_keys = dashboard.cycle_metric_keys(config)
    return {
        "root": "app",
        "elements": {
            "app": {
                "type": "App",
                "props": {
                    "title": "Drug Discovery Research Assistant",
                    "subtitle": "Follow every workflow stage and each live discovery cycle.",
                    "density": "compact",
                },
                "children": ["layout"],
            },
            "layout": {
                "type": "Grid",
                "props": {},
                "children": [
                    "overview",
                    "workflow",
                    "cycle",
                    "activity",
                    "boundary",
                ],
            },
            "overview": {
                "type": "Card",
                "props": {"title": "Run overview", "span": 12},
                "children": ["overview-status"],
            },
            "overview-status": {
                "type": "LiveStatus",
                "props": {
                    "endpoint": "/ui/state",
                    "refreshMs": 1000,
                    "keys": [
                        "Overall status",
                        "Mode",
                        "Current cycle",
                        "Completed cycles",
                        "Targets",
                        "Candidates",
                        "DrugCLIP screens",
                        "Simulations",
                        "Last update",
                    ],
                },
                "children": [],
            },
            "workflow": {
                "type": "Card",
                "props": {"title": "Workflow steps", "span": 6},
                "children": ["workflow-status"],
            },
            "workflow-status": {
                "type": "LiveStatus",
                "props": {
                    "endpoint": "/ui/state",
                    "refreshMs": 1000,
                    "keys": workflow_keys,
                },
                "children": [],
            },
            "cycle": {
                "type": "Card",
                "props": {"title": "Current discovery cycle", "span": 6},
                "children": ["cycle-status"],
            },
            "cycle-status": {
                "type": "LiveStatus",
                "props": {
                    "endpoint": "/ui/state",
                    "refreshMs": 1000,
                    "keys": cycle_keys,
                },
                "children": [],
            },
            "activity": {
                "type": "Card",
                "props": {"title": "Recent progress", "span": 12},
                "children": ["event-feed"],
            },
            "event-feed": {
                "type": "EventFeed",
                "props": {"endpoint": "/ui/state", "refreshMs": 1000, "limit": 20},
                "children": [],
            },
            "boundary": {
                "type": "Card",
                "props": {"title": "Scientific review boundary", "span": 12},
                "children": ["boundary-text"],
            },
            "boundary-text": {
                "type": "Text",
                "props": {
                    "text": (
                        "All candidates and scores are computational hypotheses. "
                        "Human scientific review is required before laboratory, clinical, "
                        "regulatory, procurement, or external-system action."
                    )
                },
                "children": [],
            },
        },
    }


def read_json_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def read_event_tail(path: Path, *, limit: int = 100) -> list[dict[str, Any]]:
    if not path.is_file() or limit < 1:
        return []
    rows: deque[dict[str, Any]] = deque(maxlen=limit)
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                try:
                    value = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(value, dict):
                    rows.append(value)
    except OSError:
        return []
    return list(rows)


class DrugDiscoveryWebUIService:
    def __init__(
        self, *, run_id: str, run_dir: Path, config: dict[str, Any]
    ) -> None:
        self.run_id = run_id
        self.run_dir = run_dir
        self.config = config
        self.application = JsonRenderApplication(
            title="Drug Discovery Research Assistant",
            spec=build_ui_spec(config),
            state_provider=self.ui_state,
            actions={},
        )

    def ui_state(self) -> dict[str, Any]:
        return dashboard.discovery_dashboard_state(
            run_id=self.run_id,
            config=self.config,
            workflow_state=read_json_object(
                self.run_dir / "workflow_state" / "drug_discovery_state.json"
            ),
            service_state=read_json_object(self.run_dir / "service_state.json"),
            cycle_progress=read_json_object(self.run_dir / "cycle_progress.json"),
            final_artifact=read_json_object(self.run_dir / "final_artifact.json"),
            events=read_event_tail(self.run_dir / "events.jsonl"),
        )


def main() -> int:
    config = load_config()
    run_id = configured_run_id()
    job_id = str(os.environ.get("MN_JOB_ID") or run_id).strip()
    run_dir = configured_run_dir()
    job_data_dir = configured_job_data_dir(job_id)
    run_dir.mkdir(parents=True, exist_ok=True)
    settings = _service_config(config)
    host = str(settings.get("host") or "0.0.0.0")
    raw_port = str(os.environ.get("MN_PORT_WEB_UI") or settings.get("port") or 61020)
    try:
        port = int(raw_port)
    except (TypeError, ValueError) as error:
        raise RuntimeError("Drug Discovery Web UI requires a numeric port") from error
    if not 1 <= port <= 65535:
        raise RuntimeError("Drug Discovery Web UI port must be between 1 and 65535")
    public_url = public_service_url(
        host, port, str(settings.get("public_url") or "")
    )
    service = DrugDiscoveryWebUIService(
        run_id=run_id, run_dir=run_dir, config=config
    )
    server = JsonRenderServer(service.application, host=host, port=port)
    write_service_artifacts(
        job_data_dir,
        job_id=job_id,
        title="Drug Discovery Research Assistant",
        url=public_url,
        spec=service.application.spec,
        service_name=WEB_UI_SERVICE_NAME,
        node_id=WEB_UI_NODE_ID,
        metadata={
            "run_id": run_id,
            "listen_host": host,
            "listen_port": port,
            "state_endpoint": f"{public_url}/ui/state",
        },
    )

    def stop(_signum: int, _frame: Any) -> None:
        threading.Thread(target=server.stop, daemon=True).start()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
