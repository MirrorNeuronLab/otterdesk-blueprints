import os
from pathlib import Path

import pytest

from membrane_benchmark_runner import run_spark

from workspace_paths import companion_workspace

BLUEPRINTS = Path(__file__).resolve().parents[1]
WORKSPACE = companion_workspace(BLUEPRINTS)
pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_OTTERDESK_TASK_BENCHMARK") != "1",
    reason="enable RUN_OTTERDESK_TASK_BENCHMARK plus two-box/GPU gates",
)


def test_frozen_tasks_and_calibrated_judge_on_spark(tmp_path):
    output = (
        Path(os.environ["OTTERDESK_TEST_RESULTS_DIR"])
        if os.environ.get("OTTERDESK_TEST_RESULTS_DIR")
        else tmp_path
    ) / "membrane-blueprint"
    root = BLUEPRINTS
    report = run_spark(
        WORKSPACE,
        root,
        output,
        os.environ,
        profile=os.environ.get("MN_MEMBRANE_PROFILE", "balanced"),
        reference=os.environ.get("MN_MEMBRANE_REFERENCE"),
        regrade_from=os.environ.get("MN_MEMBRANE_REGRADE_FROM"),
    )
    assert report["schema_version"] == "mn.membrane.task_benchmark.v2"
    assert report["metadata"]["engine_contract"] == "markdown-duckdb-peer.v1"
    assert report["metadata"]["engine_device"] == "cpu"
    assert report["peer_modes"]["cases_passed"] == 26
    assert report["runtime_invariants"]["passed"]
    assert report["judge_calibration"]["accepted"]
    assert report["judge_calibration"]["protocol_version"] == 2
    assert set(r["blueprint_id"] for r in report["rows"]) == set(report["catalog"])
    if report["profile"] == "balanced":
        assert len({r["case_id"] for r in report["rows"]}) == 60
        arms = report["metadata"]["measurement"]["arms"]
        assert len(report["rows"]) == 60 * 2 * 3 * len(arms)
        assert len(set(arms)) == len(arms)
        assert set(arms) == {"recency", "lexical", "A1", "A2", "A3"}
        assert [r["chunks"] for r in report["scaling"]] == [1000, 10000, 100000]
        assert [r["chunks"] for r in report["native_scaling"]["rows"]] == [
            1000,
            10000,
            100000,
        ]
    # Engine preservation is exact; task-quality failures are measured results,
    # never made invisible by a pytest skip or a changed success threshold.
    assert all(
        r.get("context", {}).get("privacy_preserved", True) for r in report["rows"]
    )
    assert all(r.get("context", {}).get("within_budget", True) for r in report["rows"])
    for row in report["rows"]:
        if "judgment" not in row:
            continue
        checks = row["task"]["checks"]
        if not all(
            checks[k]
            for k in (
                "schema_valid",
                "decision_correct",
                "facts_correct",
                "citations_supported",
            )
        ):
            assert row["judgment"]["ratings"]["grounding"] <= 1
            assert row["judgment"]["ratings"]["usefulness"] <= 1
    assert not any(
        c.get("task_success", {}).get("regression")
        or c.get("normalized_quality", {}).get("regression")
        or c.get("performance", {}).get("regression")
        for c in report.get("regressions", {}).get("arms", {}).values()
    )
    assert not report["run_tracking"]["regression_detected"], (
        "Benchmark execution completed, but a quality or performance regression was detected. "
        "Read 'Run tracking and regressions' in "
        + str(output / "results/report.md")
        + "; exact flagged metrics and reference values are retained in "
        + str(output / "results/tracking.json")
    )
    assert (output / "results/tracking.json").is_file()
    assert (output.parent.parent / "membrane-history.md").is_file()
