#!/usr/bin/env python3.11
import json
import os
import sys
from pathlib import Path

from extract_utils import extract_payload
from logging_utils import get_logger

try:
    if os.environ.get("BIOTARGET_SOURCE_DIR"):
        sys.path.append(os.environ["BIOTARGET_SOURCE_DIR"])
    from biotarget.stages.stage_a_discovery import stage_a_target_discovery
except Exception as error:
    stage_a_target_discovery = None
    stage_a_import_error = error
else:
    stage_a_import_error = None

logger = get_logger("mn.blueprint.drug_discovery.stage_a")


def fallback_targets():
    return [
        {"protein_id": "P05067", "gene": "APP", "score_opentargets": 0.96},
        {"protein_id": "P02649", "gene": "APOE", "score_opentargets": 0.91},
        {"protein_id": "P37840", "gene": "SNCA", "score_opentargets": 0.83},
    ]


def load_message():
    return json.loads(Path(os.environ["MN_MESSAGE_FILE"]).read_text())


def fake_mode() -> bool:
    if os.environ.get("MN_SCIENCE_FAKE_MODE") == "1":
        return True
    try:
        return str(json.loads(os.environ.get("MN_BLUEPRINT_CONFIG_JSON", "{}")).get("mode") or "").lower() in {"fake", "mock"}
    except json.JSONDecodeError:
        return False


def main():
    message = load_message()
    payload = extract_payload(message)
    disease = payload.get("disease", "Alzheimer")

    logger.info("Stage A: discovering targets for %s", disease)
    if stage_a_target_discovery is None:
        if not fake_mode():
            raise RuntimeError(
                "Live target discovery could not import the bundled BioTarget adapter: "
                f"{stage_a_import_error}"
            ) from stage_a_import_error
        targets = fallback_targets()
    else:
        try:
            targets = stage_a_target_discovery(disease)
        except Exception as exc:
            if not fake_mode():
                raise RuntimeError(f"Live target discovery failed: {exc}") from exc
            logger.warning("BioTarget Stage A failed in fake mode; using synthetic targets: %s", exc)
            targets = fallback_targets()

    top_targets = targets[:3]

    print(json.dumps({"disease": disease, "targets": top_targets}))


if __name__ == "__main__":
    main()
