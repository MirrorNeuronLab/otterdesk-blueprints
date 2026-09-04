#!/usr/bin/env python3.11
"""Serve the drug-discovery dashboard and claim its job-scoped iframe handle."""

from __future__ import annotations

import importlib.util
import json
import os
import signal
import threading
import urllib.parse
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from mn_web_ui_skill import claim_web_ui, mark_web_ui_status, resolve_web_ui_binding


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
    execution_node = str(os.environ.get("MN_EXECUTION_NODE") or "").strip()
    if wildcard and not advertised and "@" in execution_node:
        advertised = execution_node.rpartition("@")[2]
    display_host = (
        advertised if wildcard and advertised else "127.0.0.1" if wildcard else host
    )
    return f"http://{display_host}:{port}"


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

    def ui_state(self) -> dict[str, Any]:
        return dashboard.discovery_dashboard_state(
            run_id=self.run_id,
            config=self.config,
            workflow_state=read_json_object(
                self.run_dir / "workflow_state" / "drug_discovery_state.json"
            ),
            service_state=read_json_object(self.run_dir / "service_state.json"),
            cycle_progress=read_json_object(self.run_dir / "cycle_progress.json"),
            molecule_preview=read_json_object(
                self.run_dir / "leading_candidate.json"
            ),
            final_artifact=read_json_object(self.run_dir / "final_artifact.json"),
            events=read_event_tail(self.run_dir / "events.jsonl"),
        )


class DrugDiscoveryWebUIServer:
    def __init__(
        self, service: DrugDiscoveryWebUIService, *, host: str, port: int
    ) -> None:
        self.service = service
        self._server = ThreadingHTTPServer((host, port), _handler_for(service))

    @property
    def address(self) -> tuple[str, int]:
        host, port = self._server.server_address[:2]
        return str(host), int(port)

    def serve_forever(self) -> None:
        self._server.serve_forever(poll_interval=0.5)

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()


def _handler_for(
    service: DrugDiscoveryWebUIService,
) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self) -> None:  # noqa: N802
            path = urllib.parse.urlsplit(self.path).path
            if path == "/":
                self._send(dashboard_html().encode(), "text/html; charset=utf-8")
                return
            if path in {"/health", "/healthz"}:
                self._json(
                    {"status": "ok", "component": "drug-discovery-web-ui"}
                )
                return
            if path == "/ui/state":
                self._json(service.ui_state())
                return
            if path == "/artifacts/leading_candidate.svg":
                self._molecule_svg()
                return
            self._json({"error": "not found"}, status=404)

        def do_POST(self) -> None:  # noqa: N802
            self._json({"error": "read-only web UI"}, status=405)

        def _molecule_svg(self) -> None:
            try:
                body = (service.run_dir / "leading_candidate.svg").read_bytes()
            except OSError:
                self._json({"error": "molecule preview is not ready"}, status=404)
                return
            self._send(body, "image/svg+xml; charset=utf-8")

        def _json(self, value: dict[str, Any], *, status: int = 200) -> None:
            self._send(
                json.dumps(value, separators=(",", ":")).encode(),
                "application/json; charset=utf-8",
                status=status,
            )

        def _send(self, body: bytes, content_type: str, *, status: int = 200) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
                "script-src 'self' 'unsafe-inline'; connect-src 'self'",
            )
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, _format: str, *_args: Any) -> None:
            return

    return Handler


def main() -> int:
    config = load_config()
    run_id = configured_run_id()
    job_id = str(os.environ.get("MN_JOB_ID") or run_id).strip()
    run_dir = configured_run_dir()
    job_data_dir = configured_job_data_dir(job_id)
    run_dir.mkdir(parents=True, exist_ok=True)
    binding = resolve_web_ui_binding(config)
    service = DrugDiscoveryWebUIService(
        run_id=run_id, run_dir=run_dir, config=config
    )
    server = DrugDiscoveryWebUIServer(
        service, host=binding.host, port=binding.port
    )
    _bound_host, port = server.address
    settings = (
        config.get("web_ui") if isinstance(config.get("web_ui"), dict) else {}
    )
    service_settings = (
        settings.get("service")
        if isinstance(settings.get("service"), dict)
        else {}
    )
    claim_web_ui(
        job_data_dir,
        job_id=job_id,
        title="Drug Discovery Research Assistant",
        url=public_service_url(
            binding.host, port, str(service_settings.get("public_url") or "")
        ),
        service_name=WEB_UI_SERVICE_NAME,
        node_id=WEB_UI_NODE_ID,
        http_ports=[port],
        metadata={
            "run_id": run_id,
            "state_endpoint": "/ui/state",
            "molecule_artifact": "leading_candidate.svg",
        },
    )

    def stop(_signum: int, _frame: Any) -> None:
        mark_web_ui_status(
            job_data_dir,
            job_id=job_id,
            status="stopped",
            detail="The drug-discovery progress service is stopped.",
        )
        threading.Thread(target=server.stop, daemon=True).start()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    server.serve_forever()
    return 0


def dashboard_html() -> str:
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Drug Discovery Research Assistant</title>
  <style>
    :root { color-scheme: light; --canvas: #eef2ec; --panel: #fff; --ink: #15241f; --muted: #64746e; --quiet: #8a9892; --line: #d9e1dc; --line-strong: #c5d2cb; --green: #176b55; --green-soft: #dff2e9; --mint: #49c69a; --amber: #a86b16; --amber-soft: #fff0d7; --red: #a64038; --red-soft: #fbe5e2; --blue: #426a9f; --radius: 18px; --mono: "SFMono-Regular",Consolas,"Liberation Mono",monospace; }
    * { box-sizing: border-box; }
    body { margin: 0; min-width: 320px; color: var(--ink); background: radial-gradient(circle at 10% -10%,rgba(73,198,154,.15),transparent 30%),var(--canvas); font: 14px/1.5 Inter,ui-sans-serif,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; -webkit-font-smoothing: antialiased; }
    .shell { width: min(1420px,100%); margin: 0 auto; padding: 0 24px 30px; }
    .topbar { min-height: 78px; display: flex; align-items: center; justify-content: space-between; gap: 18px; border-bottom: 1px solid var(--line-strong); }
    .brand { display: flex; align-items: center; gap: 12px; min-width: 0; }
    .mark { width: 40px; height: 40px; display: grid; place-items: center; color: #fff; background: var(--green); border-radius: 12px; box-shadow: 0 8px 24px rgba(23,107,85,.16); }
    .mark svg { width: 23px; height: 23px; }
    .brand-name { margin: 0; font-size: 16px; font-weight: 720; letter-spacing: -.015em; }
    .brand-subtitle,.eyebrow { margin: 2px 0 0; color: var(--muted); font: 10px var(--mono); letter-spacing: .11em; text-transform: uppercase; }
    .connection { display: flex; align-items: center; gap: 9px; color: var(--muted); font: 11px var(--mono); }
    .connection-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--amber); box-shadow: 0 0 0 4px rgba(168,107,22,.11); }
    .connection[data-state="live"] .connection-dot { background: var(--mint); box-shadow: 0 0 0 4px rgba(73,198,154,.13); }
    .connection[data-state="offline"] .connection-dot { background: var(--red); box-shadow: 0 0 0 4px rgba(166,64,56,.11); }
    main { padding-top: 22px; }
    .panel { background: var(--panel); border: 1px solid var(--line); border-radius: var(--radius); box-shadow: 0 12px 36px rgba(40,63,52,.055); }
    .hero { display: grid; grid-template-columns: minmax(260px,.68fr) minmax(0,1.5fr); overflow: hidden; }
    .run-summary { padding: 24px; background: linear-gradient(145deg,#173f34,#0f2f27); color: #f6fffb; }
    .run-summary .eyebrow { color: #9dc7b8; }
    h1,h2,p { margin-top: 0; }
    h1 { margin: 15px 0 7px; font-size: clamp(26px,4vw,40px); line-height: 1.02; letter-spacing: -.045em; }
    h2 { margin-bottom: 0; font-size: 16px; letter-spacing: -.015em; }
    .run-mode { color: #b8d1c8; }
    .run-ref { margin: 28px 0 0; color: #83aa9c; font: 11px var(--mono); overflow-wrap: anywhere; }
    .warning { display: none; margin-top: 18px; padding: 10px 12px; border: 1px solid rgba(255,215,146,.35); border-radius: 10px; color: #ffe5ba; background: rgba(119,74,10,.35); font-size: 12px; }
    .warning.visible { display: block; }
    .molecule-workspace { display: grid; grid-template-columns: minmax(0,1.35fr) minmax(220px,.65fr); min-height: 390px; }
    .molecule-stage { position: relative; display: grid; place-items: center; min-height: 390px; padding: 24px; background: #f8faf6; border-right: 1px solid var(--line); }
    .molecule-stage::before { content: ""; position: absolute; inset: 18px; border: 1px dashed #dbe5df; border-radius: 14px; pointer-events: none; }
    .molecule-stage img { position: relative; display: block; width: 100%; height: 330px; object-fit: contain; }
    .molecule-empty { position: relative; z-index: 1; max-width: 34ch; text-align: center; color: var(--muted); }
    .molecule-empty strong { display: block; margin-bottom: 8px; color: var(--ink); font-size: 15px; }
    .molecule-empty[hidden],.molecule-stage img[hidden] { display: none; }
    .candidate-meta { padding: 25px 22px; }
    .candidate-id { margin: 11px 0 18px; font-size: 21px; font-weight: 720; letter-spacing: -.025em; overflow-wrap: anywhere; }
    .meta-label { margin: 14px 0 5px; color: var(--quiet); font: 10px var(--mono); letter-spacing: .1em; text-transform: uppercase; }
    .smiles { display: block; max-height: 90px; padding: 9px 10px; overflow: auto; color: #315349; background: #f2f6f2; border: 1px solid var(--line); border-radius: 8px; font: 11px/1.45 var(--mono); overflow-wrap: anywhere; white-space: normal; }
    .score-list { margin: 0; padding: 0; list-style: none; }
    .score-list li { display: flex; justify-content: space-between; gap: 12px; padding: 8px 0; border-bottom: 1px solid #edf1ee; }
    .score-list span { color: var(--muted); font-size: 12px; }
    .score-list strong { font: 12px var(--mono); }
    .section-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-top: 16px; }
    .section-card { padding: 20px 21px 22px; }
    .section-heading { display: flex; align-items: baseline; justify-content: space-between; gap: 10px; margin-bottom: 15px; }
    .step-list { display: grid; gap: 8px; }
    .step { display: grid; grid-template-columns: 27px 1fr auto; align-items: center; gap: 10px; padding: 9px 10px; border: 1px solid #e3e9e5; border-radius: 10px; background: #fbfcfa; }
    .step-index { width: 25px; height: 25px; display: grid; place-items: center; border-radius: 8px; color: var(--muted); background: #edf2ee; font: 10px var(--mono); }
    .step-name { font-size: 12px; font-weight: 620; }
    .step-status { padding: 3px 7px; border-radius: 999px; color: var(--muted); background: #eef2ef; font: 9px var(--mono); letter-spacing: .05em; text-transform: uppercase; }
    .step[data-status="complete"] .step-status { color: var(--green); background: var(--green-soft); }
    .step[data-status="running"] .step-status { color: var(--blue); background: #e5eef9; }
    .step[data-status="failed"] .step-status { color: var(--red); background: var(--red-soft); }
    .telemetry { display: grid; grid-template-columns: repeat(4,minmax(0,1fr)); gap: 12px; margin-top: 16px; }
    .metric { padding: 17px 18px; min-height: 102px; background: rgba(255,255,255,.8); border: 1px solid var(--line); border-radius: 14px; }
    .metric-label { color: var(--quiet); font: 10px var(--mono); letter-spacing: .1em; text-transform: uppercase; }
    .metric-value { display: block; margin-top: 12px; font-size: 24px; letter-spacing: -.03em; }
    .activity-grid { display: grid; grid-template-columns: 1.35fr .65fr; gap: 16px; margin-top: 16px; }
    .activity { padding: 20px 22px; min-width: 0; }
    .events { margin: 14px 0 0; padding: 0; list-style: none; max-height: 280px; overflow-y: auto; }
    .event { display: grid; grid-template-columns: 9px minmax(120px,.35fr) 1fr auto; gap: 10px; align-items: baseline; padding: 10px 0; border-top: 1px solid #e9eeeb; }
    .event-dot { width: 7px; height: 7px; border-radius: 50%; background: var(--blue); }
    .event-type { font-size: 12px; font-weight: 650; }
    .event-summary { color: var(--muted); font-size: 12px; overflow-wrap: anywhere; }
    .event-time { color: var(--quiet); font: 10px var(--mono); white-space: nowrap; }
    .empty-events { padding: 28px 0; color: var(--muted); text-align: center; }
    .boundary { padding: 20px 22px; color: #6f4d18; background: var(--amber-soft); border-color: #ead0a5; }
    .boundary-mark { width: 30px; height: 30px; display: grid; place-items: center; margin-bottom: 18px; border: 1px solid #d2a65f; border-radius: 9px; font-weight: 800; }
    .boundary p { margin: 9px 0 0; font-size: 12px; }
    @media (max-width: 980px) { .hero,.molecule-workspace,.activity-grid { grid-template-columns: 1fr; } .molecule-stage { border-right: 0; border-bottom: 1px solid var(--line); } .section-grid { grid-template-columns: 1fr; } }
    @media (max-width: 700px) { .shell { padding: 0 14px 22px; } .brand-subtitle,.connection span:last-child { display: none; } .telemetry { grid-template-columns: repeat(2,minmax(0,1fr)); } .event { grid-template-columns: 9px 1fr auto; } .event-summary { grid-column: 2 / -1; } .molecule-stage { min-height: 300px; } .molecule-stage img { height: 260px; } }
    @media (prefers-reduced-motion: no-preference) { .connection[data-state="live"] .connection-dot { animation: pulse 2s ease-out infinite; } @keyframes pulse { 0%,65%,100% { opacity: 1; } 82% { opacity: .35; } } }
  </style>
</head>
<body>
  <div class="shell">
    <header class="topbar">
      <div class="brand"><div class="mark" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><path d="M8 3v5l-4.7 8.1A3.2 3.2 0 0 0 6.1 21h11.8a3.2 3.2 0 0 0 2.8-4.9L16 8V3"/><path d="M7 13h10M9 3h6"/><circle cx="10" cy="16" r="1" fill="currentColor" stroke="none"/><circle cx="14.5" cy="18" r=".8" fill="currentColor" stroke="none"/></svg></div><div><p class="brand-name">Drug Discovery Research Assistant</p><p class="brand-subtitle">Computational candidate review</p></div></div>
      <div class="connection" id="connection" data-state="connecting" role="status"><span class="connection-dot"></span><span id="connection-label">Connecting to run</span></div>
    </header>
    <main>
      <section class="panel hero">
        <div class="run-summary"><p class="eyebrow">Discovery status</p><h1 id="overall-status">Waiting to start</h1><p class="run-mode" id="run-mode">Preparing the live workflow.</p><div class="warning" id="warning" role="alert"></div><p class="run-ref" id="run-ref">RUN —</p></div>
        <div class="molecule-workspace">
          <div class="molecule-stage"><img id="molecule-image" hidden alt="Two-dimensional structure of the leading computational candidate"><div class="molecule-empty" id="molecule-empty"><strong>Leading molecule not ready</strong><span>The locally rendered 2D structure appears after the first simulation-ranked cycle completes.</span></div></div>
          <aside class="candidate-meta"><p class="eyebrow">Leading candidate</p><p class="candidate-id" id="candidate-id">Awaiting ranking</p><p class="meta-label">SMILES</p><code class="smiles" id="candidate-smiles">—</code><p class="meta-label">Computational scores</p><ul class="score-list"><li><span>DrugCLIP</span><strong id="score-drugclip">—</strong></li><li><span>Stability</span><strong id="score-stability">—</strong></li><li><span>GNINA affinity</span><strong id="score-affinity">—</strong></li><li><span>Toxicity penalty</span><strong id="score-toxicity">—</strong></li></ul></aside>
        </div>
      </section>
      <section class="telemetry" aria-label="Discovery metrics"><article class="metric"><span class="metric-label">Current cycle</span><strong class="metric-value" id="metric-cycle">—</strong></article><article class="metric"><span class="metric-label">Candidates</span><strong class="metric-value" id="metric-candidates">0</strong></article><article class="metric"><span class="metric-label">DrugCLIP screens</span><strong class="metric-value" id="metric-screens">0</strong></article><article class="metric"><span class="metric-label">Simulations</span><strong class="metric-value" id="metric-simulations">0</strong></article></section>
      <section class="section-grid"><article class="panel section-card"><div class="section-heading"><div><p class="eyebrow">Logical DAG</p><h2>Workflow steps</h2></div></div><div class="step-list" id="workflow-steps"></div></article><article class="panel section-card"><div class="section-heading"><div><p class="eyebrow">Active loop</p><h2>Current discovery cycle</h2></div></div><div class="step-list" id="cycle-steps"></div></article></section>
      <section class="activity-grid"><article class="panel activity"><p class="eyebrow">Live trace</p><h2>Recent progress</h2><ol class="events" id="events"><li class="empty-events">Waiting for the first workflow event.</li></ol></article><aside class="panel boundary"><div class="boundary-mark">!</div><p class="eyebrow">Scientific review boundary</p><h2>Hypothesis, not validation</h2><p>The molecule and scores are computational outputs. Human scientific review is required before laboratory, clinical, regulatory, procurement, or external-system action.</p></aside></section>
    </main>
  </div>
  <script>
    const byId = id => document.getElementById(id);
    const setText = (id,value) => { const node=byId(id); if(node) node.textContent=String(value ?? '—'); };
    const score = value => Number.isFinite(Number(value)) ? Number(value).toFixed(4) : '—';
    const displayTime = value => { const parsed=new Date(value); return Number.isNaN(parsed.valueOf()) ? String(value||'').slice(0,16) : parsed.toLocaleTimeString([],{hour:'2-digit',minute:'2-digit',second:'2-digit'}); };
    function renderSteps(targetId,metrics,prefix) { const target=byId(targetId); target.replaceChildren(); const rows=Object.entries(metrics).filter(([key])=>key.startsWith(prefix)); if(!rows.length){const empty=document.createElement('p');empty.className='empty-events';empty.textContent='Waiting for step definitions.';target.append(empty);return;} rows.forEach(([key,value],index)=>{const row=document.createElement('div');row.className='step';row.dataset.status=String(value||'waiting').toLowerCase();const order=document.createElement('span');order.className='step-index';order.textContent=String(index+1).padStart(2,'0');const name=document.createElement('span');name.className='step-name';name.textContent=key.replace(prefix,'');const status=document.createElement('span');status.className='step-status';status.textContent=value||'Waiting';row.append(order,name,status);target.append(row);}); }
    function renderEvents(events) { const target=byId('events');target.replaceChildren();const rows=Array.isArray(events)?events.slice().reverse().slice(0,28):[];if(!rows.length){const empty=document.createElement('li');empty.className='empty-events';empty.textContent='Connected and waiting for workflow activity.';target.append(empty);return;}rows.forEach(event=>{const row=document.createElement('li');row.className='event';const dot=document.createElement('span');dot.className='event-dot';const type=document.createElement('span');type.className='event-type';type.textContent=event.type||'Runtime event';const summary=document.createElement('span');summary.className='event-summary';summary.textContent=event.summary||'State updated.';const time=document.createElement('time');time.className='event-time';time.textContent=displayTime(event.timestamp);row.append(dot,type,summary,time);target.append(row);}); }
    function renderMolecule(molecule) { const preview=molecule||{};const image=byId('molecule-image');const empty=byId('molecule-empty');const ready=preview.status==='ready'&&preview.image_url;image.hidden=!ready;empty.hidden=Boolean(ready);if(ready){const next=preview.image_url;if(image.getAttribute('src')!==next)image.setAttribute('src',next);image.alt='Two-dimensional structure of '+(preview.candidate_id||'the leading candidate');}else{const strong=empty.querySelector('strong');const detail=empty.querySelector('span');strong.textContent=preview.status==='unavailable'?'Molecule preview unavailable':preview.status==='disabled'?'Molecule preview disabled':'Leading molecule not ready';detail.textContent=preview.detail||'The locally rendered 2D structure appears after the first simulation-ranked cycle completes.';}setText('candidate-id',ready?preview.candidate_id:'Awaiting ranking');setText('candidate-smiles',ready?preview.smiles:'—');setText('score-drugclip',score(preview.drugclip_score));setText('score-stability',score(preview.simulation_stability));setText('score-affinity',score(preview.gnina_affinity));setText('score-toxicity',score(preview.toxicity_penalty)); }
    function applyState(state) { const metrics=state&&state.metrics?state.metrics:{};setText('overall-status',metrics['Overall status']||'Waiting to start');setText('run-mode',(metrics['Mode']||'Live')+' · '+(metrics['Last update']||'waiting for update'));setText('run-ref','RUN '+(metrics.Run||'—'));setText('metric-cycle',metrics['Current cycle']??'—');setText('metric-candidates',metrics.Candidates??0);setText('metric-screens',metrics['DrugCLIP screens']??0);setText('metric-simulations',metrics.Simulations??0);const warning=byId('warning');warning.textContent=state.warning||'';warning.classList.toggle('visible',Boolean(state.warning));renderSteps('workflow-steps',metrics,'Step ');renderSteps('cycle-steps',metrics,'Cycle — ');renderEvents(state.events);renderMolecule(state.molecule); }
    async function refresh(){try{const response=await fetch('/ui/state',{cache:'no-store'});if(!response.ok)throw new Error('state unavailable');applyState(await response.json());byId('connection').dataset.state='live';setText('connection-label','Run state connected');}catch(_error){byId('connection').dataset.state='offline';setText('connection-label','Reconnecting to run');}}
    refresh();window.setInterval(refresh,1000);
  </script>
</body>
</html>\n"""


if __name__ == "__main__":
    raise SystemExit(main())
