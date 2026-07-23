"""Local composition entrypoint that exercises the deployed specialist operations."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .common import BLUEPRINT_ID, utc_now_iso, write_json
from .contracts import compare_contracts, extract_contracts
from .documents import read_documents, watch
from .invoices import extract_invoices, validate_payables
from .reporting import publish_report
from .review import audit_review, reconcile_evidence
from .runtime_services import runtime_context_for_step


OPERATIONS = (
    watch,
    read_documents,
    extract_invoices,
    validate_payables,
    extract_contracts,
    compare_contracts,
    reconcile_evidence,
    audit_review,
    publish_report,
)


def run_blueprint(
    inputs: dict[str, Any] | None = None,
    config: dict[str, Any] | None = None,
    runs_root: str | Path | None = None,
    run_id: str | None = None,
    llm_client: Any | None = None,
) -> dict[str, Any]:
    del llm_client  # Runtime model selection is resolved per specialist operation.
    context = runtime_context_for_step(inputs=inputs, config=config, runs_root=str(runs_root) if runs_root else None, run_id=run_id)
    result: dict[str, Any] = {}
    for operation in OPERATIONS:
        result = operation(context)
    write_json(
        Path(context["run_dir"]) / "run.json",
        {
            "run_id": context["run_id"],
            "blueprint_id": BLUEPRINT_ID,
            "status": "completed",
            "completed_at": utc_now_iso(),
        },
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Legal Assistant")
    parser.add_argument("--input-folder", default="")
    parser.add_argument("--output-folder", default="")
    parser.add_argument("--runs-root", default="")
    parser.add_argument("--run-id", default="")
    parser.add_argument("--config-json", default="")
    args = parser.parse_args()
    inputs: dict[str, Any] = {}
    if args.input_folder:
        inputs.update({"document_folder": args.input_folder, "input_folder": args.input_folder})
    if args.output_folder:
        inputs["output_folder"] = args.output_folder
    config = json.loads(args.config_json) if args.config_json else None
    result = run_blueprint(inputs=inputs, config=config, runs_root=args.runs_root or None, run_id=args.run_id or None)
    print(json.dumps({"run_id": result["run_id"], "status": result["status"], "final_artifact": result["final_artifact"]}, indent=2, default=str))


if __name__ == "__main__":
    main()
