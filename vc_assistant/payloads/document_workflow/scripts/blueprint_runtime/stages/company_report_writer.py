from __future__ import annotations

from .. import runtime as _runtime

globals().update({name: value for name, value in vars(_runtime).items() if not name.startswith("__")})

def run_company_report_writer_step(ctx: dict[str, Any], *, llm_client: Any | None = None) -> dict[str, Any]:
    company_records = read_company_records_state(ctx["run_dir"])
    company_work_queue = read_company_work_queue_state(ctx["run_dir"])
    analyses = read_all_company_analyses(ctx["run_dir"])
    research_ledgers = read_all_research_ledgers(ctx["run_dir"], [analysis["company_name"] for analysis in analyses])
    output_files = write_company_outputs(ctx["output_folder"], analyses, company_records, research_ledgers, company_work_queue)
    watch_state = update_watch_state(ctx["output_folder"], ctx["run_dir"], company_work_queue, run_id=ctx["run_id"])
    for analysis in analyses:
        write_company_analysis_state(ctx["run_dir"], analysis)
    write_workflow_state(ctx["run_dir"], "output_files.json", output_files)
    write_workflow_state(ctx["run_dir"], "watch_state.json", watch_state)
    services = build_runtime_services(
        ctx,
        llm_client=llm_client,
        need_llm=step_actor_review_selected(ctx, "company_report_writer"),
        rag_stage="company_report_writer" if step_actor_review_selected(ctx, "company_report_writer") else "",
    )
    run_step_actor_review(ctx, "company_report_writer", services, llm_client=llm_client)
    persist_action_budget_state(ctx, services["action_budget"])
    complete_runtime_step(ctx, "company_report_writer", {"output_folder": str(ctx["output_folder"]), "output_file_count": len(output_files)})
    append_event(ctx["run_dir"], "watch_cycle_completed", {"cycle": 1, "companies": len(company_records)})
    return step_result(ctx, "company_report_writer", output_file_count=len(output_files))

