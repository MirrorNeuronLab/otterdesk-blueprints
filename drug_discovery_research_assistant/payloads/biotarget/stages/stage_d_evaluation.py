import os
import torch
import shutil
import tempfile
import subprocess
from torch_geometric.data import Batch
from tqdm import tqdm
from rdkit import Chem
from rdkit.Chem import AllChem
from biotarget.core.utils import normalize_01


def run_gnina(receptor_path, ligand_smiles):
    executable = shutil.which("gnina")
    if not executable:
        raise RuntimeError(
            "GNINA is not installed in the NVIDIA DockerWorker image. "
            "Rebuild the drug-discovery DockerWorker image before running this blueprint."
        )

    ligand_sdf = None
    try:
        mol = Chem.MolFromSmiles(ligand_smiles)
        mol = Chem.AddHs(mol)
        res = AllChem.EmbedMolecule(
            mol, randomSeed=42, maxAttempts=3, useRandomCoords=True
        )
        if res == -1:
            return 0.0, False

        AllChem.MMFFOptimizeMolecule(mol, maxIters=10)

        with tempfile.NamedTemporaryFile(suffix=".sdf", delete=False, dir="/tmp") as f:
            ligand_sdf = f.name

        writer = Chem.SDWriter(ligand_sdf)
        writer.write(mol)
        writer.close()

        receptor_dir = os.path.dirname(os.path.abspath(receptor_path))
        receptor_name = os.path.basename(receptor_path)

        # GNINA has issues with multi-MODEL PDB files from AlphaFold, so we clean it
        cleaned_receptor = os.path.join(receptor_dir, f"cleaned_{receptor_name}")
        with open(receptor_path, "r") as fin:
            with open(cleaned_receptor, "w") as fout:
                for line in fin:
                    if line.startswith("MODEL") or line.startswith("ENDMDL"):
                        continue
                    fout.write(line)
        cmd = [
            executable,
            "-r",
            cleaned_receptor,
            "-l",
            ligand_sdf,
            "--score_only",
            "--cnn",
            "fast",
        ]

        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=300
        )  # Increased timeout for slow emulation

        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip()
            raise RuntimeError(
                f"GNINA failed with exit code {result.returncode}: {detail[:500]}"
            )

        for line in result.stdout.split("\n"):
            if "CNN_VS" in line:
                pass  # gnina prints some lines starting with CNN_VS
            elif "CNN affinity" in line or "CNNaffinity" in line:
                parts = line.split()
                for p in parts:
                    try:
                        return float(p), True
                    except ValueError:
                        pass

        # fallback parsing for other gnina versions
        if "Affinity:" in result.stdout:
            for line in result.stdout.split("\n"):
                if "Affinity:" in line:
                    try:
                        return float(line.split()[1]), True
                    except (ValueError, IndexError):
                        pass

    except subprocess.TimeoutExpired as error:
        raise RuntimeError("GNINA timed out.") from error
    except RuntimeError:
        raise
    except Exception as error:
        raise RuntimeError(f"GNINA execution failed: {error}") from error
    finally:
        if ligand_sdf and os.path.exists(ligand_sdf):
            os.remove(ligand_sdf)

    raise RuntimeError("GNINA returned no parseable affinity score.")


def stage_d_evaluate_binding_and_tox(
    candidates, candidate_graphs, structures, model, device
):
    print(f"\n[Stage D] Binding Evaluation (gnina) & Toxicity Filtering (DrugCLIP)")
    target_protein = structures[0]
    receptor_path = target_protein["path"]
    print(
        f"[*] Loaded Target Receptor: {target_protein['gene']} from Stage B ({receptor_path})"
    )

    if not shutil.which("gnina"):
        raise RuntimeError(
            "GNINA is unavailable. Candidate generation must run in the bundled NVIDIA DockerWorker image."
        )

    print(
        f"[*] Computing Toxicity penalties for {len(candidates)} candidates via DrugCLIP..."
    )
    with torch.no_grad():
        tox_emb = model.text_encoder(
            [
                "This molecule failed clinical trials due to severe toxicity and side effects."
            ]
        )
        tox_emb = torch.nn.functional.normalize(tox_emb, p=2, dim=1)

        all_graph_embs = []
        batch_size = 256
        with torch.amp.autocast("cuda", enabled=torch.cuda.is_available()):
            for i in range(0, len(candidate_graphs), batch_size):
                batch = Batch.from_data_list(candidate_graphs[i : i + batch_size]).to(
                    device
                )
                graph_emb = model.graph_encoder(batch.z, batch.pos, batch.batch)
                all_graph_embs.append(
                    torch.nn.functional.normalize(graph_emb, p=2, dim=1)
                )

        all_graph_embs = torch.cat(all_graph_embs, dim=0)
        raw_tox_scores = torch.matmul(tox_emb, all_graph_embs.T).reshape(-1)
        norm_tox_scores = normalize_01(raw_tox_scores).reshape(-1)

    print(
        f"[*] Executing 'gnina' structure-aware docking & CNN scoring on {len(candidates)} candidates..."
    )

    results = []

    for idx, sm in enumerate(tqdm(candidates, desc="Docking")):
        gnina_affinity, _is_real = run_gnina(receptor_path, sm)

        results.append(
            {
                "smiles": sm,
                "gnina_affinity": gnina_affinity,
                "tox_penalty": norm_tox_scores[idx].item(),
            }
        )

    return results
