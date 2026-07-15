from __future__ import annotations

from mn_prototype_operation_router_agent import OperationRouterSpec, create_agent

from agents.company_packet_grouper import run_company_packet_grouper
from agents.startup_folder_watcher import run_startup_folder_watcher

from ._shared import compose


run = compose(
    create_agent(
        OperationRouterSpec(
            operations={
                "detect_changes": run_startup_folder_watcher,
                "assemble_packets": run_company_packet_grouper,
            },
            label="VC intake operation",
        )
    )
)
