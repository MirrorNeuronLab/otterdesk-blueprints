"""Opt-in offline Linux integration with a prepared wheelhouse and RGX worker."""

import os
from pathlib import Path
import subprocess

import pytest


@pytest.mark.skipif(
    not os.environ.get("MN_LITIGATION_TEST_IMAGE"),
    reason="opt-in Linux Docker integration",
)
def test_linux_worker_with_actual_graph_engine():
    root = Path(__file__).resolve().parents[2]
    blueprint = root / "litigation_analyst"
    wheels = Path(os.environ["MN_LITIGATION_TEST_WHEELS"]).resolve(strict=True)
    script = Path(__file__).resolve().parent
    command = ["docker", "run", "--rm", "--network", "none", "--workdir", "/tmp"]
    for source, target in (
        (wheels, "/wheels"),
        (script, "/smoke"),
        (blueprint, "/blueprint"),
    ):
        command += ["--mount", f"type=bind,src={source},dst={target},readonly"]
    command += [
        "-e",
        "PYTHONPATH=/blueprint/payloads",
        "-e",
        "MN_BLUEPRINT_BUNDLE_DIR=/blueprint",
        "-e",
        "PATH=/blueprint/payloads/docker_worker/engine/bin:/usr/local/bin:/usr/bin:/bin",
        "--entrypoint",
        "python",
        os.environ["MN_LITIGATION_TEST_IMAGE"],
        "-c",
        'import glob,subprocess,runpy; subprocess.run(["python","-m","pip","install","--no-index","--no-deps",*glob.glob("/wheels/*.whl")],check=True); runpy.run_path("/smoke/linux_worker_smoke.py")',
    ]
    result = subprocess.run(command, capture_output=True, text=True, timeout=180)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS: actual Linux RGX" in result.stdout
