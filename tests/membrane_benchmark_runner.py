"""Snapshot and run the component-owned benchmark on the configured SSH node."""

from __future__ import annotations

import hashlib
import json
import shlex
import subprocess
import tarfile
from pathlib import Path

from mn_system_tests.remote import configured_remote_command


SPARK_PREREQUISITES = r"""
import importlib.util,json,pathlib,shutil,subprocess
root=pathlib.Path.cwd()
assert (pathlib.Path.home()/'.cargo/bin/cargo').is_file(), 'Spark Rust toolchain missing'
assert shutil.which('protoc'), 'Spark protoc missing'
assert shutil.which('c++'), 'Spark C++ compiler missing for bundled DuckDB'
assert shutil.which('docker'), 'Spark Docker missing'
assert importlib.util.find_spec('grpc'), 'Spark Python gRPC missing'
assert shutil.which('nvidia-smi'), 'Spark GPU telemetry unavailable'
models=json.loads(subprocess.check_output(['docker','model','list','--json'],text=True))
for tag in ('docker.io/ai/nemotron-3.5-lightning:latest',):
 assert any(tag in x.get('tags',[]) for x in models), 'required installed model missing: '+tag
print('mn-membrane-prerequisites-ready')
"""


def spark_prerequisites(environment):
    # Gate checks belong to the runner and precede this read-only call.
    command = "mn-system-tests/.venv/bin/python -c " + shlex.quote(SPARK_PREREQUISITES)
    p = subprocess.run(
        configured_remote_command(command, environment),
        capture_output=True,
        text=True,
        timeout=30,
    )
    return p.returncode == 0 and "mn-membrane-prerequisites-ready" in p.stdout, (
        p.stderr or p.stdout
    )[-500:]


def snapshot(workspace, blueprints, destination):
    from mn_context_benchmark.tasks.dataset import catalog_sources

    workspace, blueprints = Path(workspace), Path(blueprints)
    _, sources = catalog_sources(blueprints)
    entries = []
    for relative, folders in (
        ("Membrane/mn-context-engine", ("src", "proto", "examples")),
        ("Membrane/mn-context-auto-optimizer-benchmark", ("src",)),
        ("Membrane/mn-context-engine-python-sdk", ("src", "build_backend")),
        ("mn-python-sdk", ("mn_sdk",)),
    ):
        root = workspace / relative
        for name in ("Cargo.toml", "Cargo.lock", "build.rs", "pyproject.toml"):
            if (root / name).is_file():
                entries.append((root / name, relative + "/" + name))
        for folder in folders:
            for p in sorted((root / folder).rglob("*")):
                if (
                    p.is_file()
                    and not p.is_symlink()
                    and "__pycache__" not in p.parts
                    and p.suffix not in {".pyc", ".so"}
                ):
                    entries.append((p, str(p.relative_to(workspace))))
    for relative in sources:
        entries.append((blueprints / relative, "otterdesk-blueprints/" + relative))
    hashes = {
        relative: hashlib.sha256(p.read_bytes()).hexdigest() for p, relative in entries
    }
    revisions = {}
    for name, root in (
        ("Membrane", workspace / "Membrane"),
        ("mn-python-sdk", workspace / "mn-python-sdk"),
        ("mn-system-tests", workspace / "mn-system-tests"),
        ("otterdesk-blueprints", blueprints),
    ):
        p = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True
        )
        revisions[name] = p.stdout.strip() if p.returncode == 0 else None
    manifest = {
        "source_revisions": revisions,
        "evaluated_file_sha256": hashes,
        "source_fingerprint": hashlib.sha256(
            json.dumps(hashes, sort_keys=True).encode()
        ).hexdigest(),
    }
    manifest_path = destination.parent / "evaluated-source.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    with tarfile.open(destination, "w:gz") as tar:
        for p, relative in entries:
            tar.add(p, arcname=relative, recursive=False)
        tar.add(manifest_path, arcname="evaluated-source.json")
    return manifest


def run_spark(
    workspace,
    blueprints,
    output,
    environment,
    profile="balanced",
    reference=None,
    regrade_from=None,
):
    if (
        environment.get("MN_ENABLE_TWO_BOX") != "1"
        or environment.get("MN_ENABLE_GPU_TESTS") != "1"
    ):
        raise RuntimeError(
            "Spark execution requires explicit two-node and GPU gates before SSH"
        )
    from mn_system_tests.membrane_history import load_reference, record_run
    from mn_context_benchmark.tasks.dataset import (
        DEFAULT_FIXTURE,
        load_suite,
        validate_sources,
    )

    if reference:
        from mn_context_benchmark.tasks import DUCKDB_SCHEMA, ENGINE_CONTRACT

        candidate = load_reference(reference)
        if (
            candidate.get("schema_version") != DUCKDB_SCHEMA
            or candidate["metadata"].get("engine_contract") != ENGINE_CONTRACT
        ):
            raise ValueError(
                "reference belongs to a different engine contract; preserve the historical baseline"
            )
    # Direct callers must also reject drift before creating an archive or using SSH.
    try:
        validate_sources(load_suite(), Path(blueprints))
    except (OSError, ValueError) as exc:
        raise ValueError(
            f"Membrane blueprint source prerequisite failed ({DEFAULT_FIXTURE}): {exc}"
        ) from exc
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    archive = output / "evaluated-source.tar.gz"
    snapshot(workspace, blueprints, archive)

    def remote(command, **kwargs):
        return subprocess.run(
            configured_remote_command(command, environment), check=True, **kwargs
        )

    made = remote(
        "python3 -c "
        + shlex.quote(
            "import tempfile; print(tempfile.mkdtemp(prefix='mn-membrane-',dir='/tmp'))"
        ),
        capture_output=True,
        text=True,
        timeout=15,
    )
    root = made.stdout.strip()
    if not root.startswith("/tmp/mn-membrane-") or any(
        c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789/_-"
        for c in root
    ):
        raise RuntimeError("invalid remote owned directory")
    quoted = shlex.quote(root)
    try:
        with archive.open("rb") as source:
            remote("tar -xz -C " + quoted, stdin=source, timeout=60)
        paths = (
            root
            + "/Membrane/mn-context-auto-optimizer-benchmark/src:"
            + root
            + "/Membrane/mn-context-engine-python-sdk/src:"
            + root
            + "/mn-python-sdk"
        )
        argv = [
            "mn-system-tests/.venv/bin/python",
            "-u",
            "-m",
            "mn_context_benchmark.tasks.runner",
            "--profile",
            profile,
            "--engine-root",
            root + "/Membrane/mn-context-engine",
            "--blueprint-root",
            root + "/otterdesk-blueprints",
            "--source-manifest",
            root + "/evaluated-source.json",
            "--output",
            root + "/results",
        ]
        if profile == "balanced":
            argv += ["--scaling", "--establish-reference"]
        if regrade_from:
            with Path(regrade_from).open("rb") as source:
                remote(
                    "cat > " + quoted + "/measured-execution.json",
                    stdin=source,
                    timeout=60,
                )
            argv += ["--regrade-report", root + "/measured-execution.json"]
        if reference:
            with Path(reference).open("rb") as source:
                remote("cat > " + quoted + "/reference.json", stdin=source, timeout=60)
            argv += ["--reference", root + "/reference.json"]
        observability = (
            "true"
            if environment.get("MN_CONTEXT_OBSERVABILITY", "").lower()
            in {"1", "true", "yes", "on"}
            else "false"
        )
        script = (
            "MN_CONTEXT_OBSERVABILITY="
            + observability
            + " PYTHONPATH="
            + shlex.quote(paths)
            + " "
            + shlex.join(argv)
        )
        completed = subprocess.run(
            configured_remote_command(script, environment), timeout=14400, check=False
        )
        # Copy only report evidence, never durable memory or host model/config files.
        names = [
            "report.json",
            "report.md",
            "evidence.jsonl",
            "quality-reference.json",
            "runtime/build.log",
            "runtime/engine-deterministic.log",
            "runtime/native-scaling.json",
            "runtime/native-scaling.log",
            "invariant-journal/invariants.json",
        ]
        pack = (
            "import pathlib,tarfile,sys; root=pathlib.Path("
            + repr(root)
            + "); t=tarfile.open(fileobj=sys.stdout.buffer,mode='w|gz'); [(t.add(root/'results'/n,arcname='results/'+n,recursive=False)) for n in "
            + repr(names)
            + " if (root/'results'/n).is_file()]; t.close()"
        )
        fetch = subprocess.run(
            configured_remote_command("python3 -c " + shlex.quote(pack), environment),
            capture_output=True,
            timeout=60,
        )
        if fetch.stdout:
            bundle = output / "reports.tar.gz"
            bundle.write_bytes(fetch.stdout)
            with tarfile.open(bundle) as tar:
                tar.extractall(output, filter="data")
        if not (output / "results/report.json").is_file():
            raise RuntimeError("remote benchmark produced no readable report")
        report = json.loads((output / "results/report.json").read_text())
        if report.get("phase") == "source_preflight":
            raise RuntimeError(
                "Spark source preflight failed: "
                + str(report.get("error"))
                + "; full failure evidence: "
                + str(output / "results/report.json")
            )
        tracked = record_run(output, reference)
        if completed.returncode != 0 or report["status"] != "complete":
            raise RuntimeError(
                "Spark benchmark "
                + report["status"]
                + ": "
                + str(report.get("error", "execution failed"))
                + "; full failure evidence: "
                + str(output / "results/report.json")
            )
        return tracked
    finally:
        # Scope is a validated mkdtemp generated by this call; no shared checkout.
        clean = """import pathlib,shutil,json,os,signal,subprocess
p=pathlib.Path(ROOT); assert p.parent==pathlib.Path('/tmp') and p.name.startswith('mn-membrane-')
registry=p/'results/runtime/owned.json'
if registry.is_file():
 owned=json.loads(registry.read_text())
 for pid in owned['pids']:
  cmd=pathlib.Path('/proc')/str(pid)/'cmdline'
  if cmd.is_file() and str(p).encode() in cmd.read_bytes():
   try: os.killpg(pid,signal.SIGTERM)
   except ProcessLookupError: pass
shutil.rmtree(p)
""".replace("ROOT", repr(root))
        cleanup = "python3 -c " + shlex.quote(clean)
        subprocess.run(
            configured_remote_command(cleanup, environment),
            capture_output=True,
            timeout=30,
        )
