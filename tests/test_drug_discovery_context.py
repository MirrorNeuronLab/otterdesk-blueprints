"""Discovery source publication through the shared Job/Membrane query contract."""

import importlib
import json
from mn_blueprint_blocks.context import BlockContext
from mn_sdk_common.committed_artifacts import CommittedJsonStore
from mn_sdk.blueprints import blueprint_definition
from pathlib import Path

import pytest
from mn_sdk.blueprint_runtime import load_blueprint_config
from mn_sdk.blueprints import compile_blueprint, read_blueprint
from mn_sdk.context_engine import blueprint_requires_context_engine
from mn_sdk.integrations.folder_context import FolderContext

BLUEPRINT = Path(__file__).resolve().parents[1] / "drug_discovery_research_assistant"


@pytest.fixture
def discovery(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(BLUEPRINT / "payloads"))
    sources = importlib.import_module("domain.conversation_sources")
    stages = importlib.import_module("domain.native_stages")
    config = load_blueprint_config(BLUEPRINT)
    folder = tmp_path / "approved_inputs"
    folder.mkdir()
    (folder / "target_profile.json").write_text(json.dumps({"target": "BACE1", "purpose": "research"}))
    (folder / "seeds.csv").write_text("id,smiles\nseed-1,CCO\nseed-2,CCN\n")
    config["inputs"]["payload"]["input_folder"] = str(folder)
    output = tmp_path / "submissions" / "discovery-job" / "outputs" / "user"
    run = tmp_path / "run"
    run.mkdir()
    monkeypatch.setenv("MN_JOB_OUTPUT_DIR", str(output))
    ctx = BlockContext(store=CommittedJsonStore(run), invocation_id="targets", revision="test-v4",
        run_id="run-1", job_id="job-1", config=config, resources={"output_folder": output, "inputs": {}})
    return sources, stages, ctx


def test_source_profile_prepares_membrane_without_unused_runtime_recall():
    package = read_blueprint(BLUEPRINT)
    compiled = compile_blueprint(package).manifest
    config = load_blueprint_config(BLUEPRINT)
    assert config["source_context"]["enabled"] is True
    assert config["text_memory"]["enabled"] is False
    assert blueprint_requires_context_engine(compiled, config, env={})
    dependencies = package.document("dependencies")
    assert "mirrorneuron-docs-to-markdown-skill" in {d["name"] for d in dependencies["skills"]}
    assert next(d for d in dependencies["packages"] if d["name"] == "mirrorneuron-python-sdk")["extras"] == ["context"]


def test_input_context_survives_failed_first_stage_and_retains_complete_documents(discovery, monkeypatch):
    sources, stages, ctx = discovery
    ctx.config["api_key"] = "SECRET-CREDENTIAL"
    ctx.resources['inputs']["targets"] = []
    folder = Path(ctx.config["inputs"]["payload"]["input_folder"])
    (folder / "notes.md").write_text("Background.\n" * 300 + "TAIL-ASSAY-CONSTRAINT: review selectivity.\n")
    (folder / ".credentials.txt").write_text("HIDDEN-SECRET")
    monkeypatch.setattr(stages, "stage_a_target_discovery", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("target adapter failed")))
    with pytest.raises(RuntimeError, match="target adapter failed"):
        stages.discover_targets(ctx, ctx.resources['inputs'])
    documents = list((ctx.resources['output_folder'] / "context_sources" / "inputs").rglob("*.md"))
    body = "\n".join(path.read_text() for path in documents)
    assert "TAIL-ASSAY-CONSTRAINT" in body
    assert "BACE1" in body and "seed-2" in body and "CCN" in body
    assert "Procedure configured" in body and "candidate_generation" in body
    assert "SECRET-CREDENTIAL" not in body and "HIDDEN-SECRET" not in body
    assert "not evidence that a stage completed" in body
    sources.publish_inputs(ctx, stages.research_inputs(ctx, ctx.resources['inputs']))
    assert len(documents) == len(list((ctx.resources['output_folder'] / "context_sources" / "inputs").rglob("*.md")))


def test_saved_results_are_retrievable_and_refresh_after_each_stage(discovery, text_memory_transport):
    sources, stages, ctx = discovery
    sources.publish_inputs(ctx, stages.research_inputs(ctx, ctx.resources['inputs']))
    state = {"targets": [{"gene": "BACE1", "protein_id": "P56817"}],
             "structures": [{"gene": "BACE1", "path": "/private/receptor.pdb"}],
             "api_key": "SECRET-CREDENTIAL"}
    stages.write_discovery_state(ctx, state, "targets")
    service = FolderContext(job_id="test-memory-job",
        manifest={"metadata": {"mn_storage": {"submission_id": "discovery-job"}}},
        shared_root=ctx.resources['output_folder'].parents[3])
    try:
        text, citations, warnings = service.retrieve("BACE1 discovery results")
        assert not warnings and citations and "BACE1" in text and "run-1" in text
        assert "/private/receptor.pdb" not in text and "SECRET-CREDENTIAL" not in text
        state["final_report"] = {"ranked_candidates": [
            {"candidate": {"candidate_id": "candidate-1", "smiles": "CCO"},
             "drugclip_score": 0.91, "gnina_affinity": -8.7}],
            "missing_evidence": ["experimental binding and selectivity data"]}
        stages.write_discovery_state(ctx, state, "ranking")
        text, citations, warnings = service.retrieve("ranked_candidates gnina_affinity")
        assert not warnings and citations and "candidate-1" in text and "-8.7" in text
        assert "experimental binding" in text
        text, citations, warnings = service.retrieve("candidate_pool_size procedure")
        assert not warnings and citations and "800" in text
    finally:
        service.close()


def test_disabled_source_profile_does_not_read_inputs_or_publish(discovery):
    sources, stages, ctx = discovery
    ctx.config["source_context"]["enabled"] = False
    ctx.config["inputs"]["payload"]["input_folder"] = "/unavailable"
    sources.publish_inputs(ctx, stages.research_inputs(ctx, ctx.resources['inputs']))
    sources.publish_results(ctx, {"final_report": {}})
    assert not ctx.resources['output_folder'].exists()


def test_provided_target_is_preserved_without_a_disease_search(discovery, monkeypatch):
    _, stages, ctx = discovery
    ctx.resources['inputs']["targets"] = [{"gene": "BACE1", "protein_id": "P56817", "score_opentargets": .999}]
    monkeypatch.setattr(stages, "stage_a_target_discovery", lambda *args, **kwargs: pytest.fail("Provided targets must not invoke disease search"))
    assert stages.discover_targets(ctx, ctx.resources['inputs'])["target_count"] == 1
    state = ctx.store.read_path("discovery/targets.json")
    assert state["targets"] == [{"gene": "BACE1", "protein_id": "P56817"}]
    assert state["target_source"] == "provided_protein_targets"


def test_missing_optional_step_inputs_keep_saved_defaults_and_input_documents(discovery, monkeypatch):
    _, stages, ctx = discovery
    ctx.resources['inputs'] = {key: None for key in ("disease", "targets", "input_folder", "disease_or_target_profile")}
    monkeypatch.setattr(stages, "stage_a_target_discovery", lambda *args, **kwargs: pytest.fail("Saved BACE1 target must survive missing run input mappings"))
    stages.discover_targets(ctx, ctx.resources['inputs'])
    assert ctx.store.read_path("discovery/targets.json")["targets"] == [{"gene": "BACE1", "protein_id": "P56817"}]
    assert len(list((ctx.resources['output_folder'] / "context_sources" / "inputs").rglob("*.md"))) == 4
    ctx.resources['inputs']["targets"] = []
    from mn_sdk.integrations.block_inputs import declared_inputs
    assert declared_inputs(ctx, ctx.resources['inputs'], runtime_file=stages.__file__)["targets"] == []


def test_default_bundle_input_is_resolved_and_saved_by_common_blocks(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(BLUEPRINT / "payloads"))
    monkeypatch.setenv("MN_JOB_OUTPUT_DIR", str(tmp_path / "outputs"))
    config = load_blueprint_config(BLUEPRINT)
    assert config["inputs"]["payload"]["input_folder"] == "@/examples/sample_inputs"
    block = BlockContext(store=CommittedJsonStore(tmp_path / "run"), config=config,
        invocation_id="sample-inputs", revision="test", run_id="sample-run", job_id="sample-job",
        environment={"MN_WORKDIR": str(tmp_path / "unrelated-worker"), "MN_JOB_OUTPUT_DIR": str(tmp_path / "outputs")})
    stages = importlib.import_module("domain.native_stages")
    assert stages.discover_targets(block, {"input_folder": None})["target_count"] == 1
    inputs = block.store.read_path("inputs.json")
    assert inputs["input_folder"] == str(BLUEPRINT / "examples/sample_inputs")
    assert block.original_config["inputs"]["payload"]["input_folder"] == "@/examples/sample_inputs"
    documents = list((tmp_path / "outputs/context_sources/inputs").rglob("*.md"))
    assert documents and any("BACE1" in path.read_text() for path in documents)


def test_compiled_sample_stages_inputs_without_absolute_path_override(tmp_path):
    from block_workflow_fixture import run_sample
    result = run_sample("drug_discovery_research_assistant", config={"mode": "mock"},
        runs_root=tmp_path / "runs", run_id="default-sample", through_step="target_discovery")
    assert result["target_count"] == 1
    run = tmp_path / "runs/default-sample"
    inputs = json.loads((run / "inputs.json").read_text())
    assert "mn_local_inputs" in inputs["input_folder"] and "@/" not in inputs["input_folder"]
    assert (Path(inputs["input_folder"]) / "target_profile.json").is_file()


def test_disease_search_uses_the_explicit_name_and_preserves_therapeutic_text(discovery, monkeypatch):
    _, stages, ctx = discovery
    inputs = ctx.resources['inputs']
    inputs.update(targets=[], disease="Alzheimer disease")
    seen = []
    def lookup(disease):
        seen.append(disease)
        return [{"protein_id": "P05067", "gene": "APP"}]
    monkeypatch.setattr(stages, "stage_a_target_discovery", lookup)
    stages.discover_targets(ctx, ctx.resources['inputs'])
    assert seen == ["Alzheimer disease"]
    assert "BACE1 modulation" in importlib.import_module("domain.configuration").cycle_configuration(ctx, ctx.store.read_path("discovery/targets.json"))["inputs"]["payload"]["disease_or_target_profile"]


@pytest.mark.parametrize("targets", [[{"gene": "BACE1"}], [{"protein_id": "../../private"}], "BACE1",
    [{"protein_id": "P56817"}], [{"protein_id": "P56817", "gene": "../../private"}],
    [{"protein_id": "P56817", "gene": ["BACE1"]}], [{"protein_id": "P568170", "gene": "BACE1"}]])
def test_invalid_explicit_targets_do_not_fall_back_to_other_targets(discovery, monkeypatch, targets):
    _, stages, ctx = discovery
    ctx.resources['inputs']["targets"] = targets
    monkeypatch.setattr(stages, "stage_a_target_discovery", lambda *args, **kwargs: pytest.fail("Invalid explicit targets cannot become a disease search"))
    with pytest.raises(ValueError, match="targets|target"):
        stages.discover_targets(ctx, ctx.resources['inputs'])


def test_input_links_cannot_escape_the_approved_folder(discovery, tmp_path):
    sources, stages, ctx = discovery
    outside = tmp_path / "outside.txt"
    outside.write_text("Private file outside the approved input folder")
    folder = Path(ctx.config["inputs"]["payload"]["input_folder"])
    (folder / "escape.txt").symlink_to(outside)
    with pytest.raises(ValueError, match="escapes"):
        sources.publish_inputs(ctx, stages.research_inputs(ctx, ctx.resources['inputs']))
    assert not ctx.resources['output_folder'].exists()


def test_oversized_sources_fail_without_a_truncated_replacement(discovery, monkeypatch):
    sources, stages, ctx = discovery
    monkeypatch.setattr(sources, "MAX_SOURCE_BYTES", 32)
    folder = Path(ctx.config["inputs"]["payload"]["input_folder"])
    (folder / "notes.md").write_text("complete evidence " * 100)
    with pytest.raises(RuntimeError, match="byte limit"):
        sources.publish_inputs(ctx, stages.research_inputs(ctx, ctx.resources['inputs']))
    assert not ctx.resources['output_folder'].exists()


def test_synthetic_results_remain_labelled_and_runs_have_distinct_sources(discovery):
    sources, _, ctx = discovery
    ctx.config["mode"] = "mock"
    sources.publish_results(ctx, {"evaluations": [{"drugclip_score": 0.5}]})
    ctx.run_id = "run-2"
    sources.publish_results(ctx, {"targets": [{"gene": "APP"}]})
    documents = list((ctx.resources['output_folder'] / "context_sources" / "outputs").rglob("*.md"))
    assert len(documents) == 2
    assert all("Synthetic smoke-test data" in p.read_text() for p in documents)
    assert {"run-1", "run-2"} == {run for run in ("run-1", "run-2") if any(run in p.read_text() for p in documents)}
