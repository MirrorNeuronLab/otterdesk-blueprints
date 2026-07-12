#!/usr/bin/env python3.11
"""JSON adapter for the local BioTarget + homerquan/DrugClip implementation.

This runs as a native HostLocal or cross-box dispatched process.  It deliberately
uses BioTarget's stage modules rather than reproducing their model logic in the
blueprint.  Dependencies must be installed on the worker that receives the job.
"""
from __future__ import annotations

import argparse
import contextlib
import json
import os
import sys
from pathlib import Path
from typing import Any, Iterator


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def dump_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def biotarget_source(request: dict[str, Any]) -> Path:
    config = request.get("biotarget") if isinstance(request.get("biotarget"), dict) else {}
    configured = os.environ.get("BIOTARGET_SOURCE_DIR") or config.get("source_dir")
    if not configured:
        raise RuntimeError("BioTarget source directory is not configured; set BIOTARGET_SOURCE_DIR or biotarget.source_dir.")
    source = Path(str(configured)).expanduser().resolve()
    if not (source / "biotarget" / "pipeline.py").is_file():
        raise RuntimeError(f"BioTarget source directory is unavailable or invalid: {source}")
    os.environ["USE_TF"] = "0"
    os.environ["BIOTARGET_SOURCE_DIR"] = str(source)
    if str(source) not in sys.path:
        sys.path.insert(0, str(source))
    return source


def drugclip_config(request: dict[str, Any]) -> dict[str, Any]:
    value = request.get("drugclip")
    return value if isinstance(value, dict) else {}


def load_drugclip(request: dict[str, Any]) -> tuple[Any, Any]:
    """Load the exact graph-text checkpoint used by the local BioTarget stages."""
    biotarget_source(request)
    import torch
    from drugclip.models.align_model import DrugCLIP

    config = drugclip_config(request)
    checkpoint_path = str(config.get("checkpoint_path") or os.environ.get("DRUGCLIP_CHECKPOINT") or "").strip()
    if checkpoint_path:
        checkpoint = Path(checkpoint_path).expanduser()
        if not checkpoint.is_file():
            raise RuntimeError(f"Configured DrugClip checkpoint does not exist: {checkpoint}")
    else:
        repo_id = str(config.get("checkpoint_repo") or "homerquan/DrugClip")
        filename = str(config.get("checkpoint_filename") or "best.ckpt")
        try:
            from huggingface_hub import hf_hub_download
        except ImportError as error:  # pragma: no cover - depends on native worker image
            raise RuntimeError("BioTarget DrugClip loading requires huggingface_hub or DRUGCLIP_CHECKPOINT.") from error
        checkpoint = Path(hf_hub_download(repo_id=repo_id, filename=filename))

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = DrugCLIP(hidden_channels=64, out_dim=128, text_model="distilbert-base-uncased")
    state_dict = torch.load(checkpoint, map_location=device)
    model.load_state_dict(state_dict)
    model = model.to(device)
    model.eval()
    return model, device


@contextlib.contextmanager
def working_directory(path: Path) -> Iterator[None]:
    path.mkdir(parents=True, exist_ok=True)
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


def design_prompt(request: dict[str, Any]) -> str:
    if isinstance(request.get("design_prompt"), str) and request["design_prompt"].strip():
        return request["design_prompt"].strip()
    targets = request.get("targets") if isinstance(request.get("targets"), list) else []
    target_names = ", ".join(
        str(target.get("gene") or target.get("protein_id") or "")
        for target in targets
        if isinstance(target, dict)
    )
    return f"A potent small molecule inhibitor for {target_names or 'the configured therapeutic target'} treatment."


def candidate_generation(request: dict[str, Any], work_dir: Path) -> dict[str, Any]:
    biotarget_source(request)
    from biotarget.stages.stage_c_generative import stage_c_generative_ai

    model, device = load_drugclip(request)
    service = request.get("service") if isinstance(request.get("service"), dict) else {}
    candidate_count = int(service.get("candidate_count") or service.get("simulation_top_k", 16) * 10)
    smiles, _graphs = stage_c_generative_ai(design_prompt(request), model, device, candidate_count)
    return {
        "candidates": [
            {
                "candidate_id": f"drugclip-{request.get('cycle_id', 0)}-{index}",
                "smiles": value,
                "provenance": "BioTarget Stage C; homerquan/DrugClip text-molecular-graph alignment",
            }
            for index, value in enumerate(smiles)
        ],
        "model_ref": drugclip_config(request).get("model_ref", "hf.co/homerquan/DrugClip"),
    }


def folding(request: dict[str, Any], work_dir: Path) -> dict[str, Any]:
    biotarget_source(request)
    from biotarget.stages.stage_b_structure import stage_b_structure_generation

    target = request.get("target") if isinstance(request.get("target"), dict) else {}
    if not target:
        raise RuntimeError("BioTarget folding request requires target.")
    normalized_target = {
        "gene": str(target.get("gene") or target.get("protein_id") or "TARGET"),
        "protein_id": str(target.get("protein_id") or target.get("gene") or "TARGET"),
    }
    with working_directory(work_dir):
        structures = stage_b_structure_generation([normalized_target], engine="openfold3")
    if not structures:
        raise RuntimeError("BioTarget Stage B returned no structure.")
    return {"target": normalized_target, **structures[0], "provenance": "BioTarget Stage B"}


def graph_text_score(request: dict[str, Any], _work_dir: Path) -> dict[str, Any]:
    biotarget_source(request)
    import torch
    from torch_geometric.data import Batch, Data
    from biotarget.core.utils import process_single_molecule

    candidate = request.get("candidate") if isinstance(request.get("candidate"), dict) else {}
    structure = request.get("structure") if isinstance(request.get("structure"), dict) else {}
    smiles = str(candidate.get("smiles") or "")
    if not smiles:
        raise RuntimeError("DrugClip scoring request requires candidate.smiles.")
    processed = process_single_molecule(smiles)
    if processed is None:
        raise RuntimeError(f"BioTarget could not build a 3D molecular graph for {smiles!r}.")
    _, graph = processed
    model, device = load_drugclip(request)
    data = Data(z=torch.tensor(graph["z"], dtype=torch.long), pos=torch.tensor(graph["pos"], dtype=torch.float32))
    with torch.no_grad():
        text_embedding = model.text_encoder([design_prompt(request)])
        text_embedding = torch.nn.functional.normalize(text_embedding, p=2, dim=1)
        batch = Batch.from_data_list([data]).to(device)
        graph_embedding = model.graph_encoder(batch.z, batch.pos, batch.batch)
        graph_embedding = torch.nn.functional.normalize(graph_embedding, p=2, dim=1)
        score = float(torch.matmul(text_embedding, graph_embedding.T).squeeze().item())
    return {
        "candidate": candidate,
        "structure": structure,
        "drugclip_score": score,
        "provenance": "homerquan/DrugClip graph-text alignment via BioTarget",
        "model_ref": drugclip_config(request).get("model_ref", "hf.co/homerquan/DrugClip"),
    }


def simulation(request: dict[str, Any], work_dir: Path) -> dict[str, Any]:
    biotarget_source(request)
    import torch
    from biotarget.core.utils import process_single_molecule
    from biotarget.stages.stage_d_evaluation import stage_d_evaluate_binding_and_tox
    from torch_geometric.data import Data

    screen = request.get("screen") if isinstance(request.get("screen"), dict) else {}
    candidate = screen.get("candidate") if isinstance(screen.get("candidate"), dict) else {}
    structure = screen.get("structure") if isinstance(screen.get("structure"), dict) else {}
    smiles = str(candidate.get("smiles") or "")
    if not smiles or not structure.get("path"):
        raise RuntimeError("BioTarget simulation requires screen.candidate.smiles and screen.structure.path.")
    processed = process_single_molecule(smiles)
    if processed is None:
        raise RuntimeError(f"BioTarget could not build a 3D molecular graph for {smiles!r}.")
    _, graph = processed
    model, device = load_drugclip(request)
    molecular_graph = Data(
        z=torch.tensor(graph["z"], dtype=torch.long),
        pos=torch.tensor(graph["pos"], dtype=torch.float32),
    )
    with working_directory(work_dir):
        evaluations = stage_d_evaluate_binding_and_tox([smiles], [molecular_graph], [structure], model, device)
    if not evaluations:
        raise RuntimeError("BioTarget Stage D returned no evaluation.")
    evaluation = evaluations[0]
    affinity = float(evaluation.get("gnina_affinity") or 0.0)
    toxicity = float(evaluation.get("tox_penalty") or 0.0)
    return {
        **screen,
        **evaluation,
        "simulation_stability": affinity - 0.5 * toxicity,
        "simulation_status": "biotarget_stage_d_gnina",
        "provenance": "BioTarget Stage D; GNINA binding score plus DrugClip toxicity penalty",
    }


ADAPTERS = {
    "candidate_generator": candidate_generation,
    "folding": folding,
    "drugclip": graph_text_score,
    "simulation": simulation,
}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run a native BioTarget adapter job.")
    parser.add_argument("--adapter", required=True, choices=sorted(ADAPTERS))
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    request = load_json(Path(args.input))
    result = ADAPTERS[args.adapter](request, Path(args.output).parent)
    dump_json(Path(args.output), result)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
