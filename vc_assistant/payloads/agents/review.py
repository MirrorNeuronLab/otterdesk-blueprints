"""Actor-review behavior for one VC agent invocation."""

from __future__ import annotations

from typing import Any

from domain.agent_review import run_step_agent_reviews


def review_agent_invocation(
    ctx: dict[str, Any],
    *,
    step_id: str,
    agent_id: str,
    services: dict[str, Any],
    llm_client: Any | None = None,
) -> dict[str, Any]:
    return run_step_agent_reviews(
        ctx,
        step_id,
        [agent_id],
        services,
        llm_client=llm_client,
    )


__all__ = ["review_agent_invocation"]
