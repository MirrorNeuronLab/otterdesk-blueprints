"""Local end-to-end runner using the same purchase specialists as deployment."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .comparison import (
    analyze_total_cost,
    audit_recommendation,
    research_market,
    review_purchase_risks,
)
from .intake import collect_context, retrieve_knowledge
from .reporting import publish_report
from .runtime_services import runtime_context_for_step


LOCAL_OPERATIONS = (
    collect_context,
    retrieve_knowledge,
    research_market,
    analyze_total_cost,
    review_purchase_risks,
    audit_recommendation,
    publish_report,
)


def run_blueprint(
    blueprint_id: str = "purchase_research_assistant",
    *,
    inputs: dict[str, Any] | None = None,
    llm_client: Any | None = None,
    config: dict[str, Any] | None = None,
    config_path: str | Path | None = None,
    config_json: str | None = None,
    run_id: str | None = None,
    runs_root: str | Path | None = None,
    **_options: Any,
) -> dict[str, Any]:
    if blueprint_id != "purchase_research_assistant":
        raise ValueError(f"this runner handles 'purchase_research_assistant', got {blueprint_id!r}")
    if llm_client is not None or config_path is not None or config_json is not None:
        raise ValueError("The specialist sample runner accepts resolved config overlays only; model clients are runtime-managed.")
    context = runtime_context_for_step(
        inputs=inputs,
        config=config,
        runs_root=str(runs_root) if runs_root else None,
        run_id=run_id,
    )
    result: dict[str, Any] = {}
    for operation in LOCAL_OPERATIONS:
        result = operation(context)
    return {
        "run_id": context["run_id"],
        "blueprint_id": "purchase_research_assistant",
        "status": "completed",
        **result,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the Purchase Research Assistant sample workflow.")
    parser.add_argument("--input-folder", default="")
    parser.add_argument("--output-folder", default="")
    parser.add_argument("--runs-root", type=Path)
    parser.add_argument("--run-id")
    args = parser.parse_args(argv)
    inputs: dict[str, Any] = {}
    if args.input_folder:
        inputs["input_folder"] = args.input_folder
    if args.output_folder:
        inputs["output_folder"] = args.output_folder
    result = run_blueprint(inputs=inputs, runs_root=args.runs_root, run_id=args.run_id)
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["run_blueprint", "main"]
