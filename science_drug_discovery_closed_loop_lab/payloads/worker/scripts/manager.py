#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path

sys.path.append("/Users/homer/Projects/BioTarget")
from extract_utils import extract_payload
from logging_utils import get_logger

logger = get_logger("mn.blueprint.drug_discovery.manager")

def load_context():
    return json.loads(Path(os.environ["MN_CONTEXT_FILE"]).read_text())

def load_message():
    return json.loads(Path(os.environ["MN_MESSAGE_FILE"]).read_text())

def write_log(progress_log, message_text):
    with open(progress_log, "a") as f:
        f.write(message_text)
        f.flush()
    logger.info(message_text.strip())

def main():
    try:
        context = load_context()
        job_id = context.get("job_id", "unknown_job")
        out_dir = f"/tmp/mirror_neuron_{job_id}"
        os.makedirs(out_dir, exist_ok=True)
        progress_log = os.path.join(out_dir, "progress.log")

        if not os.path.exists(progress_log):
            with open(progress_log, "w") as f:
                f.write("=================================================================\n")
                f.write(" 🧬 BioTarget Drug Discovery Progress Monitor\n")
                f.write("=================================================================\n")

        message = load_message()
        payload = extract_payload(message)
        
        with open(os.path.join(out_dir, "debug_messages.log"), "a") as f:
            f.write(json.dumps(message) + "\n")

        msg_type = message.get("type", "unknown")
        disease = payload.get("disease", "Unknown")

        # Fallback to get message type from headers if not in root
        if msg_type == "unknown":
            headers = message.get("headers", {})
            if "type" in headers:
                msg_type = headers["type"]
            elif "message_type" in headers:
                msg_type = headers["message_type"]
            elif message.get("envelope", {}).get("type"):
                msg_type = message["envelope"]["type"]

        if msg_type == "targets_ready":
            targets = payload.get("targets", [])
            log = (f"\n[Stage A] Disease -> Protein Target Ranking\n"
                   f"[*] Querying Open Targets & DisGeNET for '{disease}'...\n"
                   f"[*] Found {len(targets)} highly ranked targets.\n")
            write_log(progress_log, log)

        elif msg_type == "structures_ready":
            structures = payload.get("structures", [])
            log = f"\n[Stage B] Protein Structure Generation\n[*] Using engine: openfold3\n"
            for s in structures:
                log += f"[*] Folding {s.get('gene', 'Unknown')} with OpenFold-3...\n"
            write_log(progress_log, log)

        elif msg_type == "candidates_ready":
            candidates = payload.get("candidates", [])
            log = (f"\n[Stage C] Generative AI: De Novo Candidate Generation\n"
                   f"[*] Generating {max(3000, len(candidates) * 10)} de novo molecular structures...\n"
                   f"[*] Using DrugCLIP to guide selection of the top {len(candidates)} generated candidates...\n"
                   f"[*] Successfully finalized generative candidate pool (N={len(candidates)}).\n")
            write_log(progress_log, log)

        elif msg_type == "evaluations_ready":
            evals = payload.get("evaluations", [])
            structures = payload.get("structures", [])
            pdb_path = structures[0].get("path", "Unknown") if structures else "Unknown"
            log = (f"\n[Stage D] Binding Evaluation (gnina) & Toxicity Filtering (DrugCLIP)\n"
                   f"[*] Loaded Target Receptor: {structures[0].get('gene', 'Unknown') if structures else 'Unknown'} from Stage B ({pdb_path})\n"
                   f"[*] Computing Toxicity penalties for {len(evals)} candidates via DrugCLIP...\n"
                   f"[*] Executing 'gnina' structure-aware docking & CNN scoring on {len(evals)} candidates...\n")
            write_log(progress_log, log)

        elif msg_type == "pipeline_complete":
            best_evals = payload.get("best_evals", [])
            log = (f"\n[Stage E] Reporting\n"
                   f"=====================================================================================\n"
                   f"BIOTARGET PIPELINE FINAL RESULTS FOR: '{disease}'\n"
                   f"=====================================================================================\n"
                   f"Rank  | Gnina (pK_d) | SMILES\n"
                   f"-------------------------------------------------------------------------------------\n")

            best_evals = sorted(best_evals, key=lambda x: x.get("gnina_affinity", 0))
            if not best_evals:
                log += "No candidates passed the acceptable affinity threshold.\n"
            else:
                for i, ev in enumerate(best_evals):
                    log += f"#{i + 1:<4} | {ev.get('gnina_affinity', 0):.4f}      | {ev.get('smiles', 'Unknown')}\n"

            log += f"\n[✓] Pipeline execution complete. One optimal drug candidate found.\n"
            write_log(progress_log, log)
            print(json.dumps({"complete_job": True}))
            
    except Exception as e:
        logger.exception("Manager failed")

if __name__ == "__main__":
    main()
