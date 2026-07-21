"""Drug Discovery runtime preparation boundary.

The discovery service support scripts live under the bundle-level ``service``;
this package intentionally contains no service or scientific workflow logic.
"""

from domain.runtime_services import runtime_context_for_step

__all__ = ["runtime_context_for_step"]
