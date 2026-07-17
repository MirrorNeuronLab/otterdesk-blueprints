"""Drug Discovery runtime preparation boundary.

The discovery service is an executable specialist under ``agents/service``;
this package intentionally contains no service or scientific workflow logic.
"""

from drug_discovery_domain.runtime_services import runtime_context_for_step

__all__ = ["runtime_context_for_step"]

