#!/usr/bin/env python3.11
"""Convert continuous-service cycle output into a bounded review handoff.

Simulation is performed inside the continuous service through configured native
or distributed adapters.  This stage must not substitute a synthetic docking
or DrugCLIP result in a live run.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from extract_utils import extract_payload
from logging_utils import get_logger


logger = get_logger("mn.blueprint.drug_discovery.cycle_review")


def load_message() -> dict:
    return json.loads(Path(os.environ["MN_MESSAGE_FILE"]).read_text(encoding="utf-8"))


def main() -> None:
    payload = extract_payload(load_message())
    reports = payload.get("reports") or payload.get("cycle_reports") or []
    if not isinstance(reports, list):
        reports = []
    latest = reports[-1] if reports else {}
    evaluations = latest.get("top_candidates") if isinstance(latest, dict) else []
    if not isinstance(evaluations, list):
        evaluations = []
    logger.info("Reviewing %d candidates from the final service cycle", len(evaluations))
    print(json.dumps({"evaluations": evaluations, "service_reports": reports, "review_required": True}))


if __name__ == "__main__":
    main()
