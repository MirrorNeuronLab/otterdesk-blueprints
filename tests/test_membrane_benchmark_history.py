"""Product benchmark transport preserves immutable measured history."""

import copy
import io
import json
import subprocess
import tarfile
import pytest
from mn_context_benchmark.tasks import ARMS, SCHEMA
from mn_context_benchmark.tasks.reporting import summarize
from membrane_benchmark_runner import run_spark


def measured_report():
    """Synthetic protocol receipts for helper tests, never saved to live results."""
    catalog = [f"blueprint-{i}" for i in range(12)]
    rows = [
        {
            "case_id": f"{bp}/{checkpoint}",
            "blueprint_id": bp,
            "budget": budget,
            "repetition": repetition,
            "arm": arm,
            "path": "prompt",
            "status": "completed",
            "task": {"success": True},
            "judgment": {"normalized_quality": 1},
            "performance": {"task_seconds": 2, "model_calls": 1},
        }
        for bp in catalog
        for checkpoint in range(5)
        for budget in (2048, 4096)
        for repetition in range(3)
        for arm in ARMS
    ]
    return {
        "schema_version": SCHEMA,
        "execution_mode": "live",
        "status": "complete",
        "profile": "balanced",
        "catalog": catalog,
        "rows": rows,
        "runtime_invariants": {"passed": True},
        "judge_calibration": {"accepted": True, "protocol_version": 2},
        "metadata": {
            "fixture_fingerprint": "frozen",
            "protocol_fingerprint": "protocol",
            "grading_contract": "transport-provenance-citations-and-domain-bounded-judge.v3",
            "artifacts": {"medium": {"digest": "sha256:unit-test-only"}},
            "tokenizer": {"measured": True},
            "serving_allocations": {"slots": 4},
            "measurement": {"seed": 1947},
            "hardware": {"gpu": "unit-test-only"},
        },
        "scaling": [
            {
                "records": n,
                "samples": 200,
                "workload": {"clients": 1, "max_items": 10},
                "p95_ms": 2,
                "concurrent_p95_ms": {"4": 3, "16": 6},
                "ingestion_seconds": n / 1000,
            }
            for n in (1000, 10000, 100000)
        ],
    }


def save(collection, run_id, report=None):
    report = copy.deepcopy(report or measured_report())
    report["started_at"] = "2026-10-" + run_id + "T12:00:00+00:00"
    report["summary"] = summarize(report["rows"], report["catalog"])
    output = collection / run_id / "membrane-spark"
    result = output / "results"
    result.mkdir(parents=True)
    (result / "report.json").write_text(json.dumps(report))
    (result / "report.md").write_text("# Measured benchmark\n")
    (result / "quality-reference.json").write_text(json.dumps(report))
    (result / "evidence.jsonl").write_text("unit-test-only\n")
    return output


def duckdb_report():
    from mn_context_benchmark.tasks import DUCKDB_SCHEMA, ENGINE_CONTRACT
    from mn_context_benchmark.tasks.peer_modes import cases

    report = measured_report()
    report["schema_version"] = DUCKDB_SCHEMA
    original = report["rows"]
    report["rows"] = [r for r in original if r["arm"] in {"recency", "lexical"}]
    for row in original:
        if row["arm"] == "membrane":
            report["rows"].extend(
                [{**copy.deepcopy(row), "arm": arm} for arm in ("A1", "A2", "A3")]
            )
    report["metadata"].update(
        engine_contract=ENGINE_CONTRACT,
        engine_device="cpu",
        model_compression_enabled=False,
        v2_arms=["A1", "A2", "A3"],
    )
    report["metadata"]["measurement"]["arms"] = ["recency", "lexical", "A1", "A2", "A3"]
    report["peer_modes"] = {
        "execution_mode": "real_rust_rpc_mechanical",
        "cases_passed": len(cases()),
        "rows": [
            {"case_id": case["id"], "mechanical_result_correct": True}
            for case in cases()
        ],
    }
    report["scaling"] = [
        {
            "chunks": n,
            "samples": 200,
            "workload": {"clients": 1},
            "scope": "verified Markdown RAW",
            "p95_ms": 20,
            "ingestion_seconds": 1,
        }
        for n in (1000, 10000, 100000)
    ]
    report["native_scaling"] = {
        "schema": "mn.membrane.duckdb_mode_scaling.v1",
        "scope": "native hash-verified queries",
        "vectors": "mechanical",
        "rows": [
            {
                "chunks": n,
                "samples": 10,
                "embedding_dimensions": 8,
                "raw_source_bytes": n * 4096,
                "semantic_p95_ms": 10,
                "graph_p95_ms": 50,
                "analytical_p95_ms": 100,
            }
            for n in (1000, 10000, 100000)
        ],
    }
    return report


def test_invalid_explicit_reference_is_rejected_before_ssh(tmp_path, monkeypatch):
    path = tmp_path / "scripted.json"
    path.write_text(
        json.dumps({"schema_version": SCHEMA, "execution_mode": "scripted"})
    )
    monkeypatch.setattr(
        "subprocess.run", lambda *a, **k: pytest.fail("SSH before reference validation")
    )
    with pytest.raises(ValueError, match="live"):
        run_spark(
            tmp_path,
            tmp_path,
            tmp_path / "out",
            {"MN_ENABLE_TWO_BOX": "1", "MN_ENABLE_GPU_TESTS": "1"},
            reference=path,
        )


def test_spark_fetch_automatically_records_history_after_measurement(
    tmp_path, monkeypatch
):
    report = duckdb_report()
    report["started_at"] = "2026-10-02T12:00:00+00:00"
    report["summary"] = summarize(report["rows"], report["catalog"])
    data = json.dumps(report).encode()
    bundle = io.BytesIO()
    with tarfile.open(fileobj=bundle, mode="w:gz") as tar:
        for name, content in (
            ("report.json", data),
            ("quality-reference.json", data),
            ("report.md", b"# Measured benchmark\n"),
        ):
            item = tarfile.TarInfo("results/" + name)
            item.size = len(content)
            tar.addfile(item, io.BytesIO(content))
    commands = []

    def remote(argv, **kwargs):
        commands.append(argv[-1])
        if "mkdtemp" in argv[-1]:
            return subprocess.CompletedProcess(argv, 0, "/tmp/mn-membrane-owned-test\n")
        if "w|gz" in argv[-1]:
            return subprocess.CompletedProcess(argv, 0, bundle.getvalue())
        return subprocess.CompletedProcess(argv, 0, "")

    monkeypatch.setattr(
        "membrane_benchmark_runner.configured_remote_command",
        lambda command, env: ["injected-ssh", command],
    )
    monkeypatch.setattr("subprocess.run", remote)
    output = tmp_path / "02/membrane-spark"

    # The source archive is opened for transfer; its contents are irrelevant to this transport witness.
    def snapshot(*args):
        args[-1].write_bytes(b"injected-source")

    monkeypatch.setattr("membrane_benchmark_runner.snapshot", snapshot)
    # This witness measures transport/history only; source admission has its own strict gate.
    monkeypatch.setattr(
        "mn_context_benchmark.tasks.dataset.validate_sources", lambda *a: {}
    )
    tracked = run_spark(
        tmp_path,
        tmp_path,
        output,
        {
            "MN_ENABLE_TWO_BOX": "1",
            "MN_ENABLE_GPU_TESTS": "1",
            "MN_CONTEXT_OBSERVABILITY": "true",
        },
    )
    assert any(
        command.startswith("MN_CONTEXT_OBSERVABILITY=true PYTHONPATH=")
        for command in commands
    )
    assert tracked["run_tracking"]["status"] == "baseline"
    assert (output / "results/report.json").read_bytes() == data
    assert (output / "results/tracking.json").is_file()
    assert (tmp_path / "membrane-history.md").is_file()
    assert "shutil.rmtree" in commands[-1]  # Cleanup still occurs after tracking.
