from __future__ import annotations

import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

import pytest

ROOT = Path(__file__).resolve().parents[1] / "cctv_operator" / "payloads"
pytestmark = pytest.mark.skipif(os.name != "posix", reason="DockerWorker process groups are POSIX")


def await_file(path: Path):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if path.exists():
            return path.read_text()
        time.sleep(0.01)
    pytest.fail(f"Process did not publish {path.name}")


def kill_group(process):
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    process.wait(timeout=5)


@pytest.fixture
def launches(tmp_path):
    # Keep production launch commands, substituting only the image-owned helper
    # with a publisher fixture. No GPU, network, or user-home access is needed.
    helper = tmp_path / "start_demo_stream.py"
    helper.write_text(f"#!{sys.executable}\n" + """
import json, os, pathlib, subprocess, sys, time
root = pathlib.Path(__file__).parent
if sys.argv[1] == '--wait':
    deadline = time.monotonic() + 5
    while not (root / 'publisher.pid').exists():
        if time.monotonic() >= deadline:
            sys.exit(1)
        time.sleep(0.01)
    (root / 'waited').write_text('ready')
else:
    (root / 'start.args').write_text(json.dumps(sys.argv[1:]))
    if os.environ.get('FAIL_DEMO_START'):
        sys.exit(1)
    publisher = subprocess.Popen([sys.executable, str(root / 'publisher.py')])
    (root / 'publisher.pid').write_text(str(publisher.pid))
""")
    helper.chmod(0o755)
    (tmp_path / "publisher.py").write_text("""
import pathlib, signal, time
root = pathlib.Path(__file__).parent
def stop(*args):
    (root / 'publisher.stopped').write_text('stopped')
    raise SystemExit(0)
signal.signal(signal.SIGTERM, stop)
(root / 'publisher.ready').write_text('ready')
while True:
    time.sleep(1)
""")
    (tmp_path / "services").mkdir()
    (tmp_path / "scripts").mkdir()
    (tmp_path / "services/cctv_web_ui.py").write_text("""
import pathlib, time
pathlib.Path('ui.ready').write_text('ready')
while True:
    time.sleep(1)
""")
    (tmp_path / "scripts/sample_video.py").write_text("from pathlib import Path; Path('sample.done').write_text('done')\n")
    for name, relative in {
        "ui": "services/run_cctv_web_ui.sh",
        "sampler": "agents/adaptive_frame_sampler/scripts/run_sampler_on_nvidia.sh",
    }.items():
        source = (ROOT / relative).read_text()
        (tmp_path / f"{name}.sh").write_text(source.replace("/opt/cctv-demo/start_demo_stream.sh", str(helper)))
    return tmp_path


def launch(root, name, profile="bundled_demo", **overrides):
    env = {**os.environ, **overrides, "MN_BLUEPRINT_CONFIG_JSON": json.dumps({"video_source": {
        "profile": profile, "demo_file": "/staged/warehouse demo.mp4",
    }})}
    return subprocess.Popen(["bash", f"{name}.sh"], cwd=root, env=env, start_new_session=True,
                            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


def test_demo_publisher_survives_sampling_cleanup_and_stops_with_service(launches):
    # Entrypoints start concurrently: sampling must wait, then completing its
    # invocation and killing its descendants must leave the publisher running.
    sampler = launch(launches, "sampler")
    service = launch(launches, "ui")
    try:
        await_file(launches / "ui.ready")
        await_file(launches / "publisher.ready")
        publisher_pid = int(await_file(launches / "publisher.pid"))
        assert os.getpgid(publisher_pid) == service.pid
        assert json.loads((launches / "start.args").read_text()) == ["/staged/warehouse demo.mp4"]
        assert sampler.wait(timeout=5) == 0
        assert (launches / "waited").read_text() == "ready"
        assert (launches / "sample.done").read_text() == "done"
        kill_group(sampler)  # MirrorNeuron cleans the completed invocation group.
        os.kill(publisher_pid, 0)
        assert not (launches / "publisher.stopped").exists()
        kill_group(service)
        assert await_file(launches / "publisher.stopped") == "stopped"
    finally:
        kill_group(sampler)
        kill_group(service)


def test_external_source_skips_demo_start_and_wait(launches):
    service = launch(launches, "ui", profile="external")
    sampler = launch(launches, "sampler", profile="external")
    try:
        await_file(launches / "ui.ready")
        assert sampler.wait(timeout=5) == 0
        assert not (launches / "start.args").exists()
        assert not (launches / "waited").exists()
    finally:
        kill_group(service)
        kill_group(sampler)


def test_failed_demo_start_does_not_launch_ui(launches):
    service = launch(launches, "ui", FAIL_DEMO_START="1")
    try:
        assert service.wait(timeout=5) != 0
        assert not (launches / "ui.ready").exists()
        assert not (launches / "publisher.pid").exists()
    finally:
        kill_group(service)


def test_demo_wait_only_probes_readiness(tmp_path):
    tools = tmp_path / "tools"
    tools.mkdir()
    timeout = tools / "timeout"
    timeout.write_text('#!/bin/sh\nshift\nexec "$@"\n')
    timeout.chmod(0o755)
    probe = tools / "ffprobe"
    probe.write_text('#!/bin/sh\nprintf "%s\\n" "$@" > "$PROBE_ARGS"\n')
    probe.chmod(0o755)
    result = subprocess.run(["bash", str(ROOT / "docker_worker/demo/start_demo_stream.sh"), "--wait"],
                            env={**os.environ, "PATH": f"{tools}:{os.environ['PATH']}",
                                 "PROBE_ARGS": str(tmp_path / "probe.args")},
                            capture_output=True, timeout=5)
    assert result.returncode == 0, result.stderr.decode()
    assert "rtsp://127.0.0.1:8554/cctv-demo" in (tmp_path / "probe.args").read_text()
