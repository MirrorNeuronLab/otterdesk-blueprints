"""Exercise each catalog entry through its compiled source, check and publication blocks."""
import json
from pathlib import Path
import shutil

import pytest

from block_workflow_fixture import run_sample
from mn_sdk.blueprints import compile_blueprint, read_blueprint
from mn_sdk.run_resources import normalize_run_resources

ROOT = Path(__file__).resolve().parents[1]
REGRESSIONS = {
    "functional": ("test_name.py", "def test_name():\n    assert True\n", "auto-test-oracles"),
    "security": ("client.py", "import requests\nrequests.get(url, verify=False)\n", "auto-tls-defaults"),
    "compatibility": ("wire.json", '{"protocol": 3}', "protocol"),
    "reliability": ("input.schema.json", '{}', "name-workload"),
}


@pytest.mark.parametrize("role", REGRESSIONS)
def test_standalone_workers_share_the_cpu_node(role):
    package = read_blueprint(ROOT / (role + "_verifier"))
    profile = normalize_run_resources(compile_blueprint(package).manifest)
    assert profile == {"mode": "shared", "cpu_cores": 1, "memory_mb": 1024, "disk_mb": 1024}


@pytest.mark.parametrize("role", REGRESSIONS)
@pytest.mark.parametrize("regression", [False, True], ids=["healthy", "regression"])
def test_standalone_sample_report_and_evidence(role, regression, tmp_path):
    name = role + "_verifier"
    package = read_blueprint(ROOT / name)
    source = tmp_path / "subject"
    shutil.copytree(ROOT / name / "examples/sample_inputs", source)
    path, change, affected = REGRESSIONS[role]
    if regression:
        (source / path).write_text(change)
    values = package.extension("mn.ui")["setup_guide"]["sample"]["values"]
    request = {"input_folder": str(source), "verification_scope": values["inputs.payload.verification_scope"]}
    result = run_sample(name, inputs=request, config={"inputs": {"payload": request}}, runs_root=tmp_path)
    report = result["final_artifact"]
    assert report["verdict"] == ("FAIL" if regression else "PASS")
    assert {row["specialist"] for row in report["checks"]} == {role}
    target = next(row for row in report["checks"] if row["id"] == affected)
    assert target["status"] == ("failed" if regression else "passed")
    assert target["attempts"][0]["evidence"] and len(target["attempts"]) == 1
    if regression:
        finding = report["findings"][0]
        assert {affected} <= set(finding["check_ids"])
        assert finding["expected"] and finding["recommendation"] and finding["reproduce"]
    directory = tmp_path / result["run_id"]
    assert json.loads((directory / "final_artifact.json").read_text()) == report
    assert target["id"].replace("-", "\\-") in (directory / "report.md").read_text()
    assert target["id"] in (directory / "web/index.html").read_text()
