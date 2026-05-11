#!/usr/bin/env python3
import json
import os
import sys
import shutil
from pathlib import Path

sys.path.append("/Users/homer/Projects/BioTarget")
from extract_utils import extract_payload
from biotarget.stages.stage_b_structure import stage_b_structure_generation
from logging_utils import get_logger

logger = get_logger("mn.blueprint.drug_discovery.stage_b")


def load_message():
    return json.loads(Path(os.environ["MN_MESSAGE_FILE"]).read_text())


def main():
    message = load_message()
    payload = extract_payload(message)
    disease = payload.get("disease", "Alzheimer")
    targets = payload.get("targets", [])

    logger.info("Stage B: generating structures for %d targets", len(targets))
    structures = stage_b_structure_generation(targets, engine="openfold3")

    shared_dir = "/tmp/biotarget_shared"
    os.makedirs(shared_dir, exist_ok=True)

    abs_structures = []
    for structure in structures:
        pdb_path = structure["path"]
        shared_pdb = os.path.join(shared_dir, os.path.basename(pdb_path))
        shutil.copy(pdb_path, shared_pdb)
        structure["path"] = shared_pdb
        abs_structures.append(structure)

    print(
        json.dumps(
            {"disease": disease, "targets": targets, "structures": abs_structures}
        )
    )


if __name__ == "__main__":
    main()
