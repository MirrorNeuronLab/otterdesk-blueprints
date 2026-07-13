#!/usr/bin/env python3.11
"""Write a review-only summary after the continuous service is stopped."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from extract_utils import extract_payload
from logging_utils import get_logger


logger = get_logger("mn.blueprint.drug_discovery.stage_e")


def load_message() -> dict:
    return json.loads(Path(os.environ["MN_MESSAGE_FILE"]).read_text(encoding="utf-8"))


def rank_key(result: dict) -> tuple[float, float]:
    return (
        float(result.get("simulation_stability", float("-inf"))),
        float(result.get("drugclip_score", float("-inf"))),
    )


def main() -> None:
    payload = extract_payload(load_message())
    evaluations = payload.get("evaluations") if isinstance(payload.get("evaluations"), list) else []
    ranked = sorted((item for item in evaluations if isinstance(item, dict)), key=rank_key, reverse=True)
    report = {
        "schema_version": "mn.blueprint.continuous_discovery_review.v1",
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "candidate_count": len(ranked),
        "ranked_candidates": ranked[:20],
        "recommendation": "review_required",
        "review_boundary": "Computational hypotheses only. A human scientific reviewer must assess evidence before laboratory, clinical, regulatory, procurement, or external-system action.",
        "missing_evidence": [
            "experimental binding and selectivity data",
            "ADMET and toxicity validation",
            "reproducible simulation protocol and independent review",
        ],
    }
    run_dir = Path(os.environ.get("MN_RUN_DIR") or "/tmp")
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "discovery_service_review.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    logger.info("Wrote review-only summary for %d candidates", len(ranked))
    print(json.dumps({"best_evals": ranked[:20], "review_report": report, "review_required": True}))


if __name__ == "__main__":
    main()
