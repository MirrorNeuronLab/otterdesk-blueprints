from __future__ import annotations

from typing import Any

from mn_sdk.step_runtime import StepContext

from blueprint_runtime.stages.company_packet_grouper import run_company_packet_grouper_step
from blueprint_runtime.stages.startup_folder_watcher import run_startup_folder_watcher_step

from ._shared import execute


OPERATIONS = {
    "watch": run_startup_folder_watcher_step,
    "group": run_company_packet_grouper_step,
}


def run(context: StepContext, operation: str, **options: Any) -> dict[str, Any]:
    try:
        handler = OPERATIONS[operation]
    except KeyError as exc:
        raise ValueError(f"unknown VC intake operation: {operation}") from exc
    return execute(context, handler, **options)
