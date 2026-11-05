"""Verify scaffolding and publication with real Git and an offline GitHub CLI."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]


def git(path, *arguments, env):
    return subprocess.check_output(
        ["git", "-C", str(path), *arguments],
        env=env,
        text=True,
        stderr=subprocess.PIPE,
    ).strip()


@pytest.fixture
def catalog(tmp_path):
    root = tmp_path / "catalog with spaces"
    root.mkdir()
    shutil.copytree(
        ROOT / "scripts", root / "scripts", ignore=shutil.ignore_patterns("__pycache__")
    )
    shutil.copytree(ROOT / "templates", root / "templates")
    (root / "index.json").write_text("[]\n")
    (root / "README.md").write_text("Catalog\n")
    remotes = tmp_path / "remote repositories"
    remotes.mkdir()
    config = tmp_path / "gitconfig"
    env = {
        **os.environ,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": str(config),
        "GIT_AUTHOR_NAME": "Blueprint test",
        "GIT_AUTHOR_EMAIL": "blueprint@example.invalid",
        "GIT_COMMITTER_NAME": "Blueprint test",
        "GIT_COMMITTER_EMAIL": "blueprint@example.invalid",
        "GIT_ALLOW_PROTOCOL": "file",
        "FAKE_GH_REMOTES": str(remotes),
        "FAKE_GH_CALLS": str(tmp_path / "gh-calls.jsonl"),
    }
    for prefix in (
        "git@github.com:MirrorNeuronLab/",
        "https://github.com/MirrorNeuronLab/",
    ):
        git(
            root,
            "config",
            "--file",
            str(config),
            "--add",
            f"url.{remotes.as_uri()}/.insteadOf",
            prefix,
            env=env,
        )
    git(root, "init", "--initial-branch=main", env=env)
    git(root, "add", ".", env=env)
    git(root, "commit", "-m", "Catalog baseline", env=env)
    binary = tmp_path / "bin"
    binary.mkdir()
    gh = binary / "gh"
    gh.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, pathlib, subprocess, sys\n"
        "args = sys.argv[1:]\n"
        "with open(os.environ['FAKE_GH_CALLS'], 'a') as log:\n"
        "    log.write(json.dumps(args) + '\\n')\n"
        "if args[:2] == ['auth', 'status']:\n"
        "    sys.exit(1 if os.environ.get('FAKE_GH_AUTH_FAIL') else 0)\n"
        "if args[:2] != ['repo', 'create'] or '--public' not in args:\n"
        "    sys.exit('Unexpected GitHub CLI call')\n"
        "remote = pathlib.Path(os.environ['FAKE_GH_REMOTES']) / (args[2].split('/')[-1] + '.git')\n"
        "if remote.exists() or os.environ.get('FAKE_GH_CREATE_FAIL'):\n"
        "    sys.exit('Repository already exists or creation was denied')\n"
        "subprocess.run(['git', 'init', '--bare', '--initial-branch=main', str(remote)], check=True, capture_output=True)\n"
        "if os.environ.get('FAKE_GH_REJECT_PUSH'):\n"
        "    hook = remote / 'hooks/pre-receive'\n"
        "    hook.write_text('#!/bin/sh\\nexit 1\\n')\n"
        "    hook.chmod(0o755)\n"
    )
    gh.chmod(0o755)
    env["PATH"] = str(binary) + os.pathsep + env["PATH"]
    return SimpleNamespace(root=root, remotes=remotes, env=env, temporary=tmp_path)


def create(catalog, *arguments):
    return subprocess.run(
        ["bash", str(catalog.root / "scripts/create_blueprint.sh"), *arguments],
        cwd=catalog.temporary,
        env=catalog.env,
        text=True,
        capture_output=True,
        timeout=30,
    )


def calls(catalog):
    path = Path(catalog.env["FAKE_GH_CALLS"])
    return (
        [json.loads(line) for line in path.read_text().splitlines()]
        if path.exists()
        else []
    )


def test_creates_public_repo_and_pinned_submodule_without_committing_other_work(
    catalog,
):
    root, env = catalog.root, catalog.env
    before = git(root, "rev-parse", "HEAD", env=env)
    (root / "README.md").write_text("Unrelated staged edit\n")
    git(root, "add", "README.md", env=env)
    staged = git(root, "diff", "--cached", "--", "README.md", env=env)
    (root / "notes.txt").write_text("Unrelated untracked note\n")
    result = create(catalog, "-n", "example_blueprint")
    assert result.returncode == 0, result.stderr
    child = root / "example_blueprint"
    remote = catalog.remotes / "mn-blueprint-example_blueprint.git"
    pin = git(child, "rev-parse", "HEAD", env=env)
    assert git(remote, "rev-parse", "main", env=env) == pin
    assert git(root, "ls-files", "--stage", "--", child.name, env=env).startswith(
        f"160000 {pin} 0"
    )
    assert (child / ".git").is_file()
    assert (
        git(child, "config", "remote.origin.url", env=env)
        == "git@github.com:MirrorNeuronLab/mn-blueprint-example_blueprint.git"
    )
    assert (
        git(
            root,
            "config",
            "--file",
            ".gitmodules",
            "submodule.example_blueprint.url",
            env=env,
        )
        == "https://github.com/MirrorNeuronLab/mn-blueprint-example_blueprint.git"
    )
    assert (
        git(
            root,
            "config",
            "--file",
            ".gitmodules",
            "submodule.example_blueprint.branch",
            env=env,
        )
        == "main"
    )
    assert git(root, "rev-parse", "HEAD", env=env) == before
    assert git(root, "diff", "--cached", "--", "README.md", env=env) == staged
    assert (root / "notes.txt").read_text() == "Unrelated untracked note\n"
    assert (root / "index.json").read_text() == "[]\n"
    assert calls(catalog)[1][:3] == [
        "repo",
        "create",
        "MirrorNeuronLab/mn-blueprint-example_blueprint",
    ]
    assert "--public" in calls(catalog)[1]
    for name in (
        "README.md",
        "SPEC.md",
        "TERM.md",
        "LICENSE.md",
        "manifest.json",
        "config/default.json",
        "payloads/steps/.gitkeep",
        "payloads/domain/noop.py",
        "tests/test_noop.py",
    ):
        assert (child / name).is_file()
    assert "MIT License" in (child / "LICENSE.md").read_text()
    assert "{{" not in (child / "manifest.json").read_text()
    git(
        child,
        "check-ignore",
        ".env",
        ".env.production",
        "config/overwrite.json",
        env=env,
    )
    standalone = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests"],
        cwd=child,
        env=env,
        text=True,
        capture_output=True,
    )
    assert standalone.returncode == 0, standalone.stderr


def test_generated_blueprint_compiles_and_executes_the_stock_noop_worker(
    catalog, monkeypatch
):
    from mn_sdk.blueprints import compile_blueprint, read_blueprint, resolve_config
    from mn_sdk.blueprints.worker_descriptors import resolved_worker_descriptor
    from mn_sdk.components import ComponentRegistry
    from mn_sdk.step_runtime import StepContext, invoke_handler
    from mn_sdk_common.committed_artifacts import CommittedJsonStore

    result = create(catalog, "-n", "empty-worker")
    assert result.returncode == 0, result.stderr
    root = catalog.root / "empty-worker"
    package = read_blueprint(root)
    configuration = resolve_config(package)
    compiled = compile_blueprint(package, configuration).manifest
    assert [step["id"] for step in compiled["workflow"]["steps"]] == ["do_nothing"]
    assert "gpu" not in compiled["requirements"]
    assert package.document("dependencies")["skills"] == []
    node = next(
        node for node in compiled["agents"]["nodes"] if node["agent_type"] == "executor"
    )
    assert node["config"]["runner_module"] == "MirrorNeuron.Runner.HostLocal"
    binding = node["config"]["environment"]
    descriptor = catalog.temporary / "descriptor.json"
    descriptor.write_text(
        json.dumps(resolved_worker_descriptor(package, compiled, configuration))
    )
    run_directory = catalog.temporary / "run"
    environment = {
        "MN_BLUEPRINT_BUNDLE_DIR": str(root),
        "MN_BLUEPRINT_MANIFEST_PATH": str(descriptor),
        "MN_RUN_DIR": str(run_directory),
        "MN_WORKDIR": str(catalog.temporary / "worker"),
        "MN_SDK_COMPONENTS_JSON": json.dumps(
            sorted(ComponentRegistry.from_manifest(compiled).enabled)
        ),
    }
    for name, value in environment.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("MN_HOME", str(catalog.temporary / "mn-home"))
    monkeypatch.syspath_prepend(str(root / "payloads"))
    context = StepContext(
        step_id="do_nothing",
        agent_id="block_do_nothing_specialist",
        run_id="starter-test",
        job_id="starter-test",
        idempotency_key="starter-test/do-nothing",
        invocation_id=binding["MN_WORKFLOW_INVOCATION_ID"],
        config=configuration.data,
        environment=environment,
        message={"body": {"step_input": {}}},
    )
    parameters = json.loads(binding["MN_WORKFLOW_STEP_WITH_JSON"])
    result = invoke_handler(
        binding["MN_WORKFLOW_STEP_HANDLER"], context=context, parameters=parameters
    )
    assert result["status"] == "completed"
    assert CommittedJsonStore(run_directory).read(result["outputs"]["result"]) == {}
    # The same invocation replays its committed empty result successfully.
    replay = invoke_handler(
        binding["MN_WORKFLOW_STEP_HANDLER"], context=context, parameters=parameters
    )
    assert replay["outputs"] == result["outputs"]


@pytest.mark.parametrize(
    "name",
    [
        "",
        "../escape",
        "bad/name",
        "two words",
        "$(touch secret)",
        "Uppercase",
        "con",
        "nul",
        "a" * 65,
    ],
)
def test_invalid_names_have_no_git_or_github_side_effects(catalog, name):
    result = create(catalog, "-n", name)
    assert result.returncode != 0
    assert calls(catalog) == []
    assert git(catalog.root, "status", "--porcelain", env=catalog.env) == ""
    assert list(catalog.remotes.iterdir()) == []


@pytest.mark.parametrize("arguments, status", [((), 2), (("-n",), 2), (("--help",), 0)])
def test_name_is_required_and_help_does_not_touch_github(catalog, arguments, status):
    result = create(catalog, *arguments)
    assert result.returncode == status
    assert "-n" in result.stdout + result.stderr
    assert calls(catalog) == []


def test_existing_folder_is_preserved(catalog):
    target = catalog.root / "existing"
    target.mkdir()
    (target / "user.txt").write_text("Keep this\n")
    result = create(catalog, "-n", target.name)
    assert result.returncode != 0
    assert (target / "user.txt").read_text() == "Keep this\n"
    assert calls(catalog) == []


def test_existing_catalog_identity_is_rejected_even_when_its_folder_has_another_name(
    catalog,
):
    published = catalog.root / "published_folder"
    published.mkdir()
    (published / "manifest.json").write_text('{"id": "existing_id"}')
    (catalog.root / "index.json").write_text('["published_folder"]')
    result = create(catalog, "-n", "existing_id")
    assert result.returncode != 0
    assert "already belongs to published_folder" in result.stderr
    assert not (catalog.root / "existing_id").exists()
    assert calls(catalog) == []


def test_authentication_failure_does_not_create_a_folder(catalog):
    catalog.env["FAKE_GH_AUTH_FAIL"] = "1"
    result = create(catalog, "-n", "new_worker")
    assert result.returncode != 0
    assert "gh auth login" in result.stderr
    assert not (catalog.root / "new_worker").exists()
    assert len(calls(catalog)) == 1


def test_existing_remote_is_not_overwritten_or_registered(catalog):
    remote = catalog.remotes / "mn-blueprint-existing.git"
    remote.mkdir()
    (remote / "marker.txt").write_text("Existing remote\n")
    result = create(catalog, "-n", "existing")
    assert result.returncode != 0
    assert (remote / "marker.txt").read_text() == "Existing remote\n"
    assert not (catalog.root / "existing").exists()
    assert git(catalog.root, "status", "--porcelain", env=catalog.env) == ""


def test_failed_push_keeps_new_scaffold_but_does_not_stage_a_broken_pin(catalog):
    catalog.env["FAKE_GH_REJECT_PUSH"] = "1"
    result = create(catalog, "-n", "new_worker")
    assert result.returncode != 0
    assert "Starter preserved" in result.stderr
    assert (catalog.root / "new_worker/manifest.json").is_file()
    assert (catalog.root / "new_worker/.git").is_dir()
    assert not (catalog.root / ".gitmodules").exists()
    assert git(catalog.root, "diff", "--cached", "--name-only", env=catalog.env) == ""


def test_pending_submodule_metadata_is_not_overwritten(catalog):
    (catalog.root / ".gitmodules").write_text("# Unrelated metadata draft\n")
    result = create(catalog, "-n", "new_worker")
    assert result.returncode != 0
    assert ".gitmodules changes" in result.stderr
    assert (catalog.root / ".gitmodules").read_text() == "# Unrelated metadata draft\n"
    assert calls(catalog) == []
