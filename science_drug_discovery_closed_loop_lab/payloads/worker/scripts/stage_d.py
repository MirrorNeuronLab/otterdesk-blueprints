#!/usr/bin/env python3
import json
import os
import sys
import types
from pathlib import Path

# Mock drugclip for run_gnina to import without error
sys.modules["drugclip"] = types.ModuleType("drugclip")
sys.modules["drugclip.utils"] = types.ModuleType("drugclip.utils")
m = types.ModuleType("drugclip.utils.chemistry")
m.smiles_to_schnet_data = lambda *args, **kwargs: None
sys.modules["drugclip.utils.chemistry"] = m

sys.path.append("/Users/homer/Projects/BioTarget")
from extract_utils import extract_payload
from biotarget.stages.stage_d_evaluation import run_gnina
from logging_utils import get_logger

logger = get_logger("mn.blueprint.drug_discovery.stage_d")


def load_context() -> dict:
    return json.loads(Path(os.environ["MN_CONTEXT_FILE"]).read_text())


def load_message():
    return json.loads(Path(os.environ["MN_MESSAGE_FILE"]).read_text())


def main():
    context = load_context()
    job_id = context.get("job_id", "unknown_job")
    out_dir = f"/tmp/mirror_neuron_{job_id}"
    os.makedirs(out_dir, exist_ok=True)
    docking_log_file = os.path.join(out_dir, "docking.log")

    message = load_message()
    payload = extract_payload(message)
    disease = payload.get("disease", "Alzheimer")
    targets = payload.get("targets", [])
    structures = payload.get("structures", [])
    candidates = payload.get("candidates", [])

    if not structures:
        logger.error("No structures found in payload")
        sys.exit(1)

    pdb_path = structures[0]["path"]
    logger.info("Stage D: evaluating %d candidates against %s", len(candidates), pdb_path)

    evaluations = []
    for smiles in candidates:
        score, success = run_gnina(pdb_path, smiles)
        with open(docking_log_file, "a") as f:
            f.write(f"Docking Score: {score}, Success: {success}\n")
        evaluations.append(
            {"smiles": smiles, "gnina_affinity": score, "success": success}
        )

    print(
        json.dumps(
            {
                "disease": disease,
                "targets": targets,
                "structures": structures,
                "evaluations": evaluations,
            }
        )
    )


if __name__ == "__main__":
    main()
