from __future__ import annotations

from mn_prototype_operation_router_agent import OperationRouterSpec, create_agent

from agents.batch_index_writer import run_batch_index_writer
from agents.company_report_writer import run_company_report_writer

from ._shared import compose


run = compose(
    create_agent(
        OperationRouterSpec(
            operations={
                "write_company_reports": run_company_report_writer,
                "publish_batch_summary": run_batch_index_writer,
            },
            label="VC reporting operation",
        )
    )
)
