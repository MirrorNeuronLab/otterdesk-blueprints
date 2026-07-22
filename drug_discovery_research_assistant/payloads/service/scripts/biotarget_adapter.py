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


_GENERIC_MODEL_BINDINGS: dict[str, Any] = {}


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def dump_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def biotarget_source(request: dict[str, Any]) -> Path:
    bundled = Path(__file__).resolve().parents[2]
    if not (bundled / "biotarget" / "pipeline.py").is_file():
        raise RuntimeError(f"Bundled BioTarget package is missing from the staged payload: {bundled}")
    source = bundled
    os.environ["USE_TF"] = "0"
    os.environ["BIOTARGET_SOURCE_DIR"] = str(source)
    if str(source) not in sys.path:
        sys.path.insert(0, str(source))
    return source


def drugclip_config(request: dict[str, Any]) -> dict[str, Any]:
    value = request.get("drugclip")
    return value if isinstance(value, dict) else {}


def prepare_problem_specific_model(request: dict[str, Any]) -> dict[str, Any] | None:
    """Prepare DrugClip without declaring it as a shared LLM runtime model."""
    config = drugclip_config(request)
    generic = config.get("generic_model") if isinstance(config.get("generic_model"), dict) else {}
    if generic.get("enabled") is False:
        return None
    model_ref = str(generic.get("model_ref") or config.get("model_ref") or "").strip()
    if not model_ref:
        raise RuntimeError("DrugClip cannot run: no Hugging Face model reference is configured.")
    cache_key = json.dumps(
        {
            "model_ref": model_ref,
            "runtime": generic.get("runtime", "auto"),
            "backend": generic.get("backend", "auto"),
            "context_size": generic.get("context_size"),
            "docker": generic.get("docker"),
        },
        sort_keys=True,
        default=str,
    )
    cached = _GENERIC_MODEL_BINDINGS.get(cache_key)
    if cached is not None:
        return cached
    try:
        from mn_use_generic_model_skill import (
            GenericModelUnavailableError,
            prepare_model,
        )

        docker = generic.get("docker") if isinstance(generic.get("docker"), dict) else None
        if isinstance(docker, dict) and docker.get("enabled") is not True:
            docker = None
        binding = prepare_model(
            model_ref,
            runtime=str(generic.get("runtime") or "auto"),
            backend=str(generic.get("backend") or "auto"),
            context_size=generic.get("context_size"),
            docker=docker,
        )
    except ImportError as error:  # pragma: no cover - depends on native worker image
        raise RuntimeError("DrugClip cannot run: mirrorneuron-use-generic-model-skill is not installed on this worker.") from error
    except GenericModelUnavailableError as error:
        raise RuntimeError(str(error)) from error
    except Exception as error:
        raise RuntimeError(f"DrugClip cannot run: {error}") from error
    result = binding.to_dict()
    _GENERIC_MODEL_BINDINGS[cache_key] = result
    return result


def load_drugclip(request: dict[str, Any]) -> tuple[Any, Any]:
    """Load the exact graph-text checkpoint used by the local BioTarget stages."""
    prepare_problem_specific_model(request)
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


def molecule_graph(smiles: str) -> Any:
    """Use DrugClip's current PyG graph API, not BioTarget's stale dict adapter."""
    from drugclip.utils.chemistry import smiles_to_schnet_data

    graph = smiles_to_schnet_data(smiles)
    if graph is None:
        raise RuntimeError(f"DrugClip could not build a 3D molecular graph for {smiles!r}.")
    return graph


def score_graphs(model: Any, device: Any, graphs: list[Any], prompt: str) -> Any:
    import torch
    from torch_geometric.data import Batch

    with torch.no_grad():
        text_embedding = model.text_encoder([prompt])
        text_embedding = torch.nn.functional.normalize(text_embedding, p=2, dim=1)
        batch = Batch.from_data_list(graphs).to(device)
        graph_embedding = model.graph_encoder(batch.z, batch.pos, batch.batch)
        graph_embedding = torch.nn.functional.normalize(graph_embedding, p=2, dim=1)
        return torch.matmul(text_embedding, graph_embedding.T).squeeze(0)


def candidate_generation(request: dict[str, Any], work_dir: Path) -> dict[str, Any]:
    prepare_problem_specific_model(request)
    biotarget_source(request)
    from biotarget.core.utils import get_seed_smiles

    model, device = load_drugclip(request)
    service = request.get("service") if isinstance(request.get("service"), dict) else {}
    candidate_count = int(service.get("candidate_count") or service.get("simulation_top_k", 16) * 10)
    pool = get_seed_smiles(max(3000, candidate_count * 5))
    valid_smiles: list[str] = []
    graphs: list[Any] = []
    for smiles in pool:
        try:
            graphs.append(molecule_graph(str(smiles)))
            valid_smiles.append(str(smiles))
        except RuntimeError:
            continue
    if not graphs:
        raise RuntimeError("BioTarget candidate pool produced no valid DrugClip molecular graphs.")
    scores = score_graphs(model, device, graphs, design_prompt(request))
    selected = sorted(
        ((float(scores[index].item()), smiles) for index, smiles in enumerate(valid_smiles)),
        key=lambda item: (-item[0], item[1]),
    )[:candidate_count]
    return {
        "candidates": [
            {
                "candidate_id": f"drugclip-{request.get('cycle_id', 0)}-{index}",
                "smiles": smiles,
                "drugclip_score": score,
                "provenance": "BioTarget Stage C candidate pool; homerquan/DrugClip text-molecular-graph alignment",
            }
            for index, (score, smiles) in enumerate(selected)
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
    prepare_problem_specific_model(request)
    biotarget_source(request)

    candidate = request.get("candidate") if isinstance(request.get("candidate"), dict) else {}
    structure = request.get("structure") if isinstance(request.get("structure"), dict) else {}
    smiles = str(candidate.get("smiles") or "")
    if not smiles:
        raise RuntimeError("DrugClip scoring request requires candidate.smiles.")
    model, device = load_drugclip(request)
    score = float(score_graphs(model, device, [molecule_graph(smiles)], design_prompt(request))[0].item())
    return {
        "candidate": candidate,
        "structure": structure,
        "drugclip_score": score,
        "provenance": "homerquan/DrugClip graph-text alignment via BioTarget",
        "model_ref": drugclip_config(request).get("model_ref", "hf.co/homerquan/DrugClip"),
    }


def simulation(request: dict[str, Any], work_dir: Path) -> dict[str, Any]:
    prepare_problem_specific_model(request)
    biotarget_source(request)
    from biotarget.stages.stage_d_evaluation import stage_d_evaluate_binding_and_tox

    screen = request.get("screen") if isinstance(request.get("screen"), dict) else {}
    candidate = screen.get("candidate") if isinstance(screen.get("candidate"), dict) else {}
    structure = screen.get("structure") if isinstance(screen.get("structure"), dict) else {}
    smiles = str(candidate.get("smiles") or "")
    if not smiles or not structure.get("path"):
        raise RuntimeError("BioTarget simulation requires screen.candidate.smiles and screen.structure.path.")
    model, device = load_drugclip(request)
    molecular_graph = molecule_graph(smiles)
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
