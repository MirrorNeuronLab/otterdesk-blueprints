from __future__ import annotations

import sys
from pathlib import Path

from workspace_paths import companion_workspace

WORKSPACE = companion_workspace(Path(__file__).resolve().parents[1])
SIBLING_SOURCES = (
    Path(__file__).resolve().parents[1],
    Path(__file__).resolve().parents[2] / "mn-blueprints",
    WORKSPACE / "mn-python-sdk",
    WORKSPACE / "mn-skills" / "blueprint_support_skill" / "src",
    WORKSPACE / "mn-skills" / "live_video_analysis_skill" / "src",
    WORKSPACE / "mn-skills" / "web_ui_skill" / "src",
)

for source in SIBLING_SOURCES:
    if source.is_dir() and str(source) not in sys.path:
        sys.path.insert(0, str(source))


import pytest


@pytest.fixture(autouse=True)
def isolated_payload_modules():
    # Blueprints deliberately use the same package names inside isolated worker
    # processes. Unit tests must provide the same isolation in this process.
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
    yield
    for name in list(sys.modules):
        if any(name == prefix or name.startswith(prefix + ".") for prefix in prefixes):
            sys.modules.pop(name, None)
    sys.modules.update(previous)
    sys.path[:] = previous_path
