"""Native scientific operations consuming immutable predecessor state."""
import re
from pathlib import Path
from mn_sdk_common.committed_artifacts import validate_embedded_references
from mn_sdk.agent_events import report_activity
from mn_sdk.blueprint_support import write_json
from biotarget.stages.stage_a_discovery import stage_a_target_discovery
from biotarget.stages.stage_b_structure import stage_b_structure_generation
from service.scripts.continuous_service import fake_fold, is_fake

from .configuration import BLUEPRINT_ID, research_inputs
from .conversation_sources import publish_inputs, publish_results


def read_discovery_state(block, inputs):
    state = block.store.read(inputs["previous"]["state"])
    validate_embedded_references(block.store, state)
    return state


def write_discovery_state(block, state, phase):
    reference = block.store.commit(f"discovery/{phase}.json", state, kind="discovery_evidence")
    write_json(block.store.path("workflow_state/drug_discovery_state.json"), state)
    publish_results(block, state)
    return reference.to_dict()


def selected_targets(targets, *, discovered):
    if not isinstance(targets, list) or not targets:
        raise ValueError("Protein targets must be a nonempty list of UniProt identifiers.")
    selected = []
    fields = ("protein_id", "gene", "score_opentargets") if discovered else ("protein_id", "gene")
    for target in targets:
        protein_id = target.get("protein_id") if isinstance(target, dict) else None
        gene = target.get("gene") if isinstance(target, dict) else None
        if not isinstance(protein_id, str) or not re.fullmatch(r"[A-Z][A-Z0-9]{5}(?:[A-Z0-9]{4})?(?:-[1-9][0-9]*)?", protein_id):
            raise ValueError("Each target requires a UniProt protein_id.")
        if not isinstance(gene, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", gene):
            raise ValueError("Each target requires a gene symbol without path characters.")
        selected.append({key: target[key] for key in fields if key in target})
    return selected


def discover_targets(block, inputs):
    report_activity("Researching target biology", owner_blueprint=BLUEPRINT_ID, run_dir=block.store.run_dir)
    inputs = research_inputs(block, inputs)
    publish_inputs(block, inputs)
    block.store.commit("inputs.json", inputs, kind="discovery_inputs")
    targets = inputs.get("targets")
    if targets is not None and not isinstance(targets, list):
        raise ValueError("Protein targets must be a list of UniProt identifiers.")
    source = "provided_protein_targets"
    if not targets:
        disease = inputs.get("disease")
        if not isinstance(disease, str) or not disease.strip():
            raise ValueError("Provide protein targets or a disease name for target discovery.")
        block.check()
        if is_fake(block.config):
            targets = [{"protein_id": "P05067", "gene": "APP"},
                       {"protein_id": "P02649", "gene": "APOE"}, {"protein_id": "P37840", "gene": "SNCA"}]
            source = "synthetic_smoke_test"
        else:
            targets = stage_a_target_discovery(disease.strip())[:3]
            source = "open_targets_disease_associations"
    state = {"targets": selected_targets(targets, discovered=source == "open_targets_disease_associations"), "disease": inputs.get("disease") or "",
             "target_source": source, "research_inputs": inputs}
    return {"target_count": len(state["targets"]), "state": write_discovery_state(block, state, "targets")}


def generate_structures(block, inputs):
    report_activity("Generating candidate structures", owner_blueprint=BLUEPRINT_ID, run_dir=block.store.run_dir)
    state = read_discovery_state(block, inputs)
    folder = block.store.path("structures")
    if is_fake(block.config):
        structures = []
        for target in state["targets"]:
            block.check()
            structures.append(fake_fold(target, folder))
    else:
        structures = stage_b_structure_generation(state["targets"], engine="openfold3", output_dir=folder, check=block.check)
    state["structure_artifacts"] = [block.store.commit_bytes(
        Path(structure["path"]).relative_to(block.store.run_dir), Path(structure["path"]).read_bytes(),
        kind="protein_structure").to_dict() for structure in structures]
    state["structures"] = structures
    return {"structure_count": len(structures), "state": write_discovery_state(block, state, "structures")}


def evaluate_binding(block, inputs):
    report_activity("Evaluating binding evidence", owner_blueprint=BLUEPRINT_ID, run_dir=block.store.run_dir)
    state = read_discovery_state(block, inputs)
    reports = state.get("service_reports") or []
    if len(reports) != 1 or reports[0].get("candidate_count") != 5:
        raise ValueError("Review requires one completed five-candidate discovery cycle.")
    evaluations = reports[0].get("top_candidates")
    if not isinstance(evaluations, list) or len(evaluations) != 5:
        raise ValueError("Review requires evaluation evidence for all five candidates.")
    state["evaluations"] = evaluations
    return {"evaluation_count": len(evaluations), "state": write_discovery_state(block, state, "evaluations")}
