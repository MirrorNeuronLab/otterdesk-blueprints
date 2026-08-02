"""Only runtime preparation is exposed here; product logic stays in domain/."""

from domain.runtime_services import runtime_context_for_step

__all__ = ["runtime_context_for_step"]
