"""VC Assistant runtime preparation boundary.

This module exposes only blueprint identity, context/service preparation, and
lifecycle hooks.  It deliberately has no dependency on executable agents or
VC analysis behavior.
"""

from domain.agent_review import step_agent_review_selected
from domain.common import BLUEPRINT_ID, BLUEPRINT_NAME
from domain.research_core import agentic_research_config
from domain.runtime_services import (
    build_runtime_services,
    persist_action_budget_state,
    runtime_context_for_step,
)
from domain.runtime_tools import (
    append_debug_record,
    append_event,
    write_benchmark_artifacts,
)


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
