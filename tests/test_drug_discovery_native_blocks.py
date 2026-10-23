"""Native scientific block contracts; all compute remains explicitly synthetic."""
import importlib
import hashlib
import json
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


def test_reporting_exports_science_and_review_media_from_an_isolated_worker(discovery, tmp_path, monkeypatch):
    from mn_sdk.integrations.block_worker import run
    from mn_sdk.step_runtime import StepContext

    block, modules = discovery
    structures = prepared(block, modules)
    cycle = modules["continuous_service"].run_discovery_service(block, {"previous": structures})
    evaluations = modules["native_stages"].evaluate_binding(block, {"previous": cycle})
    # Live adapter requests/results are also part of the scientific run archive.
    request = block.store.path("cycles/cycle-000000/simulation/simulation.request.json")
    request.parent.mkdir(parents=True, exist_ok=True)
    request.write_text('{"screens": []}')
    dashboard = importlib.import_module("domain.dashboard")
    png = b"test molecule preview"
    monkeypatch.setattr(dashboard, "_draw_candidate_png", lambda _smiles: png)
    monkeypatch.setattr(dashboard, "_draw_candidate_svg", lambda _smiles: "<svg/>")
    handoff = tmp_path / "handoff"
    context = StepContext(step_id="ranking_reporting", run_id=block.run_id, job_id=block.job_id,
        idempotency_key="review-publication", environment={
            "MN_RUN_DIR": str(block.store.run_dir), "MN_JOB_OUTPUT_DIR": str(block.output_directory),
            "MN_SDK_COMPONENTS_JSON": '["blueprint-blocks"]',
            "MN_ARTIFACT_OUTPUT_DIR": str(handoff), "MN_ARTIFACT_COMMIT_ID": "review-attempt",
            "MN_ARTIFACT_PRODUCER": json.dumps({"run_id": block.run_id}),
        }, config=block.config, message={"body": {"step_input": {"previous": evaluations}}})
    options = {"revision": "test-review@1", "instance": {"uses": "mn.blocks.domain_operation@1",
        "hooks": {"operation": "domain.reporting:publish_ranking"}}}
    options["hooks"] = {"operation": lambda current, _inputs: modules["reporting"].publish_ranking(
        current, {"previous": evaluations})}
    result = run(context, **options)
    assert run(context, **options) == result
    required = {"final_artifact.json", "result.json", "discovery_service_review.json",
        "cycles/cycle-000000/cycle_report.json", "cycles/cycle-000000/simulation_results.json",
        "cycles/cycle-000000/simulation/simulation.request.json", "service_state.json", "cycle_progress.json"}
    optional = {"web/index.html", "web_ui.json", "web/conversation_media.json",
        *[f"web/candidate-{i}.png" for i in range(1, 6)]}
    assert required | optional <= set(result.exports)
    assert not required.intersection(result.optional_exports)
    assert optional <= set(result.optional_exports)
    assert not any(path.startswith(("blocks/", ".")) for path in result.exports)
    manifest = json.loads((handoff / result.exports["web/conversation_media.json"]["path"]).read_bytes())
    assert manifest["run_id"] == block.run_id
    for item in manifest["items"]:
        exported = result.exports["web/" + item["filename"]]
        assert (handoff / exported["path"]).read_bytes() == png
        assert item["sha256"] == hashlib.sha256(png).hexdigest()

    # Only advertised files cross the worker boundary. Host delivery must be
    # able to finish and publish the output-folder link from that inventory.
    from mn_sdk.blueprint_support.shared_outputs import materialize_shared_storage_outputs_until_stable
    shared = tmp_path / "replicated"
    submission = shared / "submissions/job-1"
    host_run = submission / "outputs/runs" / block.run_id
    for name, ref in result.exports.items():
        target = host_run / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((handoff / ref["path"]).read_bytes())
    runtime_run = "/runtime/shared/submissions/job-1/outputs/runs/" + block.run_id
    (host_run / ".mn_completion.json").write_text(json.dumps({"status": "completed",
        "output_files": [{"path": runtime_run + "/" + name} for name in result.exports]}))
    storage = {"run_id": block.run_id, "host_root": str(shared), "runtime_root": "/runtime/shared",
        "host_submission_path": str(submission), "output_copy": [{"source_path": runtime_run,
            "target_path": str(tmp_path / "delivered"), "layout": "batch",
            "completion_manifest": ".mn_completion.json",
            "result": {"kind": "output_folder", "label": "Output folder"}}]}
    delivery = materialize_shared_storage_outputs_until_stable(storage,
        poll_seconds=.01, timeout_seconds=1, stable_observations=1)
    assert delivery["copied"] and not delivery["errors"]
    folder = Path(delivery["target_paths"][0])
    assert (folder / "web/candidate-1.png").read_bytes() == png
    events = [json.loads(line) for line in (submission / "delivery" / block.run_id / "events.jsonl").read_text().splitlines()]
    assert any(event["type"] == "run_result_available" and
        event["payload"]["locator"]["path"] == str(folder) for event in events)


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
