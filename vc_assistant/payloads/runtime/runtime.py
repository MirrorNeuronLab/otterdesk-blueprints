"""VC Assistant runtime preparation boundary.

The workflow manifest owns routing and the modules under ``agents`` own domain
behavior.  This module only exposes runtime context, service preparation,
observability hooks, and lifecycle persistence used by agent invocations.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agents import domain as _domain


BLUEPRINT_ID = _domain.BLUEPRINT_ID
BLUEPRINT_NAME = _domain.BLUEPRINT_NAME


def runtime_context_for_step(
    *,
    inputs: dict[str, Any] | None = None,
    config: dict[str, Any] | None = None,
    runs_root: str | Path | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    return _domain.runtime_context_for_step(
        inputs=inputs,
        config=config,
        runs_root=runs_root,
        run_id=run_id,
    )


def agentic_research_config(config: dict[str, Any]) -> dict[str, Any]:
    return _domain.agentic_research_config(config)


def step_agent_review_selected(ctx: dict[str, Any], agent_ids: list[str]) -> bool:
    return _domain.step_agent_review_selected(ctx, agent_ids)


def build_runtime_services(
    ctx: dict[str, Any],
    *,
    llm_client: Any | None = None,
    need_llm: bool = False,
    rag_stage: str = "",
) -> dict[str, Any]:
    return _domain.build_runtime_services(
        ctx,
        llm_client=llm_client,
        need_llm=need_llm,
        rag_stage=rag_stage,
    )


def persist_action_budget_state(
    ctx: dict[str, Any], action_budget: Any
) -> dict[str, Any]:
    return _domain.persist_action_budget_state(ctx, action_budget)


def append_event(run_dir: Path, event_type: str, payload: dict[str, Any]) -> None:
    _domain.append_event(run_dir, event_type, payload)


def append_debug_record(
    run_dir: Path, event_type: str, payload: dict[str, Any]
) -> None:
    _domain.append_debug_record(run_dir, event_type, payload)


def write_benchmark_artifacts(*args: Any, **kwargs: Any) -> dict[str, Any] | None:
    return _domain.write_benchmark_artifacts(*args, **kwargs)


__all__ = [
    "BLUEPRINT_ID",
    "BLUEPRINT_NAME",
    "agentic_research_config",
    "append_debug_record",
    "append_event",
    "build_runtime_services",
    "persist_action_budget_state",
    "runtime_context_for_step",
    "step_agent_review_selected",
    "write_benchmark_artifacts",
]
