from __future__ import annotations

import sys
from pathlib import Path


WORKSPACE = Path(__file__).resolve().parents[2]
SIBLING_SOURCES = (
    WORKSPACE / "mn-python-sdk",
    WORKSPACE / "mn-skills" / "blueprint_support_skill" / "src",
    WORKSPACE / "mn-skills" / "live_video_analysis_skill" / "src",
    WORKSPACE / "mn-skills" / "web_ui_skill" / "src",
)

for source in SIBLING_SOURCES:
    if source.is_dir() and str(source) not in sys.path:
        sys.path.insert(0, str(source))
