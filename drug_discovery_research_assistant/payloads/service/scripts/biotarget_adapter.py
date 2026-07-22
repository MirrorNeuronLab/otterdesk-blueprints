#!/usr/bin/env python3.11
"""JSON adapter for the local BioTarget + homerquan/DrugClip implementation.

This runs as a native DockerWorker or cross-box dispatched process.  It deliberately
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


_MODEL_REFERENCE_VALIDATIONS: dict[str, dict[str, Any]] = {}


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


def prepare_problem_specific_model(request: dict[str, Any]) -> dict[str, Any]:
    """Validate the DrugClip source before its native checkpoint is loaded.

    DrugClip is a graph/text checkpoint, not a generative model that Docker
    Model Runner can serve.  The generic-model skill therefore owns canonical
    Hugging Face reference validation; this adapter owns the actual native
    checkpoint download and ``DrugCLIP`` execution.
    """
    config = drugclip_config(request)
    generic = config.get("generic_model") if isinstance(config.get("generic_model"), dict) else {}
    if generic.get("enabled") is not True:
        raise RuntimeError(
            "DrugClip cannot run: native checkpoint execution requires generic_model reference validation to be enabled."
        )
    model_ref = str(generic.get("model_ref") or config.get("model_ref") or "").strip()
    if not model_ref:
        raise RuntimeError("DrugClip cannot run: no Hugging Face model reference is configured.")
    cached = _MODEL_REFERENCE_VALIDATIONS.get(model_ref)
    if cached is not None:
        return cached
    try:
        from mn_use_generic_model_skill import normalize_model_reference

        source_model, normalized_model = normalize_model_reference(model_ref)
    except ImportError as error:  # pragma: no cover - depends on native worker image
        raise RuntimeError("DrugClip cannot run: mirrorneuron-use-generic-model-skill is not installed on this worker.") from error
    except Exception as error:
        raise RuntimeError(f"DrugClip cannot validate its Hugging Face model reference: {error}") from error

    repository = normalized_model
    for prefix in ("hf.co/", "huggingface.co/"):
        if repository.startswith(prefix):
            repository = repository[len(prefix) :]
            break
    repository, separator, revision = repository.partition(":")
    if not repository or "/" not in repository:
        raise RuntimeError(f"DrugClip cannot run: invalid normalized Hugging Face repository {normalized_model!r}.")
    configured_repository = str(config.get("checkpoint_repo") or repository).strip()
    if configured_repository != repository:
        raise RuntimeError(
            "DrugClip checkpoint repository must match the validated model reference: "
            f"{configured_repository!r} != {repository!r}."
        )
    result = {
        "model_ref": source_model,
        "normalized_model_ref": normalized_model,
        "checkpoint_repo": repository,
        "checkpoint_revision": revision or None,
        "execution": "native_checkpoint",
    }
    _MODEL_REFERENCE_VALIDATIONS[model_ref] = result
    return result


def load_drugclip(request: dict[str, Any]) -> tuple[Any, Any]:
    """Load the exact graph-text checkpoint used by the local BioTarget stages."""
    model_reference = prepare_problem_specific_model(request)
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
        repo_id = str(model_reference["checkpoint_repo"])
        filename = str(config.get("checkpoint_filename") or "best.ckpt")
        try:
            from huggingface_hub import hf_hub_download
        except ImportError as error:  # pragma: no cover - depends on native worker image
            raise RuntimeError("BioTarget DrugClip loading requires huggingface_hub or DRUGCLIP_CHECKPOINT.") from error
        checkpoint = Path(
            hf_hub_download(
                repo_id=repo_id,
                filename=filename,
                revision=model_reference.get("checkpoint_revision") or None,
            )
        )

    if not torch.cuda.is_available():
        raise RuntimeError(
            "DrugClip requires an NVIDIA CUDA PyTorch runtime; no CUDA device is available. "
            "This blueprint is not supported on Apple or CPU-only workers."
        )
    device = torch.device("cuda")
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


def absolute_structure_result(structure: dict[str, Any], work_dir: Path) -> dict[str, Any]:
    """Keep a folded receptor addressable after leaving its adapter cwd."""
    raw_path = str(structure.get("path") or "").strip()
    if not raw_path:
        raise RuntimeError("BioTarget Stage B returned a structure without a path.")
    path = Path(raw_path).expanduser()
    if not path.is_absolute():
        path = work_dir / path
    path = path.resolve()
    if not path.is_file():
        raise RuntimeError(f"BioTarget Stage B structure does not exist: {path}")
    return {**structure, "path": str(path)}


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
    candidate_pool_size = int(service.get("candidate_pool_size") or candidate_count * 5)
    if candidate_count < 1:
        raise RuntimeError("DrugClip candidate_count must be at least one.")
    if candidate_pool_size < candidate_count:
        raise RuntimeError("DrugClip candidate_pool_size must be at least candidate_count.")
    scoring_batch_size = int(service.get("drugclip_scoring_batch_size") or 64)
    if scoring_batch_size < 1:
        raise RuntimeError("DrugClip drugclip_scoring_batch_size must be at least one.")
    pool = get_seed_smiles(candidate_pool_size)
    valid_smiles: list[str] = []
    graphs: list[Any] = []
    for smiles in pool:
        try:
            graphs.append(molecule_graph(str(smiles)))
            valid_smiles.append(str(smiles))
        except (RuntimeError, ValueError):
            continue
    if not graphs:
        raise RuntimeError("BioTarget candidate pool produced no valid DrugClip molecular graphs.")
    prompt = design_prompt(request)
    scores: list[float] = []
    for offset in range(0, len(graphs), scoring_batch_size):
        batch_scores = score_graphs(model, device, graphs[offset : offset + scoring_batch_size], prompt)
        scores.extend(float(value) for value in batch_scores.detach().cpu().tolist())
    selected = sorted(
        ((scores[index], smiles) for index, smiles in enumerate(valid_smiles)),
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
    work_dir = work_dir.expanduser().resolve()
    with working_directory(work_dir):
        structures = stage_b_structure_generation([normalized_target], engine="openfold3")
    if not structures:
        raise RuntimeError("BioTarget Stage B returned no structure.")
    structure = absolute_structure_result(structures[0], work_dir)
    return {"target": normalized_target, **structure, "provenance": "BioTarget Stage B"}


def graph_text_score(request: dict[str, Any], _work_dir: Path) -> dict[str, Any]:
    """Score one candidate or a batch against the same therapeutic prompt.

    Batch requests are the live service contract.  Loading a fresh DrugClip
    checkpoint for every candidate would multiply the real model's startup
    cost without changing the graph/text score.
    """
    prepare_problem_specific_model(request)
    biotarget_source(request)

    batch = request.get("candidates") if isinstance(request.get("candidates"), list) else None
    candidates = batch if batch is not None else [request.get("candidate")]
    normalized_candidates = [candidate for candidate in candidates if isinstance(candidate, dict)]
    if not normalized_candidates:
        raise RuntimeError("DrugClip scoring request requires one or more candidate objects.")
    structure = request.get("structure") if isinstance(request.get("structure"), dict) else {}
    model, device = load_drugclip(request)
    service = request.get("service") if isinstance(request.get("service"), dict) else {}
    batch_size = int(service.get("drugclip_scoring_batch_size") or 64)
    if batch_size < 1:
        raise RuntimeError("DrugClip drugclip_scoring_batch_size must be at least one.")
    graphs: list[Any] = []
    valid_candidates: list[dict[str, Any]] = []
    for candidate in normalized_candidates:
        smiles = str(candidate.get("smiles") or "")
        if not smiles:
            raise RuntimeError("DrugClip scoring request requires each candidate to include smiles.")
        try:
            graph = molecule_graph(smiles)
        except (RuntimeError, ValueError) as error:
            candidate_id = str(candidate.get("candidate_id") or smiles)
            raise RuntimeError(f"DrugClip could not construct a graph for candidate {candidate_id!r}.") from error
        graphs.append(graph)
        valid_candidates.append(candidate)
    scores: list[float] = []
    prompt = design_prompt(request)
    for offset in range(0, len(graphs), batch_size):
        values = score_graphs(model, device, graphs[offset : offset + batch_size], prompt)
        scores.extend(float(value) for value in values.detach().cpu().tolist())
    screens = [
        {
            "candidate": candidate,
            "structure": structure,
            "drugclip_score": scores[index],
            "provenance": "homerquan/DrugClip graph-text alignment via BioTarget",
            "model_ref": drugclip_config(request).get("model_ref", "hf.co/homerquan/DrugClip"),
        }
        for index, candidate in enumerate(valid_candidates)
    ]
    if batch is None:
        return screens[0]
    return {"screens": screens}


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
