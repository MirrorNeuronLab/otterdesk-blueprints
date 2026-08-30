import os
import requests
import time


ALPHAFOLD_API_URL = "https://alphafold.ebi.ac.uk/api/prediction/{protein_id}"
ALPHAFOLD_PDB_URLS = (
    "https://alphafold.ebi.ac.uk/files/AF-{protein_id}-F1-model_v6.pdb",
    "https://alphafold.ebi.ac.uk/files/AF-{protein_id}-F1-model_v5.pdb",
    "https://alphafold.ebi.ac.uk/files/AF-{protein_id}-F1-model_v4.pdb",
)
RETRIEVAL_ATTEMPTS = 2


def _download_pdb(url, destination):
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    content = response.content
    if not content.lstrip().startswith((b"HEADER", b"ATOM", b"MODEL")):
        raise RuntimeError(f"AlphaFold returned a non-PDB response from {url}")
    with open(destination, "wb") as handle:
        handle.write(content)


def _retry(operation, *, description):
    last_error = None
    for attempt in range(RETRIEVAL_ATTEMPTS):
        try:
            return operation()
        except (requests.RequestException, RuntimeError, ValueError) as error:
            last_error = error
            if attempt + 1 < RETRIEVAL_ATTEMPTS:
                time.sleep(attempt + 1)
    raise RuntimeError(f"{description}: {last_error}") from last_error


def fetch_alphafold_structure(protein_id, pdb_path):
    """Retrieve a real AlphaFold structure despite temporary API discovery outages.

    The API returns the canonical model URL when available.  AlphaFold model
    files also use stable accession-derived URLs, so a transient 5xx response
    from the discovery endpoint must not prevent a live run from retrieving
    the same public structure.
    """
    urls = []

    def lookup_prediction():
        response = requests.get(
            ALPHAFOLD_API_URL.format(protein_id=protein_id), timeout=10
        )
        response.raise_for_status()
        return response.json()

    try:
        metadata = _retry(
            lookup_prediction,
            description=f"AlphaFold prediction lookup failed for {protein_id}",
        )
        if isinstance(metadata, list) and metadata:
            pdb_url = metadata[0].get("pdbUrl")
            if isinstance(pdb_url, str) and pdb_url:
                urls.append(pdb_url)
    except RuntimeError as error:
        print(f"[!] AlphaFold API discovery failed for {protein_id}: {error}")

    urls.extend(template.format(protein_id=protein_id) for template in ALPHAFOLD_PDB_URLS)
    last_error = None
    for url in dict.fromkeys(urls):
        try:
            _retry(
                lambda url=url: _download_pdb(url, pdb_path),
                description=f"AlphaFold PDB download failed for {protein_id}",
            )
            return
        except RuntimeError as error:
            last_error = error

    raise RuntimeError(
        f"AlphaFold could not retrieve a PDB for {protein_id} through its API or model-file URLs: {last_error}"
    ) from last_error


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
                fetch_alphafold_structure(protein_id, pdb_path)

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
