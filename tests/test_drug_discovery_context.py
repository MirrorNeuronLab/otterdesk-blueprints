"""Discovery source publication through the shared Job/Membrane query contract."""

import importlib
import json
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
    ctx = {"run_id": "run-1", "run_dir": run, "output_folder": output, "config": config}
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
    ctx["config"]["api_key"] = "SECRET-CREDENTIAL"
    ctx["config"]["inputs"]["payload"]["targets"] = []
    folder = Path(ctx["config"]["inputs"]["payload"]["input_folder"])
    (folder / "notes.md").write_text("Background.\n" * 300 + "TAIL-ASSAY-CONSTRAINT: review selectivity.\n")
    (folder / ".credentials.txt").write_text("HIDDEN-SECRET")
    monkeypatch.setattr(stages, "run_stage_script", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("target adapter failed")))
    with pytest.raises(RuntimeError, match="target adapter failed"):
        stages.discover_targets(ctx)
    documents = list((ctx["output_folder"] / "context_sources" / "inputs").rglob("*.md"))
    body = "\n".join(path.read_text() for path in documents)
    assert "TAIL-ASSAY-CONSTRAINT" in body
    assert "BACE1" in body and "seed-2" in body and "CCN" in body
    assert "Procedure configured" in body and "candidate_generation" in body
    assert "SECRET-CREDENTIAL" not in body and "HIDDEN-SECRET" not in body
    assert "not evidence that a stage completed" in body
    sources.publish_inputs(ctx, stages._resolved_inputs(ctx))
    assert len(documents) == len(list((ctx["output_folder"] / "context_sources" / "inputs").rglob("*.md")))


def test_saved_results_are_retrievable_and_refresh_after_each_stage(discovery, text_memory_transport):
    sources, stages, ctx = discovery
    sources.publish_inputs(ctx, stages._resolved_inputs(ctx))
    state = {"targets": [{"gene": "BACE1", "protein_id": "P56817"}],
             "structures": [{"gene": "BACE1", "path": "/private/receptor.pdb"}],
             "api_key": "SECRET-CREDENTIAL"}
    stages.write_discovery_state(ctx, state)
    service = FolderContext(job_id="test-memory-job",
        manifest={"metadata": {"mn_storage": {"submission_id": "discovery-job"}}},
        shared_root=ctx["output_folder"].parents[3])
    try:
        text, citations, warnings = service.retrieve("BACE1 discovery results")
        assert not warnings and citations and "BACE1" in text and "run-1" in text
        assert "/private/receptor.pdb" not in text and "SECRET-CREDENTIAL" not in text
        state["final_report"] = {"ranked_candidates": [
            {"candidate": {"candidate_id": "candidate-1", "smiles": "CCO"},
             "drugclip_score": 0.91, "gnina_affinity": -8.7}],
            "missing_evidence": ["experimental binding and selectivity data"]}
        stages.write_discovery_state(ctx, state)
        text, citations, warnings = service.retrieve("ranked_candidates gnina_affinity")
        assert not warnings and citations and "candidate-1" in text and "-8.7" in text
        assert "experimental binding" in text
        text, citations, warnings = service.retrieve("candidate_pool_size procedure")
        assert not warnings and citations and "800" in text
    finally:
        service.close()


def test_disabled_source_profile_does_not_read_inputs_or_publish(discovery):
    sources, stages, ctx = discovery
    ctx["config"]["source_context"]["enabled"] = False
    ctx["config"]["inputs"]["payload"]["input_folder"] = "/unavailable"
    sources.publish_inputs(ctx, stages._resolved_inputs(ctx))
    sources.publish_results(ctx, {"final_report": {}})
    assert not ctx["output_folder"].exists()


def test_provided_target_is_preserved_without_a_disease_search(discovery, monkeypatch):
    _, stages, ctx = discovery
    monkeypatch.setattr(stages, "run_stage_script", lambda *args, **kwargs: pytest.fail("Provided targets must not invoke disease search"))
    assert stages.discover_targets(ctx) == {"target_count": 1}
    state = stages.read_discovery_state(ctx)
    assert state["targets"] == [{"gene": "BACE1", "protein_id": "P56817"}]
    assert state["target_source"] == "provided_protein_targets"


def test_missing_optional_step_inputs_keep_saved_defaults_and_input_documents(discovery, monkeypatch):
    _, stages, ctx = discovery
    ctx["payload"] = {key: None for key in ("disease", "targets", "input_folder", "disease_or_target_profile")}
    monkeypatch.setattr(stages, "run_stage_script", lambda *args, **kwargs: pytest.fail("Saved BACE1 target must survive missing run input mappings"))
    stages.discover_targets(ctx)
    assert stages.read_discovery_state(ctx)["targets"] == [{"gene": "BACE1", "protein_id": "P56817"}]
    assert len(list((ctx["output_folder"] / "context_sources" / "inputs").rglob("*.md"))) == 4
    ctx["payload"]["targets"] = []
    assert stages._resolved_inputs(ctx)["targets"] == []


def test_disease_search_uses_the_explicit_name_and_preserves_therapeutic_text(discovery, monkeypatch):
    _, stages, ctx = discovery
    inputs = ctx["config"]["inputs"]["payload"]
    inputs.update(targets=[], disease="Alzheimer disease")
    seen = []
    def lookup(_ctx, _state, script, payload):
        seen.append((script, payload))
        return {"targets": [{"protein_id": "P05067", "gene": "APP"}]}
    monkeypatch.setattr(stages, "run_stage_script", lookup)
    stages.discover_targets(ctx)
    assert seen == [("stage_a.py", {"disease": "Alzheimer disease"})]
    assert "BACE1 modulation" in stages._stage_config(ctx, stages.read_discovery_state(ctx))["inputs"]["payload"]["disease_or_target_profile"]


@pytest.mark.parametrize("targets", [[{"gene": "BACE1"}], [{"protein_id": "../../private"}], "BACE1",
    [{"protein_id": "P56817"}], [{"protein_id": "P56817", "gene": "../../private"}],
    [{"protein_id": "P56817", "gene": ["BACE1"]}], [{"protein_id": "P568170", "gene": "BACE1"}]])
def test_invalid_explicit_targets_do_not_fall_back_to_other_targets(discovery, monkeypatch, targets):
    _, stages, ctx = discovery
    ctx["config"]["inputs"]["payload"]["targets"] = targets
    monkeypatch.setattr(stages, "run_stage_script", lambda *args, **kwargs: pytest.fail("Invalid explicit targets cannot become a disease search"))
    with pytest.raises(ValueError, match="targets|target"):
        stages.discover_targets(ctx)


def test_input_links_cannot_escape_the_approved_folder(discovery, tmp_path):
    sources, stages, ctx = discovery
    outside = tmp_path / "outside.txt"
    outside.write_text("Private file outside the approved input folder")
    folder = Path(ctx["config"]["inputs"]["payload"]["input_folder"])
    (folder / "escape.txt").symlink_to(outside)
    with pytest.raises(ValueError, match="escapes"):
        sources.publish_inputs(ctx, stages._resolved_inputs(ctx))
    assert not ctx["output_folder"].exists()


def test_oversized_sources_fail_without_a_truncated_replacement(discovery, monkeypatch):
    sources, stages, ctx = discovery
    monkeypatch.setattr(sources, "MAX_SOURCE_BYTES", 32)
    folder = Path(ctx["config"]["inputs"]["payload"]["input_folder"])
    (folder / "notes.md").write_text("complete evidence " * 100)
    with pytest.raises(RuntimeError, match="byte limit"):
        sources.publish_inputs(ctx, stages._resolved_inputs(ctx))
    assert not ctx["output_folder"].exists()


def test_synthetic_results_remain_labelled_and_runs_have_distinct_sources(discovery):
    sources, _, ctx = discovery
    ctx["config"]["mode"] = "mock"
    sources.publish_results(ctx, {"evaluations": [{"drugclip_score": 0.5}]})
    ctx["run_id"] = "run-2"
    sources.publish_results(ctx, {"targets": [{"gene": "APP"}]})
    documents = list((ctx["output_folder"] / "context_sources" / "outputs").rglob("*.md"))
    assert len(documents) == 2
    assert all("Synthetic smoke-test data" in p.read_text() for p in documents)
    assert {"run-1", "run-2"} == {run for run in ("run-1", "run-2") if any(run in p.read_text() for p in documents)}
