"""Test-only access to the explicitly owned VC domain modules."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import ModuleType
from typing import Any


DOMAIN_MODULES = (
    "vc_domain.common",
    "vc_domain.runtime_tools",
    "vc_domain.intake",
    "vc_domain.research_core",
    "vc_domain.knowledge",
    "vc_domain.evidence",
    "vc_domain.research_policy",
    "vc_domain.valuation",
    "vc_domain.analysis",
    "vc_domain.research_browser",
    "vc_domain.research_agentic",
    "vc_domain.research_orchestration",
    "vc_domain.reporting",
    "vc_domain.review",
    "vc_domain.outputs",
    "vc_domain.execution_policy",
    "vc_domain.runtime_services",
    "vc_domain.agent_review",
    "vc_domain.composition",
    # Import agent modules as well so legacy monkeypatch-based integration
    # tests update names that agents imported from their owning domain module.
    # This compatibility surface is test-only and is never bundled as payload.
    "agents.public_researcher",
    "agents.valuation_scorer",
)


class DomainTestSurface:
    """Attribute proxy used by legacy integration tests during modularization.

    This is intentionally outside the runtime payload. Production agents must
    import their owning domain module directly.
    """

    def __init__(self, modules: list[ModuleType]) -> None:
        object.__setattr__(self, "_modules", modules)

    def __getattr__(self, name: str) -> Any:
        for module in reversed(self._modules):
            if name in vars(module):
                return getattr(module, name)
        raise AttributeError(name)

    def __setattr__(self, name: str, value: Any) -> None:
        if name.startswith("_") and name == "_modules":
            object.__setattr__(self, name, value)
            return
        matched = False
        for module in self._modules:
            if name in vars(module):
                setattr(module, name, value)
                matched = True
        if not matched:
            object.__setattr__(self, name, value)


def load_domain_test_surface(blueprint_dir: str | Path) -> DomainTestSurface:
    payload_root = Path(blueprint_dir) / "payloads"
    if str(payload_root) not in sys.path:
        sys.path.insert(0, str(payload_root))
    return DomainTestSurface(
        [importlib.import_module(name) for name in DOMAIN_MODULES]
    )


__all__ = ["DomainTestSurface", "load_domain_test_surface"]
