"""Local end-to-end runner using the same specialist handlers as deployed agents."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .advice import step_advisor_evidence_reconciler, step_advisor_review_auditor
from .cash_flow import step_cash_flow_llm_analyst, step_cash_flow_normalizer
from .common import BLUEPRINT_ID, BLUEPRINT_NAME, start_agent_beacon_thread
from .execution import execute_runtime_handler
from .intake import step_bank_statement_extractor, step_financial_document_reader, step_financial_folder_watcher
from .portfolio import step_portfolio_context_loader, step_portfolio_llm_reviewer, step_portfolio_market_data_loader, step_portfolio_risk_engine
from .reporting import step_financial_advice_reporter
from .research import step_public_finance_researcher
from .tax import step_tax_document_router, step_tax_form_ocr_capturer, step_tax_llm_reviewer, step_tax_workpaper_preparer


LOCAL_AGENT_SEQUENCE = (
    ("financial_folder_watcher", step_financial_folder_watcher),
    ("financial_document_reader", step_financial_document_reader),
    ("bank_statement_extractor", step_bank_statement_extractor),
    ("cash_flow_normalizer", step_cash_flow_normalizer),
    ("cash_flow_llm_analyst", step_cash_flow_llm_analyst),
    ("tax_document_router", step_tax_document_router),
    ("tax_form_ocr_capturer", step_tax_form_ocr_capturer),
    ("tax_workpaper_preparer", step_tax_workpaper_preparer),
    ("tax_llm_reviewer", step_tax_llm_reviewer),
    ("portfolio_context_loader", step_portfolio_context_loader),
    ("portfolio_market_data_loader", step_portfolio_market_data_loader),
    ("portfolio_risk_engine", step_portfolio_risk_engine),
    ("portfolio_llm_reviewer", step_portfolio_llm_reviewer),
    ("public_finance_researcher", step_public_finance_researcher),
    ("advisor_evidence_reconciler", step_advisor_evidence_reconciler),
    ("advisor_review_auditor", step_advisor_review_auditor),
    ("financial_advice_reporter", step_financial_advice_reporter),
)


def run_blueprint(
    inputs: dict[str, Any] | None = None,
    config: dict[str, Any] | None = None,
    runs_root: str | Path | None = None,
    run_id: str | None = None,
    llm_client: Any | None = None,
    config_json: str | None = None,
) -> dict[str, Any]:
    start_agent_beacon_thread(f"{BLUEPRINT_NAME} is running")
    current_run_id = run_id
    final_result: dict[str, Any] | None = None
    for agent_id, handler in LOCAL_AGENT_SEQUENCE:
        final_result = execute_runtime_handler(
            agent_id,
            handler,
            inputs=inputs,
            config=config,
            runs_root=runs_root,
            run_id=current_run_id,
            llm_client=llm_client,
            config_json=config_json,
            finalize_run=agent_id == "financial_advice_reporter",
        )
        current_run_id = final_result["run_id"]
    if not final_result or "final_artifact" not in final_result:
        raise RuntimeError("Financial Advisor workflow completed without a final artifact.")
    return {
        "run_id": final_result["run_id"],
        "blueprint_id": BLUEPRINT_ID,
        "status": "completed",
        "final_artifact": final_result["final_artifact"],
        "output_files": final_result.get("output_files", []),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the Financial Advisor sample workflow.")
    parser.add_argument("--input-file", type=Path)
    parser.add_argument("--input-folder", default="")
    parser.add_argument("--output-folder", default="")
    parser.add_argument("--runs-root", type=Path)
    parser.add_argument("--run-id")
    parser.add_argument("--config-json")
    args = parser.parse_args(argv)
    inputs: dict[str, Any] = {}
    if args.input_file:
        loaded = json.loads(args.input_file.read_text(encoding="utf-8"))
        inputs.update(loaded if isinstance(loaded, dict) else {})
    if args.input_folder:
        inputs.update({"document_folder": args.input_folder, "input_folder": args.input_folder})
    if args.output_folder:
        inputs["output_folder"] = args.output_folder
    result = run_blueprint(inputs=inputs, runs_root=args.runs_root, run_id=args.run_id, config_json=args.config_json)
    print(json.dumps({"run_id": result["run_id"], "status": result["status"], "final_artifact": result["final_artifact"]}, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
