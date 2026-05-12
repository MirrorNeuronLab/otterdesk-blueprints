#!/usr/bin/env python3
import json
import os
import sys
import shutil
from pathlib import Path

from extract_utils import extract_payload
from logging_utils import get_logger

try:
    sys.path.append(os.environ.get("BIOTARGET_SOURCE_DIR", "/Users/homer/Projects/BioTarget"))
    from biotarget.stages.stage_b_structure import stage_b_structure_generation
except Exception:
    stage_b_structure_generation = None

logger = get_logger("mn.blueprint.drug_discovery.stage_b")


def write_mock_pdb(path, gene):
    atom_name = (gene or "CA")[:2].upper().ljust(2)
    with open(path, "w") as f:
        f.write("HEADER    MOCK STRUCTURE FOR MIRRORNEURON BLUEPRINT\n")
        for idx in range(1, 6):
            f.write(
                f"ATOM  {idx:5d}  CA  ALA A{idx:4d}    "
                f"{10.0 + idx:8.3f}{11.0 + idx:8.3f}{12.0 + idx:8.3f}"
                f"  1.00 20.00           {atom_name}\n"
            )
        f.write("TER\nEND\n")


def fallback_structure_generation(targets):
    structures_dir = Path("./runs/structures")
    structures_dir.mkdir(parents=True, exist_ok=True)
    structures = []
    for target in targets:
        gene = target.get("gene", "TARGET")
        protein_id = target.get("protein_id", "UNKNOWN")
        pdb_path = structures_dir / f"{gene}_{protein_id}.pdb"
        write_mock_pdb(pdb_path, gene)
        structures.append({"gene": gene, "path": str(pdb_path)})
    return structures


def load_message():
    return json.loads(Path(os.environ["MN_MESSAGE_FILE"]).read_text())


def main():
    message = load_message()
    payload = extract_payload(message)
    disease = payload.get("disease", "Alzheimer")
    targets = payload.get("targets", [])

    logger.info("Stage B: generating structures for %d targets", len(targets))
    if stage_b_structure_generation is None:
        structures = fallback_structure_generation(targets)
    else:
        try:
            structures = stage_b_structure_generation(targets, engine="openfold3")
        except Exception as exc:
            logger.warning("BioTarget Stage B failed; using fallback structures: %s", exc)
            structures = fallback_structure_generation(targets)

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
