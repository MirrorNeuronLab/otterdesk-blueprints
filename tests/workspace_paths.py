from __future__ import annotations

from pathlib import Path


def companion_workspace(blueprint_root: Path) -> Path:
    """Locate companion MN repositories in sibling or monorepo layouts."""
    sibling_root = blueprint_root.resolve().parent
    nested_root = sibling_root / "mirror-neuron-set"
    if (nested_root / "mn-python-sdk").is_dir():
        return nested_root
    return sibling_root
