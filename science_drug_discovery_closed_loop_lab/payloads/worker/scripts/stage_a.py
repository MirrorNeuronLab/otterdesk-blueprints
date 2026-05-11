#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path

sys.path.append("/Users/homer/Projects/BioTarget")
from extract_utils import extract_payload
from biotarget.stages.stage_a_discovery import stage_a_target_discovery
from logging_utils import get_logger

logger = get_logger("mn.blueprint.drug_discovery.stage_a")


def load_message():
    return json.loads(Path(os.environ["MN_MESSAGE_FILE"]).read_text())


def main():
    message = load_message()
    payload = extract_payload(message)
    disease = payload.get("disease", "Alzheimer")

    logger.info("Stage A: discovering targets for %s", disease)
    targets = stage_a_target_discovery(disease)
    top_targets = targets[:3]

    print(json.dumps({"disease": disease, "targets": top_targets}))


if __name__ == "__main__":
    main()
