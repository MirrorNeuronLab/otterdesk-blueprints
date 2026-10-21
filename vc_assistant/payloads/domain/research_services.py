"""VC model, knowledge and research-budget policy on the native block context."""

from dataclasses import dataclass

from mn_sdk.blueprint_support import BlueprintBundleLayout, LlmCallLimiter
from mn_sdk.integrations.run_budget import RunActionBudget
from mn_prototype_actor_review_agent.actors import get_actor_llm_client

from .common import build_llm_call_limiter
from .knowledge import load_vc_knowledge, prepare_knowledge_rag, require_ready_rag
from .runtime_tools import BudgetedLLM, llm_requires_live, observed_operation, append_event


@dataclass
class ResearchResources:
    knowledge: dict
    rag: dict
    budget: RunActionBudget
    model: BudgetedLLM | None
    limiter: LlmCallLimiter


def research_resources(block, state, role, *, need_model=True, need_knowledge=True, budget_scope="review"):
    knowledge, rag = {}, {}
    if need_knowledge:
        root = BlueprintBundleLayout.discover(__file__, env=block.environment).root
        knowledge = load_vc_knowledge(root)
        rag = prepare_knowledge_rag(blueprint_dir=root, resolved_config=block.config,
            active_knowledge=knowledge, run_dir=block.store.run_dir)
        require_ready_rag(rag, stage=role, run_dir=block.store.run_dir)
    budget = RunActionBudget(block, name="research_actions", scope=budget_scope,
        client=block.resources.get("workflow_budget"))
    limiter = build_llm_call_limiter(block.config)
    model = None
    if need_model:
        try:
            with observed_operation(block.store.run_dir, phase="llm_init", operation="actor_llm.init"):
                model = BudgetedLLM(get_actor_llm_client(block.config, block.resources.get("llm")),
                    budget, require_live=llm_requires_live(block.config), limiter=limiter,
                    run_dir=block.store.run_dir)
        except Exception as exc:
            append_event(block.store.run_dir, "tool_call_failed", {"tool": "actor_llm.init",
                "status": "required_actor_llm_init_failed", "error": str(exc)})
            raise
    return ResearchResources(knowledge, rag, budget, model, limiter)
