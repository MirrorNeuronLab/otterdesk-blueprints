"""Durable financial workflow state and failure records."""

from .common import *

def load_state(run_dir: Path) -> dict[str, Any]:
    # The prototype stateful-agent lifecycle owns workflow_state/state.json.
    # Financial domain state uses a distinct path so lifecycle persistence
    # cannot overwrite specialist results between agent invocations.
    return read_json(run_dir / "workflow_state" / "financial_advisor_state.json")

def save_state(run_dir: Path, state: dict[str, Any]) -> None:
    write_json(run_dir / "workflow_state" / "financial_advisor_state.json", state)

def runtime_context_path(run_dir: Path) -> Path:
    return run_dir / "workflow_state" / "runtime_context.json"

def persist_runtime_context(ctx: dict[str, Any]) -> None:
    write_json(
        runtime_context_path(ctx["run_dir"]),
        {
            "blueprint_id": BLUEPRINT_ID,
            "run_id": ctx["run_id"],
            "started_at": ctx["started_at"],
            "output_folder": str(ctx["output_folder"]),
            "run_dir": str(ctx["run_dir"]),
            "document_folder": str(ctx["document_folder"]),
            "payload": ctx["payload"],
        },
    )

def write_failed_run(ctx: dict[str, Any], error: Exception | str) -> None:
    write_json(
        ctx["run_dir"] / "run.json",
        {
            "run_id": ctx["run_id"],
            "blueprint_id": BLUEPRINT_ID,
            "status": "failed",
            "error": str(error),
            "finished_at": utc_now_iso(),
        },
    )
