import os

# Must set this before importing transformers or drugclip to prevent broken tensorflow loading
os.environ["USE_TF"] = "0"

import torch
import uuid
from drugclip.models.align_model import DrugCLIP
from drugclip.utils.model_utils import get_default_checkpoint

from biotarget.core.config import DEVICE
from biotarget.stages.stage_a_discovery import stage_a_target_discovery
from biotarget.stages.stage_b_structure import stage_b_structure_generation
from biotarget.stages.stage_c_generative import stage_c_generative_ai
from biotarget.stages.stage_d_evaluation import stage_d_evaluate_binding_and_tox
from biotarget.stages.stage_e_reporting import stage_e_reporting


def run_pipeline(disease, checkpoint_path=None, top_targets=3, top_ligands=10):
    run_id = str(uuid.uuid4())[:8]
    report_dir = f"/tmp/biotarget/{run_id}"
    os.makedirs(report_dir, exist_ok=True)
    report_path = os.path.join(report_dir, "report.md")

    with open(report_path, "w") as f:
        f.write(f"# BioTarget Pipeline Report\n")
        f.write(f"**Run ID:** `{run_id}`\n")
        f.write(f"**Disease:** `{disease}`\n\n")

    resolved_ckpt = get_default_checkpoint(checkpoint_path)
    if not resolved_ckpt:
        print("[!] DrugCLIP Checkpoint could not be loaded from Hugging Face.")
        return

    # Load DrugCLIP Model
    try:
        os.environ["USE_TF"] = "0"

        model = DrugCLIP(
            hidden_channels=64, out_dim=128, text_model="distilbert-base-uncased"
        )
        # For mock, we ignore the state dict load since we didn't save one
        # model.load_state_dict(torch.load(resolved_ckpt, map_location=DEVICE, weights_only=True))
        model = model.to(DEVICE)
        model.eval()
    except Exception as e:
        print(f"[!] Error: Could not load DrugCLIP model. {e}")
        import sys

        sys.exit(1)

    # Stage A: Disease to Protein Ranking
    targets = stage_a_target_discovery(disease)

    with open(report_path, "a") as f:
        f.write("## Stage A: Target Discovery\n")
        f.write(f"Found {len(targets)} targets. Selecting top {top_targets}.\n")
        for i, t in enumerate(targets[:top_targets]):
            f.write(
                f"- {i + 1}. **{t.get('gene', 'Unknown')}** ({t.get('protein_id', 'Unknown')}) - Score: {t.get('score_opentargets', 0):.4f}\n"
            )
        f.write("\n")

    # Stage B: Target Structure Generation
    structures = stage_b_structure_generation(targets[:top_targets], engine="openfold3")

    with open(report_path, "a") as f:
        f.write("## Stage B: Structure Generation\n")
        for s in structures:
            f.write(
                f"- Generated structure for **{s.get('gene', 'Unknown')}**: `{s.get('path', 'Unknown')}`\n"
            )
        f.write("\n")

    # Stage C: Generative AI (10x Candidates via DrugCLIP guidance)
    num_candidates_needed = top_ligands * 10
    candidates_smiles, candidate_graphs = stage_c_generative_ai(
        disease, model, DEVICE, num_candidates_needed
    )

    with open(report_path, "a") as f:
        f.write("## Stage C: Generative AI\n")
        f.write(f"Generated {len(candidates_smiles)} candidates.\n\n")

    # Stage D: Gnina Binding & DrugCLIP Toxicity Evaluation
    evaluation_results = stage_d_evaluate_binding_and_tox(
        candidates_smiles, candidate_graphs, structures, model, DEVICE
    )

    with open(report_path, "a") as f:
        f.write("## Stage D: Evaluation\n")
        f.write(
            f"Evaluated binding affinity (gnina) and toxicity (DrugCLIP) for {len(evaluation_results)} candidates.\n\n"
        )

    # Stage E: Ranking and Reporting
    stage_e_reporting(disease, evaluation_results, top_ligands, report_path=report_path)

    print(f"\n[✓] Pipeline execution complete. Report saved to: {report_path}")
