"""Research-specific model requirements on shared SDK budgets and limiting."""
from typing import Any
from mn_sdk.blueprint_support import BudgetedLlmClient, build_action_budget, build_llm_call_limiter
from mn_sdk.blueprint_support.step_execution import append_debug
from .common import quick_test_enabled, research_llm


def init_research_llm(
    block, llm_client: Any | None = None
) -> tuple[Any, Any]:
    """Create the same configured, budgeted actor client used by VC Assistant."""
    config = block.config
    quick_test = quick_test_enabled(config)
    llm_config = config.get("llm") if isinstance(config.get("llm"), dict) else {}
    require_live = bool(llm_config.get("require_live", False)) and not quick_test
    budgets = config.get("budgets") if isinstance(config.get("budgets"), dict) else {}
    action_budget = build_action_budget(
        config,
        default_actions=max(1, int(budgets.get("max_llm_calls") or 20)),
    )
    limiter = build_llm_call_limiter(config, fake_mode=quick_test)
    configured_llm = research_llm(config, llm_client)
    llm = BudgetedLlmClient(
        configured_llm,
        action_budget,
        require_live=require_live,
        limiter=limiter,
        run_dir=block.store.run_dir,
        observation_writer=append_debug,
        action_type="llm_call",
        tool_name="research_actor_llm",
        operation="research_actor_llm.generate_json",
    )
    return llm, action_budget

