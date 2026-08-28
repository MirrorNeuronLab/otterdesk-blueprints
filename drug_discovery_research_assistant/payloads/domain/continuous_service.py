"""Supervised continuous-service binding for discovery cycles."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mn_prototype_supervised_service_agent import (
    ServiceContext,
    SupervisedServiceSpec,
    create_agent as create_supervised_service,
)

from .native_stages import (
    read_discovery_state,
    run_stage_script,
    write_discovery_state,
)


def run_discovery_service(ctx: dict[str, Any], **_options: Any) -> dict[str, Any]:
    state = read_discovery_state(ctx)
    service = create_supervised_service(
        SupervisedServiceSpec(
            serve=lambda _service_context: run_stage_script(
                ctx,
                state,
                "run_continuous_service.py",
                {},
                timeout=None,
            ),
        )
    )
    service(
        context=ServiceContext(
            config=ctx["config"],
            run_dir=Path(ctx["run_dir"]),
            output_folder=Path(ctx["output_folder"]),
        )
    )
    status_path = Path(ctx["run_dir"]) / "service_state.json"
    status = (
        json.loads(status_path.read_text(encoding="utf-8"))
        if status_path.exists()
        else {}
    )
    state["service_reports"] = status.get("reports") or []
    write_discovery_state(ctx, state)
    return {
        "completed_cycles": status.get("completed_cycles", 0),
        "service_status": status.get("status"),
    }
