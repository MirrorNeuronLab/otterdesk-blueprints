#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path

from extract_utils import extract_payload
from logging_utils import get_logger

try:
    sys.path.append(os.environ.get("BIOTARGET_SOURCE_DIR", "/Users/homer/Projects/BioTarget"))
    from biotarget.stages.stage_a_discovery import stage_a_target_discovery
except Exception:
    stage_a_target_discovery = None

logger = get_logger("mn.blueprint.drug_discovery.stage_a")


def fallback_targets():
    return [
        {"protein_id": "P05067", "gene": "APP", "score_opentargets": 0.96},
        {"protein_id": "P02649", "gene": "APOE", "score_opentargets": 0.91},
        {"protein_id": "P37840", "gene": "SNCA", "score_opentargets": 0.83},
    ]


def load_message():
    return json.loads(Path(os.environ["MN_MESSAGE_FILE"]).read_text())


def main():
    message = load_message()
    payload = extract_payload(message)
    disease = payload.get("disease", "Alzheimer")

    logger.info("Stage A: discovering targets for %s", disease)
    if stage_a_target_discovery is None:
        targets = fallback_targets()
    else:
        try:
            targets = stage_a_target_discovery(disease)
        except Exception as exc:
            logger.warning("BioTarget Stage A failed; using fallback targets: %s", exc)
            targets = fallback_targets()

    top_targets = targets[:3]

    print(json.dumps({"disease": disease, "targets": top_targets}))


if __name__ == "__main__":
    main()
