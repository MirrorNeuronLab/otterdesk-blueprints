from __future__ import annotations

from mn_prototype_operation_router_agent import OperationRouterSpec, create_agent

from agents.batch_index_writer import run_batch_index_writer_step
from agents.company_report_writer import run_company_report_writer_step

from ._shared import compose


run = compose(
    create_agent(
        OperationRouterSpec(
            operations={
                "company": run_company_report_writer_step,
                "batch_index": run_batch_index_writer_step,
            },
            label="VC reporting operation",
        )
    )
)
