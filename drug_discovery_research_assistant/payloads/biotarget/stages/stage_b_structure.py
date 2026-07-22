import os
import requests
import time


def ensure_openfold3_weights():
    weights_dir = os.path.expanduser("~/.biotarget/openfold3_weights")
    if not os.path.exists(weights_dir):
        os.makedirs(weights_dir, exist_ok=True)
    return True


def stage_b_structure_generation(targets, engine):
    print(f"\n[Stage B] Protein Structure Generation")
    print(f"[*] Using engine: {engine}")

    ensure_openfold3_weights()

    structures = []

    os.makedirs("./runs/structures", exist_ok=True)

    for t in targets:
        gene = t["gene"]
        protein_id = t["protein_id"]
        print(
            f"[*] Fetching 3D conformation for {gene} ({protein_id}) from AlphaFold DB..."
        )

        pdb_path = f"./runs/structures/{gene}_{protein_id}.pdb"

        # Download PDB file if it doesn't exist
        if not os.path.exists(pdb_path):
            try:
                # AlphaFold API uses v4 or v6, mostly v4 is widespread, let's try to query EBI API to get the correct URL
                af_api_url = f"https://alphafold.ebi.ac.uk/api/prediction/{protein_id}"
                resp = requests.get(af_api_url, timeout=10)
                resp.raise_for_status()
                af_data = resp.json()

                if af_data and len(af_data) > 0:
                    pdb_url = af_data[0].get("pdbUrl")
                    if pdb_url:
                        print(f"[*] Downloading PDB from {pdb_url}...")
                        pdb_resp = requests.get(pdb_url, timeout=30)
                        pdb_resp.raise_for_status()

                        with open(pdb_path, "wb") as f:
                            f.write(pdb_resp.content)
                    else:
                        print(
                            f"[!] Could not find PDB URL in AlphaFold DB response for {protein_id}"
                        )
                        continue
                else:
                    print(f"[!] No AlphaFold prediction found for {protein_id}")
                    continue

            except Exception as e:
                print(f"[!] Failed to fetch AlphaFold structure for {protein_id}: {e}")
                continue

        if os.path.exists(pdb_path):
            print(f"[*] Successfully saved structure to {pdb_path}")
            structures.append({"gene": gene, "path": pdb_path})

    if not structures:
        print(
            "[!] Could not fetch any structures. Exiting to prevent pipeline failure."
        )
        import sys

        sys.exit(1)

    return structures
