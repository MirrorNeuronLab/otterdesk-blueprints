from __future__ import annotations

from mn_prototype_operation_router_agent import OperationRouterSpec, create_agent

from agents.company_packet_grouper import run_company_packet_grouper_step
from agents.startup_folder_watcher import run_startup_folder_watcher_step

from ._shared import compose


run = compose(
    create_agent(
        OperationRouterSpec(
            operations={
                "watch": run_startup_folder_watcher_step,
                "group": run_company_packet_grouper_step,
            },
            label="VC intake operation",
        )
    )
)
