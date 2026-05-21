#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path

sys.path.append("/Users/homer/Projects/BioTarget")
from extract_utils import extract_payload
from logging_utils import get_logger

logger = get_logger("mn.blueprint.drug_discovery.stage_e")


def load_context() -> dict:
    return json.loads(Path(os.environ["MN_CONTEXT_FILE"]).read_text())


def load_message() -> dict:
    return json.loads(Path(os.environ["MN_MESSAGE_FILE"]).read_text())


def main():
    context = load_context()
    job_id = context.get("job_id", "unknown_job")
    out_dir = f"/tmp/mirror_neuron_{job_id}"
    os.makedirs(out_dir, exist_ok=True)

    best_drugs_file = os.path.join(out_dir, "best_drugs.txt")

    message = load_message()
    payload = extract_payload(message)

    disease = payload.get("disease", "Unknown")
    evaluations = payload.get("evaluations", [])
    structures = payload.get("structures", [])

    gene = structures[0].get("gene", "Unknown") if structures else "Unknown"
    pdb_path = structures[0].get("path", "Unknown") if structures else "Unknown"

    logger.info("Stage E: ranking and reporting for %s", disease)

    best_evals = []
    for eval_res in evaluations:
        if eval_res.get("success"):
            best_evals.append(eval_res)
            with open(best_drugs_file, "a") as f:
                f.write(
                    f"Disease: {disease}, Gene: {gene}, PDB: {pdb_path}, SMILES: {eval_res['smiles']}, Score: {eval_res['gnina_affinity']}\n"
                )

    # Send top candidates to manager (do NOT loop back to target discovery)
    print(json.dumps({"disease": disease, "best_evals": best_evals}))


if __name__ == "__main__":
    main()
