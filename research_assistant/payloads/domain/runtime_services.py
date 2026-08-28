"""Runtime-boundary adapters for Research Assistant."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mn_sdk.blueprint_support import (
    BudgetedLlmClient,
    build_action_budget,
    build_llm_call_limiter,
    create_blueprint_run_context,
)

from .common import BLUEPRINT_ID, quick_test_enabled, research_llm
from .llm_services import adapt_structured_research_llm


def runtime_context_for_step(
    *, inputs: dict[str, Any] | None = None, config: dict[str, Any] | None = None,
    runs_root: str | None = None, run_id: str | None = None,
) -> dict[str, Any]:
    return create_blueprint_run_context(
        runtime_file=__file__, blueprint_id=BLUEPRINT_ID,
        inputs=inputs, config=config, runs_root=runs_root, run_id=run_id,
    ).to_mapping()


def _append_llm_observation(
    run_dir: Path | None, event_type: str, payload: dict[str, Any]
) -> None:
    if run_dir is None:
        return
    run_dir.mkdir(parents=True, exist_ok=True)
    record = {"type": event_type, "payload": payload}
    with (run_dir / "llm_rag_trace.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True, default=str) + "\n")


def init_research_llm(
    ctx: dict[str, Any], llm_client: Any | None = None
) -> tuple[Any, Any]:
    """Create the same configured, budgeted actor client used by VC Assistant."""
    config = ctx["config"]
    quick_test = quick_test_enabled(config)
    llm_config = config.get("llm") if isinstance(config.get("llm"), dict) else {}
    require_live = bool(llm_config.get("require_live", False)) and not quick_test
    budgets = config.get("budgets") if isinstance(config.get("budgets"), dict) else {}
    action_budget = build_action_budget(
        config,
        default_actions=max(1, int(budgets.get("max_llm_calls") or 20)),
    )
    limiter = build_llm_call_limiter(config, fake_mode=quick_test)
    configured_llm = adapt_structured_research_llm(
        research_llm(config, llm_client), config
    )
    llm = BudgetedLlmClient(
        configured_llm,
        action_budget,
        require_live=require_live,
        limiter=limiter,
        run_dir=Path(ctx["run_dir"]),
        observation_writer=_append_llm_observation,
        action_type="llm_call",
        tool_name="research_actor_llm",
        operation="research_actor_llm.generate_json",
    )
    return llm, action_budget


__all__ = ["init_research_llm", "runtime_context_for_step"]
