"""Local orchestration for the same bounded read-only specialists."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .audit import audit_advice
from .intake import resolve_source
from .mapping import map_architecture
from .prompts import author_prompts
from .report_drafting import draft_architecture_report
from .reporting import publish_advice
from .review import assess_architecture
from .runtime_services import runtime_context_for_step

LOCAL_OPERATIONS = (
    resolve_source,
    map_architecture,
    assess_architecture,
    author_prompts,
    draft_architecture_report,
    audit_advice,
    publish_advice,
)


def run_blueprint(*, inputs: dict[str, Any] | None = None, config: dict[str, Any] | None = None, runs_root: str | Path | None = None, run_id: str | None = None, llm_client: Any | None = None, **_options: Any) -> dict[str, Any]:
    context = runtime_context_for_step(inputs=inputs, config=config, runs_root=str(runs_root) if runs_root else None, run_id=run_id)
    result: dict[str, Any] = {}
    for operation in LOCAL_OPERATIONS:
        result = operation(context, llm_client=llm_client)
    return {"run_id": context["run_id"], "blueprint_id": "software_architecture_advisor", "status": "completed", **result}
