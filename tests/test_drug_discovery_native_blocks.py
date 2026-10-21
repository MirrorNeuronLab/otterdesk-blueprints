"""Native scientific block contracts; all compute remains explicitly synthetic."""
import importlib
from pathlib import Path

import pytest
from mn_blueprint_blocks.context import BlockContext
from mn_blueprint_blocks.contracts import BlockError
from mn_sdk.blueprints import read_blueprint, resolve_config
from mn_sdk_common.committed_artifacts import CommittedJsonStore, CommittedArtifactIntegrityError

BLUEPRINT = Path(__file__).resolve().parents[1] / "drug_discovery_research_assistant"


@pytest.fixture
def discovery(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(BLUEPRINT / "payloads"))
    source = tmp_path / "inputs"
    source.mkdir()
    (source / "context.txt").write_text("Synthetic smoke test; source context is disabled.")
    config = resolve_config(read_blueprint(BLUEPRINT), {"mode": "mock", "source_context": {"enabled": False},
        "inputs": {"payload": {"input_folder": str(source)}}}).data
    monkeypatch.setenv("MN_JOB_OUTPUT_DIR", str(tmp_path / "outputs"))
    block = BlockContext(store=CommittedJsonStore(tmp_path / "run"), config=config,
        invocation_id="discovery-native", revision="v4-test", job_id="job-1", run_id="run-1")
    modules = {name: importlib.import_module("domain." + name) for name in
        ["native_stages", "continuous_service", "reporting"]}
    return block, modules


def prepared(block, modules):
    targets = modules["native_stages"].discover_targets(block, {})
    return modules["native_stages"].generate_structures(block, {"previous": targets})


def test_all_five_compiled_blocks_publish_and_replay_one_cycle(discovery, tmp_path, monkeypatch):
    from block_workflow_fixture import run_sample
    block, _ = discovery
    config = {"mode": "mock", "source_context": {"enabled": False}, "service": {"max_cycles": None},
        "inputs": block.config["inputs"]}
    first = run_sample("drug_discovery_research_assistant", config=config,
        runs_root=tmp_path / "runs", run_id="compiled-discovery")
    second = run_sample("drug_discovery_research_assistant", config=config,
        runs_root=tmp_path / "runs", run_id="compiled-discovery")
    final = first["final_artifact"]
    assert final == second["final_artifact"] and final["candidate_count"] == 5
    assert final["mode"] == "fake_smoke_test" and final["recommendation"] == "review_required"
    assert len({row["candidate"]["smiles"] for row in final["ranked_candidates"]}) == 5
    run = tmp_path / "runs/compiled-discovery"
    assert len(list(run.glob("cycles/*/cycle_report.json"))) == 1
    assert (run / "web/index.html").is_file() and (run / "web/publication.json").is_file()
    assert len(first["upstream_outputs"]) == 5


def test_interrupted_cycle_requires_reconciliation_without_repeating_compute(discovery, monkeypatch):
    block, modules = discovery
    structures = prepared(block, modules)
    calls = []
    def interrupted(*args, **kwargs):
        calls.append(True)
        raise TimeoutError("scientific process interrupted")
    monkeypatch.setattr(modules["continuous_service"], "run_service", interrupted)
    with pytest.raises(TimeoutError):
        modules["continuous_service"].run_discovery_service(block, {"previous": structures})
    with pytest.raises(BlockError) as raised:
        modules["continuous_service"].run_discovery_service(block, {"previous": structures})
    assert raised.value.code == "outcome_unknown" and calls == [True]
    assert not block.store.path("final_artifact.json").exists()


def test_completed_cycle_reconciles_saved_evidence_without_compute(discovery, monkeypatch):
    block, modules = discovery
    structures = prepared(block, modules)
    first = modules["continuous_service"].run_discovery_service(block, {"previous": structures})
    monkeypatch.setattr(modules["continuous_service"], "run_service", lambda *a, **k: pytest.fail("Completed cycle repeated"))
    assert modules["continuous_service"].run_discovery_service(block, {"previous": structures}) == first


def test_tampered_predecessor_is_rejected_before_folding(discovery, monkeypatch):
    block, modules = discovery
    targets = modules["native_stages"].discover_targets(block, {})
    block.store.path(targets["state"]["path"]).write_text("{}")
    monkeypatch.setattr(modules["native_stages"], "fake_fold", lambda *a: pytest.fail("Corrupt evidence reached folding"))
    with pytest.raises(CommittedArtifactIntegrityError):
        modules["native_stages"].generate_structures(block, {"previous": targets})


def test_tampered_protein_structure_is_rejected_before_candidate_compute(discovery, monkeypatch):
    block, modules = discovery
    structures = prepared(block, modules)
    state = block.store.read(structures["state"])
    block.store.path(state["structure_artifacts"][0]["path"]).write_text("changed structure")
    monkeypatch.setattr(modules["continuous_service"], "run_service", lambda *a, **k: pytest.fail("Changed structure reached compute"))
    with pytest.raises(CommittedArtifactIntegrityError):
        modules["continuous_service"].run_discovery_service(block, {"previous": structures})


def test_live_folding_failure_never_substitutes_synthetic_structure(discovery, monkeypatch):
    block, modules = discovery
    targets = modules["native_stages"].discover_targets(block, {})
    block.config["mode"] = "live"
    block.config["llm"]["mode"] = "live"
    def unavailable(*args, **kwargs):
        assert kwargs["output_dir"] == block.store.path("structures")
        assert kwargs["check"] == block.check
        raise RuntimeError("folding unavailable")
    monkeypatch.setattr(modules["native_stages"], "stage_b_structure_generation", unavailable)
    monkeypatch.setattr(modules["native_stages"], "fake_fold", lambda *a: pytest.fail("Live folding substituted synthetic data"))
    with pytest.raises(RuntimeError, match="folding unavailable"):
        modules["native_stages"].generate_structures(block, {"previous": targets})
    assert not block.store.path("discovery/structures.json").exists()


def test_cancelled_cycle_cannot_publish_a_scientific_success(discovery, monkeypatch):
    block, modules = discovery
    structures = prepared(block, modules)
    block.cancelled = lambda: True
    monkeypatch.setattr(modules["continuous_service"], "run_service", lambda *a, **k: pytest.fail("Cancelled cycle started compute"))
    with pytest.raises(BlockError) as raised:
        modules["continuous_service"].run_discovery_service(block, {"previous": structures})
    assert raised.value.code == "cancelled" and not block.store.path("discovery/cycle.json").exists()


def test_changed_cycle_evidence_cannot_reach_ranking(discovery):
    block, modules = discovery
    structures = prepared(block, modules)
    cycle = modules["continuous_service"].run_discovery_service(block, {"previous": structures})
    state = block.store.read(cycle["state"])
    block.store.path(state["cycle_artifacts"][0]["path"]).write_text("[]")
    with pytest.raises(CommittedArtifactIntegrityError):
        modules["native_stages"].evaluate_binding(block, {"previous": cycle})


def test_cycle_reconciliation_requires_matching_completed_report(discovery, monkeypatch):
    block, modules = discovery
    structures = prepared(block, modules)
    modules["continuous_service"].run_discovery_service(block, {"previous": structures})
    block.store.path("cycles/cycle-000000/cycle_report.json").write_text("{}")
    monkeypatch.setattr(modules["continuous_service"], "run_service", lambda *a, **k: pytest.fail("Uncertain cycle repeated"))
    with pytest.raises(BlockError) as raised:
        modules["continuous_service"].run_discovery_service(block, {"previous": structures})
    assert raised.value.code == "outcome_unknown"
