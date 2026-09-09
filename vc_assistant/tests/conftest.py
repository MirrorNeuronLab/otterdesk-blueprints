"""Use companion source checkouts when running the VC package tests directly."""

import sys
from pathlib import Path

blueprints_root = Path(__file__).resolve().parents[2]
workspace = blueprints_root.parent / "mirror-neuron-set"
if not workspace.is_dir():
    workspace = blueprints_root.parent
sources = [blueprints_root, workspace / "mn-python-sdk"]
sources.extend((workspace / "mn-python-sdk" / "packages").glob("*/src"))
for repository in ("mn-skills", "mn-agents"):
    sources.extend((workspace / repository).glob("*/src"))
for source in sources:
    if source.is_dir():
        sys.path.insert(0, str(source))

import pytest


@pytest.fixture(autouse=True)
def isolated_vc_payload_modules():
    prefixes = ("domain", "agents", "steps", "runtime")
    previous_path = list(sys.path)
    previous = {
        name: module
        for name, module in sys.modules.items()
        if any(name == prefix or name.startswith(prefix + ".") for prefix in prefixes)
    }
    for name in previous:
        sys.modules.pop(name, None)
    sys.path[:] = [entry for entry in sys.path if Path(entry).name != "payloads"]
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "payloads"))
    yield
    for name in list(sys.modules):
        if any(name == prefix or name.startswith(prefix + ".") for prefix in prefixes):
            sys.modules.pop(name, None)
    sys.modules.update(previous)
    sys.path[:] = previous_path
