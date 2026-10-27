"""Repository staging must apply dependency exclusions before resolving links."""

import json
from pathlib import Path

import pytest

from mn_sdk.blueprints import read_blueprint, resolve_config
from mn_sdk.submission import prepare_job_submission
from mn_sdk.submission_types import SubmissionPreparationError


BLUEPRINT = Path(__file__).resolve().parents[2] / "software_architecture_advisor"


def stage_repository(repository, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("MN_HOME", str(tmp_path / "mn-home"))
    config = resolve_config(read_blueprint(BLUEPRINT)).data
    config["inputs"]["payload"]["input_folder"] = str(repository)
    manifest = {
        "apiVersion": "mn.workflow/v1", "kind": "Workflow",
        "id": "software_architecture_advisor", "contract": {}, "runtime": {},
        "agents": {"nodes": [{"node_id": "capture", "config": {"environment": {
            "MN_BLUEPRINT_CONFIG_JSON": json.dumps(config),
        }}}]},
    }
    prepared = prepare_job_submission(
        manifest, {}, bundle_dir=BLUEPRINT, shared_storage_root=tmp_path / "shared",
        runtime_shared_storage_root="/runtime/shared",
    )
    staged_manifest = json.loads(prepared.manifest_json)
    storage = staged_manifest["metadata"]["mn_storage"]
    return Path(storage["host_submission_path"]) / "inputs/mn_local_inputs/repository"


def test_staging_prunes_dependencies_and_builds_but_preserves_source_and_git(tmp_path, monkeypatch):
    repository = tmp_path / "repository with spaces"
    retained = {
        "src/main.py": b"def run(): return True\n",
        "src/custom.dsl": b"module Main\n",
        "test/test_main.py": b"def test_run(): pass\n",
        ".git/HEAD": b"ref: refs/heads/main\n",
        ".git/index": b"frozen index",
        ".git/objects/pack/history.pack": b"frozen history",
    }
    for name, content in retained.items():
        path = repository / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    outside = tmp_path / "host-python"
    outside.write_text("outside the source boundary")
    for directory in (".venv", "venv", "node_modules", "nested/node_modules", "__pycache__",
                      "target", "dist", "build", "_build", "deps", ".tox", ".nox",
                      ".pytest_cache", ".mypy_cache", ".ruff_cache"):
        path = repository / directory
        path.mkdir(parents=True)
        (path / "python").symlink_to(outside)
        (path / "generated.py").write_text("excluded dependency or build output")

    staged = stage_repository(repository, tmp_path, monkeypatch)

    assert {p.relative_to(staged).as_posix(): p.read_bytes()
            for p in staged.rglob("*") if p.is_file()} == retained


def test_staging_still_rejects_source_links_outside_the_repository(tmp_path, monkeypatch):
    repository = tmp_path / "repository"
    repository.mkdir()
    outside = tmp_path / "private.py"
    outside.write_text("private = True\n")
    (repository / "source.py").symlink_to(outside)

    with pytest.raises(SubmissionPreparationError, match="escapes selected folder"):
        stage_repository(repository, tmp_path, monkeypatch)
