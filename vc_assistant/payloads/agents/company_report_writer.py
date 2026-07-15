from __future__ import annotations

from typing import Any

from mn_sdk.blueprint_support import complete_runtime_step, step_result, write_workflow_state
from runtime.runtime import (
    append_event,
    normalized_research_ledger,
    update_watch_state,
    write_company_outputs,
)

def run_company_report_writer_step(ctx: dict[str, Any], *, llm_client: Any | None = None) -> dict[str, Any]:
    store = ctx["state_store"]
    company_records = store.read_object("company_records.json")
    company_work_queue = store.read_list("company_work_queue.json")
    analyses = sorted(
        (analysis for analysis in store.list_entity_objects("analyses").values() if analysis),
        key=lambda analysis: analysis.get("company_slug") or "",
    )
    research_ledgers = {
        analysis["company_name"]: normalized_research_ledger(
            store.read_entity_object("research_ledgers", analysis["company_name"])
        )
        for analysis in analyses
    }
    output_files = write_company_outputs(ctx["output_folder"], analyses, company_records, research_ledgers, company_work_queue)
    watch_state = update_watch_state(ctx["output_folder"], ctx["run_dir"], company_work_queue, run_id=ctx["run_id"])
    for analysis in analyses:
        store.write_entity("analyses", str(analysis["company_slug"]), analysis)
    write_workflow_state(ctx["run_dir"], "output_files.json", output_files)
    write_workflow_state(ctx["run_dir"], "watch_state.json", watch_state)
    complete_runtime_step(ctx, "company_report_writer", {"output_folder": str(ctx["output_folder"]), "output_file_count": len(output_files)})
    append_event(ctx["run_dir"], "watch_cycle_completed", {"cycle": 1, "companies": len(company_records)})
    return step_result(ctx, "company_report_writer", output_file_count=len(output_files))
