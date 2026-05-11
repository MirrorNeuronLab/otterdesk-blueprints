#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

try:
    from mn_blueprint_support.solution_runner import main
except ModuleNotFoundError:
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "mn-skills" / "blueprint_support_skill" / "src"
        if candidate.exists():
            sys.path.insert(0, str(candidate))
            break
    from mn_blueprint_support.solution_runner import main

BLUEPRINT_ID = 'finance_portfolio_crash_stress_lab'


if __name__ == "__main__":
    main([BLUEPRINT_ID] + sys.argv[1:])
