"""Offline guards for the product benchmark runner; no SSH or model calls."""

from pathlib import Path
import pytest
from workspace_paths import companion_workspace
from membrane_benchmark_runner import run_spark, snapshot, SPARK_PREREQUISITES

WORKSPACE = companion_workspace(Path(__file__).resolve().parents[1])
BLUEPRINTS = Path(__file__).resolve().parents[1]


def test_spark_never_uses_ssh_without_both_explicit_gates(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "subprocess.run", lambda *a, **k: pytest.fail("SSH or mutation before gates")
    )
    for env in ({}, {"MN_ENABLE_TWO_BOX": "1"}, {"MN_ENABLE_GPU_TESTS": "1"}):
        with pytest.raises(RuntimeError, match="gates"):
            run_spark(tmp_path, tmp_path, tmp_path / "out", env)


def test_evaluated_snapshot_has_hashes_and_no_host_configuration(tmp_path):
    workspace = WORKSPACE
    manifest = snapshot(workspace, BLUEPRINTS, tmp_path / "source.tar.gz")
    assert manifest["source_revisions"]["Membrane"]
    assert "Membrane/mn-context-engine/Cargo.lock" in manifest["evaluated_file_sha256"]
    assert (
        "Membrane/mn-context-engine-python-sdk/src/mn_context_engine_sdk/text_memory.py"
        in manifest["evaluated_file_sha256"]
    )
    assert (
        "Membrane/mn-context-engine/examples/duckdb_analytical_scaling.rs"
        in manifest["evaluated_file_sha256"]
    )
    assert all(
        ".git/" not in n and ".venv/" not in n and ".mn/" not in n
        for n in manifest["evaluated_file_sha256"]
    )


def test_spark_snapshot_stages_fixed_data_sdk_and_cpu_examples(tmp_path):
    import tarfile

    workspace = WORKSPACE
    manifest = snapshot(workspace, BLUEPRINTS, tmp_path / "source.tar.gz")
    names = manifest["evaluated_file_sha256"]
    assert any("markdown_memory_sample/corpus/" in n for n in names)
    assert any(
        "markdown_memory_sample/cases/" in n for n in names
    )  # Evaluator-only, outside runtime volume.
    with tarfile.open(tmp_path / "source.tar.gz") as archive:
        assert (
            "Membrane/mn-context-engine-python-sdk/src/mn_context_engine_sdk/evidence/client.py"
            in archive.getnames()
        )


def test_spark_preflight_and_cleanup_have_no_redis_or_compressor():

    assert "redis" not in SPARK_PREREQUISITES.lower()
    assert "mn-context-engine-model" not in SPARK_PREREQUISITES
    assert "c++" in SPARK_PREREQUISITES and "cmake" not in SPARK_PREREQUISITES


@pytest.mark.parametrize("drift", ["changed", "missing", "added"])
def test_source_drift_blocks_before_remote_checks_or_staging(
    tmp_path, monkeypatch, drift
):
    import json
    from mn_context_benchmark.tasks import dataset
    from mn_context_benchmark.tasks.dataset import DEFAULT_FIXTURE

    copied = tmp_path / "blueprints"
    for relative, content in {
        "index.json": json.dumps(["vc_assistant"]),
        "vc_assistant/manifest.json": json.dumps({"id": "vc_assistant"}),
        "vc_assistant/SPEC.md": "Reviewed source policy.\n",
        "vc_assistant/contracts.json": "{}",
        "vc_assistant/config/default.json": "{}",
    }.items():
        target = copied / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
    catalog, sources = dataset.catalog_sources(copied)
    fixture = {
        "fixture_version": "unit-source-v1",
        "catalog": catalog,
        "sources": sources,
        "cases": [],
    }
    assert dataset.validate_sources(fixture, copied)["catalog_count"] == 1
    monkeypatch.setattr(dataset, "load_suite", lambda: fixture)
    changed = copied / "vc_assistant/SPEC.md"
    if drift == "changed":
        changed.write_text("Unreviewed policy")
    elif drift == "missing":
        changed.unlink()
    else:
        changed = copied / "vc_assistant/payloads/domain/instruction.py"
        changed.parent.mkdir(parents=True)
        changed.write_text("UNREVIEWED = True")
    monkeypatch.setattr(
        "subprocess.run", lambda *a, **k: pytest.fail("SSH before source admission")
    )
    with pytest.raises(
        ValueError, match="source prerequisite failed.*" + DEFAULT_FIXTURE
    ):
        run_spark(
            WORKSPACE,
            copied,
            tmp_path / "out",
            {"MN_ENABLE_TWO_BOX": "1", "MN_ENABLE_GPU_TESTS": "1"},
        )
    assert not (tmp_path / "out").exists()
