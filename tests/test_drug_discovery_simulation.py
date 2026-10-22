"""The live simulation batch shares model weights while candidates run concurrently."""
import importlib.util
import json
import threading
import subprocess
import sys
import types
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

PAYLOADS = Path(__file__).resolve().parents[1] / "drug_discovery_research_assistant/payloads"


def test_blueprint_does_not_serialize_model_calls_inside_its_run():
    config = json.loads((PAYLOADS.parent / "config/default.json").read_text())
    assert "llm" not in config["backpressure"]


@pytest.fixture
def adapter(monkeypatch):
    spec = importlib.util.spec_from_file_location("discovery_simulation_adapter", PAYLOADS / "service/scripts/biotarget_adapter.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "prepare_problem_specific_model", lambda request: None)
    monkeypatch.setattr(module, "biotarget_source", lambda request: None)
    return module


def screen(number):
    return {"candidate": {"candidate_id": f"candidate-{number}", "smiles": "CCO"},
            "structure": {"path": "/run/structure.pdb"}}


def test_simulations_share_one_loaded_model_and_run_in_parallel(adapter, monkeypatch, tmp_path):
    model = object()
    loads = []
    barrier = threading.Barrier(4)
    active = set()
    lock = threading.Lock()

    def load(request):
        loads.append(request)
        return model, "cuda"

    def evaluate(value, shared, device):
        assert shared is model and device == "cuda"
        with lock:
            active.add(threading.get_ident())
        barrier.wait(timeout=5)
        return {**value, "gnina_affinity": 3.5, "simulation_stability": 3.5}

    monkeypatch.setattr(adapter, "load_drugclip", load)
    monkeypatch.setattr(adapter, "evaluate_screen", evaluate)
    request = {"screens": [screen(i) for i in range(4)], "service": {"parallelism": {"simulation_workers": 4}}}
    original_directory = Path.cwd()
    result = adapter.simulation(request, tmp_path)
    assert len(loads) == 1 and len(active) == 4
    assert [row["candidate"] for row in result["simulations"]] == [row["candidate"] for row in request["screens"]]
    assert Path.cwd() == original_directory


def test_native_simulation_failure_remains_failed(adapter, monkeypatch, tmp_path):
    monkeypatch.setattr(adapter, "load_drugclip", lambda request: (object(), "cuda"))
    def fail(*args):
        raise RuntimeError("GNINA model initialization failed")
    monkeypatch.setattr(adapter, "evaluate_screen", fail)
    with pytest.raises(RuntimeError, match="GNINA model initialization failed"):
        adapter.simulation({"screens": [screen(0), screen(1)]}, tmp_path)


@pytest.mark.parametrize("screens", [[], [None], [{"candidate": {"smiles": "CCO"}, "structure": {"path": "relative.pdb"}}]])
def test_invalid_batch_is_rejected_before_loading_a_model(adapter, monkeypatch, tmp_path, screens):
    monkeypatch.setattr(adapter, "load_drugclip", lambda request: pytest.fail("Invalid input loaded a model"))
    with pytest.raises(RuntimeError, match="simulation requires"):
        adapter.simulation({"screens": screens}, tmp_path)


def test_parallel_gnina_calls_never_rewrite_the_shared_receptor(monkeypatch, tmp_path):
    class Writer:
        def __init__(self, path):
            self.path = Path(path)
        def write(self, mol):
            self.path.write_text("ligand")
        def close(self):
            pass
    chem = types.SimpleNamespace(MolFromSmiles=lambda value: value, AddHs=lambda mol: mol, SDWriter=Writer)
    monkeypatch.setitem(sys.modules, "torch", types.ModuleType("torch"))
    monkeypatch.setitem(sys.modules, "torch_geometric.data", types.SimpleNamespace(Batch=object))
    monkeypatch.setitem(sys.modules, "tqdm", types.SimpleNamespace(tqdm=lambda values, **kwargs: values))
    monkeypatch.setitem(sys.modules, "rdkit", types.SimpleNamespace(Chem=chem))
    monkeypatch.setitem(sys.modules, "rdkit.Chem", types.SimpleNamespace(AllChem=types.SimpleNamespace(EmbedMolecule=lambda *a, **k: 0, MMFFOptimizeMolecule=lambda *a, **k: 0)))
    monkeypatch.setitem(sys.modules, "biotarget.core.utils", types.SimpleNamespace(normalize_01=lambda value: value))
    spec = importlib.util.spec_from_file_location("discovery_gnina_isolation", PAYLOADS / "biotarget/stages/stage_d_evaluation.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module.shutil, "which", lambda name: "/usr/local/bin/gnina")
    receptor = tmp_path / "target.pdb"
    original = "MODEL        1\nATOM      1  N\nENDMDL\nEND\n"
    receptor.write_text(original)
    barrier = threading.Barrier(2)
    paths = []
    def run(command, **kwargs):
        cleaned = Path(command[command.index("-r") + 1])
        ligand = Path(command[command.index("-l") + 1])
        paths.extend([cleaned, ligand])
        barrier.wait(timeout=5)
        assert cleaned.parent == ligand.parent == Path(kwargs["cwd"])
        assert cleaned.parent != receptor.parent
        assert cleaned.read_text() == "ATOM      1  N\nEND\n"
        assert receptor.read_text() == original
        return subprocess.CompletedProcess(command, 0, stdout="CNNaffinity: 3.5\n", stderr="")
    monkeypatch.setattr(module.subprocess, "run", run)
    with ThreadPoolExecutor(max_workers=2) as executor:
        assert list(executor.map(lambda _: module.run_gnina(str(receptor), "CCO"), range(2))) == [(3.5, True)] * 2
    assert len({path.parent for path in paths}) == 2
    assert all(not path.exists() for path in paths)
    assert receptor.read_text() == original


@pytest.mark.parametrize("incomplete", [False, True])
def test_live_cycle_submits_one_complete_simulation_batch(monkeypatch, tmp_path, incomplete):
    monkeypatch.syspath_prepend(str(PAYLOADS))
    spec = importlib.util.spec_from_file_location("discovery_batch_cycle", PAYLOADS / "service/scripts/continuous_service.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    candidates = [{"candidate_id": f"molecule-{i}", "smiles": smiles} for i, smiles in enumerate(["CCO", "CCN", "CCC", "CCCl", "CCBr"])]
    # The cycle orchestration test does not load the native chemistry stack.
    monkeypatch.setattr(module, "five_distinct_candidates", lambda rows, **kwargs: rows)
    monkeypatch.setenv("MN_JOB_OUTPUT_DIR", str(tmp_path / "output"))
    batches = []
    def dispatch(name, config, request, *args):
        if name == "candidate_generator":
            return {"candidates": candidates}
        if name == "folding":
            return {"target": request["target"], "path": str(tmp_path / "receptor.pdb")}
        if name == "drugclip":
            return {"screens": [{"candidate": row, "structure": request["structure"], "drugclip_score": 0.5} for row in request["candidates"]]}
        assert name == "simulation" and "screen" not in request
        batches.append(request["screens"])
        return {"simulations": [] if incomplete else [{**row, "simulation_stability": 3.5} for row in request["screens"]]}
    monkeypatch.setattr(module, "run_native_adapter", dispatch)
    config = {"mode": "live", "inputs": {"payload": {"targets": [{"protein_id": "P56817", "gene": "BACE1"}], "output_folder": str(tmp_path / "output")}},
              "web_ui": {"molecule_preview": {"enabled": False}}}
    if incomplete:
        with pytest.raises(RuntimeError, match="incomplete candidate evaluations"):
            module.run_cycle(config, tmp_path / "run", 0)
        assert not (tmp_path / "run/cycles/cycle-000000/cycle_report.json").exists()
    else:
        result = module.run_cycle(config, tmp_path / "run", 0)
        assert result["simulation_count"] == result["candidate_count"] == 5
    assert len(batches) == 1 and len(batches[0]) == 5
