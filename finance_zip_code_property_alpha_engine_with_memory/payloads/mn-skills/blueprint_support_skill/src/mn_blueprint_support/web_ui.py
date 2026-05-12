from __future__ import annotations

import html
import json
import threading
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

from .constants import WEB_UI_ADAPTERS
from .utils import utc_now_iso


class WebUIDependencyError(RuntimeError):
    """Raised when an optional web UI dependency is required but missing."""


@dataclass(frozen=True)
class WebUIHandle:
    kind: str
    adapter: str
    url: str
    title: str
    status: str = "available"
    path: str | None = None
    created_at: str = field(default_factory=utc_now_iso)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class WebInputField:
    name: str
    label: str | None = None
    field_type: str = "text"
    default: Any = None
    required: bool = False
    description: str | None = None
    choices: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def default_web_ui_config() -> dict[str, Any]:
    return {
        "enabled": True,
        "input": {
            "adapter": "none",
            "fields": [],
            "title": None,
            "instructions": None,
            "host": "127.0.0.1",
            "port": None,
            "share": False,
            "custom_url": None,
        },
        "output": {
            "adapter": "static_html",
            "auto_generate": True,
            "title": None,
            "custom_url": None,
        },
    }


def validate_web_ui_config(config: dict[str, Any]) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    web_ui = config.get("web_ui") or {}
    if not isinstance(web_ui, dict):
        return [{"severity": "error", "field": "web_ui", "message": "web_ui section must be an object"}]
    for phase in ("input", "output"):
        phase_config = web_ui.get(phase) or {}
        if not isinstance(phase_config, dict):
            issues.append({"severity": "error", "field": f"web_ui.{phase}", "message": "must be an object"})
            continue
        adapter = str(phase_config.get("adapter") or "none")
        if adapter not in WEB_UI_ADAPTERS:
            issues.append(
                {
                    "severity": "error",
                    "field": f"web_ui.{phase}.adapter",
                    "message": f"must be one of {', '.join(WEB_UI_ADAPTERS)}",
                }
            )
    return issues


def custom_web_ui_handle(config: dict[str, Any], *, phase: str = "output") -> WebUIHandle | None:
    web_ui = config.get("web_ui") or {}
    phase_config = web_ui.get(phase) or {}
    if str(phase_config.get("adapter") or "none") != "custom":
        return None
    url = phase_config.get("custom_url") or phase_config.get("url")
    if not url:
        return None
    return WebUIHandle(
        kind=phase,
        adapter="custom",
        url=str(url),
        title=str(phase_config.get("title") or "Custom Blueprint Web UI"),
        status="external",
        metadata={"phase": phase, "customer_managed": True},
    )


def register_web_ui(run_dir: str | Path, handle: WebUIHandle | dict[str, Any]) -> dict[str, Any]:
    directory = Path(run_dir).expanduser()
    directory.mkdir(parents=True, exist_ok=True)
    payload = handle.to_dict() if isinstance(handle, WebUIHandle) else dict(handle)
    (directory / "web_ui.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def load_web_ui(run_dir: str | Path) -> dict[str, Any]:
    path = Path(run_dir).expanduser() / "web_ui.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def render_static_run_report(record: dict[str, Any], *, title: str | None = None) -> str:
    run = record.get("run") or {}
    result = record.get("result") or record
    final_artifact = record.get("final_artifact") or result.get("final_artifact") or {}
    events = record.get("events") or result.get("events") or []
    page_title = title or f"Blueprint Run {run.get('run_id') or result.get('blueprint') or 'Report'}"
    summary_rows = {
        "run_id": run.get("run_id") or (result.get("identity") or {}).get("run_id"),
        "blueprint_id": run.get("blueprint_id") or result.get("blueprint"),
        "status": run.get("status") or (result.get("run") or {}).get("status"),
        "started_at": run.get("started_at") or (result.get("run") or {}).get("started_at"),
        "ended_at": run.get("ended_at") or (result.get("run") or {}).get("ended_at"),
    }
    event_rows = "\n".join(
        f"<tr><td>{html.escape(str(event.get('ts') or event.get('timestamp') or ''))}</td>"
        f"<td>{html.escape(str(event.get('type') or 'event'))}</td>"
        f"<td><code>{html.escape(json.dumps(event.get('payload', event), sort_keys=True))}</code></td></tr>"
        for event in events[-50:]
    )
    summary_html = "\n".join(
        f"<tr><th>{html.escape(key)}</th><td>{html.escape(str(value or ''))}</td></tr>"
        for key, value in summary_rows.items()
    )
    artifact_json = html.escape(json.dumps(final_artifact, indent=2, sort_keys=True))
    result_json = html.escape(json.dumps(result, indent=2, sort_keys=True))
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(page_title)}</title>
  <style>
    :root {{ color-scheme: light; font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
    body {{ margin: 0; background: #f6f7f9; color: #17202a; }}
    main {{ max-width: 1120px; margin: 0 auto; padding: 32px 20px 56px; }}
    h1 {{ font-size: 30px; margin: 0 0 8px; }}
    h2 {{ font-size: 18px; margin-top: 28px; }}
    .subtle {{ color: #5f6b7a; margin-bottom: 24px; }}
    section {{ background: #fff; border: 1px solid #dfe3e8; border-radius: 8px; padding: 18px; margin: 16px 0; }}
    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{ border-bottom: 1px solid #edf0f2; padding: 10px; text-align: left; vertical-align: top; }}
    th {{ width: 180px; color: #334155; }}
    pre {{ overflow: auto; background: #0f172a; color: #e5e7eb; border-radius: 6px; padding: 14px; }}
    code {{ white-space: pre-wrap; word-break: break-word; }}
  </style>
</head>
<body>
  <main>
    <h1>{html.escape(page_title)}</h1>
    <div class="subtle">Static MirrorNeuron blueprint report generated from the shared run store.</div>
    <section>
      <h2>Run Summary</h2>
      <table>{summary_html}</table>
    </section>
    <section>
      <h2>Final Artifact</h2>
      <pre>{artifact_json}</pre>
    </section>
    <section>
      <h2>Event Tail</h2>
      <table><thead><tr><th>Time</th><th>Event</th><th>Payload</th></tr></thead><tbody>{event_rows}</tbody></table>
    </section>
    <section>
      <h2>Full Result</h2>
      <pre>{result_json}</pre>
    </section>
  </main>
</body>
</html>
"""


def write_static_run_report(
    record: dict[str, Any],
    run_dir: str | Path,
    *,
    title: str | None = None,
    filename: str = "index.html",
) -> WebUIHandle:
    directory = Path(run_dir).expanduser()
    web_dir = directory / "web"
    web_dir.mkdir(parents=True, exist_ok=True)
    html_path = web_dir / filename
    html_path.write_text(render_static_run_report(record, title=title), encoding="utf-8")
    handle = WebUIHandle(
        kind="output",
        adapter="static_html",
        url=html_path.resolve().as_uri(),
        title=title or "Blueprint Run Report",
        path=str(html_path),
        metadata={"run_dir": str(directory), "filename": filename},
    )
    register_web_ui(directory, handle)
    return handle


def maybe_write_static_output(run_store: Any, result: dict[str, Any], config: dict[str, Any]) -> WebUIHandle | None:
    web_ui = config.get("web_ui") or {}
    if web_ui.get("enabled") is False:
        return None
    output = web_ui.get("output") or {}
    custom = custom_web_ui_handle(config, phase="output")
    if custom:
        if getattr(run_store, "enabled", False):
            run_store.write_web_ui(custom.to_dict())
        return custom
    if str(output.get("adapter") or "static_html") != "static_html":
        return None
    if output.get("auto_generate", True) is False or not getattr(run_store, "enabled", False):
        return None
    record = {
        "run": result.get("run") or {},
        "result": result,
        "final_artifact": result.get("final_artifact") or {},
        "events": [],
    }
    handle = write_static_run_report(record, run_store.run_dir, title=output.get("title"))
    run_store.write_web_ui(handle.to_dict())
    return handle


def launch_gradio_input_app(
    fields: list[WebInputField | dict[str, Any]],
    *,
    title: str = "Blueprint Input",
    instructions: str | None = None,
    on_submit: Callable[[dict[str, Any]], Any] | None = None,
    host: str = "127.0.0.1",
    port: int | None = None,
    share: bool = False,
    custom_app: Any = None,
    run_store: Any = None,
    announce_fn: Callable[[str], None] | None = None,
) -> WebUIHandle:
    try:
        import gradio as gr
    except ModuleNotFoundError as exc:
        raise WebUIDependencyError(
            "Install mirrorneuron-blueprint-support-skill[webui] to use Gradio input apps."
        ) from exc

    normalized = [field if isinstance(field, WebInputField) else WebInputField(**field) for field in fields]
    components = []
    if custom_app is not None:
        app = custom_app
    else:
        with gr.Blocks(title=title) as app:
            gr.Markdown(f"# {title}")
            if instructions:
                gr.Markdown(instructions)
            for item in normalized:
                components.append(_gradio_component(gr, item))
            output = gr.JSON(label="Submitted Input")

            def submit(*values):
                payload = {item.name: value for item, value in zip(normalized, values)}
                return on_submit(payload) if on_submit else payload

            gr.Button("Submit").click(submit, inputs=components, outputs=output)

    launched = app.launch(server_name=host, server_port=port, share=share, prevent_thread_lock=True)
    url = getattr(app, "local_url", None)
    if not url and isinstance(launched, tuple) and len(launched) >= 2:
        url = launched[1]
    if not url:
        url = f"http://{host}:{port or 7860}"
    handle = WebUIHandle(
        kind="input",
        adapter="gradio",
        url=str(url),
        title=title,
        status="running",
        metadata={"fields": [item.to_dict() for item in normalized], "share": share},
    )
    if run_store is not None and hasattr(run_store, "write_web_ui"):
        run_store.write_web_ui(handle.to_dict())
    if announce_fn is not None:
        announce_fn(handle.url)
    return handle


def collect_gradio_input(
    fields: list[WebInputField | dict[str, Any]],
    *,
    title: str = "Blueprint Input",
    instructions: str | None = None,
    host: str = "127.0.0.1",
    port: int | None = None,
    share: bool = False,
    timeout_seconds: float | None = None,
    run_store: Any = None,
    announce_fn: Callable[[str], None] | None = None,
    on_submit: Callable[[dict[str, Any]], Any] | None = None,
) -> tuple[dict[str, Any], WebUIHandle]:
    """Launch a Gradio input form and block until the user submits it."""

    submitted: dict[str, Any] = {}
    done = threading.Event()

    def capture(payload: dict[str, Any]) -> Any:
        submitted.clear()
        submitted.update(payload)
        done.set()
        if on_submit is not None:
            return on_submit(payload)
        return {"status": "received", "input_keys": sorted(payload)}

    handle = launch_gradio_input_app(
        fields,
        title=title,
        instructions=instructions,
        on_submit=capture,
        host=host,
        port=port,
        share=share,
        run_store=run_store,
        announce_fn=announce_fn,
    )
    if not done.wait(timeout_seconds):
        raise TimeoutError(f"timed out waiting for web input at {handle.url}")
    return dict(submitted), handle


def _gradio_component(gr: Any, field: WebInputField) -> Any:
    label = field.label or field.name.replace("_", " ").title()
    kwargs = {"label": label, "info": field.description}
    if field.field_type in {"number", "float", "integer"}:
        return gr.Number(value=field.default, **kwargs)
    if field.field_type in {"checkbox", "bool", "boolean"}:
        return gr.Checkbox(value=bool(field.default), **kwargs)
    if field.field_type == "json":
        return gr.JSON(value=field.default or {}, **kwargs)
    if field.field_type == "file":
        return gr.File(**kwargs)
    if field.field_type in {"image", "webcam", "camera"}:
        if field.field_type in {"webcam", "camera"}:
            return gr.Image(value=field.default, sources=["webcam"], type="filepath", **kwargs)
        return gr.Image(value=field.default, type="filepath", **kwargs)
    if field.choices:
        return gr.Dropdown(choices=list(field.choices), value=field.default, **kwargs)
    return gr.Textbox(value="" if field.default is None else str(field.default), **kwargs)
