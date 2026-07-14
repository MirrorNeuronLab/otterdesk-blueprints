#!/usr/bin/env python3.11
"""Stable DockerWorker entrypoint for the VC Assistant workflow."""

from __future__ import annotations

import sys
from pathlib import Path


SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from blueprint_runtime import runtime

if __name__ == "__main__":
    runtime.main()
