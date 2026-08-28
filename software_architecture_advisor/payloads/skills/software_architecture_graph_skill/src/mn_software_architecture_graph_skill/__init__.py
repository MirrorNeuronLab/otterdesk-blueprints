"""Air-gapped, standard-library architecture evidence analysis."""

from .analysis import analyze_graph, build_architecture_graph, build_inventory
from .deep_analysis import build_deep_evidence, compact_inventory

__all__ = [
    "analyze_graph",
    "build_architecture_graph",
    "build_deep_evidence",
    "build_inventory",
    "compact_inventory",
]
