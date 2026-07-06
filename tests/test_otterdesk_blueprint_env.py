from __future__ import annotations

import os
import sys
import types
from pathlib import Path

import otterdesk_blueprint_env
from otterdesk_blueprint_env import (
    bootstrap_blueprint_runtime,
    find_repo_root,
    load_blueprint_env,
    normalized_env,
    parse_env_line,
    workspace_root,
)


def test_normalized_env_defaults_to_production():
    assert normalized_env(None) == "production"
    assert normalized_env("prod") == "production"
    assert normalized_env("dev") == "development"


def test_parse_env_line_handles_export_quotes_and_comments():
    assert parse_env_line("export MN_ENV=dev") == ("MN_ENV", "dev")
    assert parse_env_line("FOO=value # comment") == ("FOO", "value")
    assert parse_env_line('FOO="value # kept"') == ("FOO", "value # kept")
    assert parse_env_line("# ignored") is None


def test_load_blueprint_env_keeps_real_environment_over_env_files(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "AGENTS.md").write_text("", encoding="utf-8")
    (repo / "otterdesk_blueprint_env.py").write_text("", encoding="utf-8")
    (repo / ".env").write_text("MN_ENV=dev\nSHARED=base\nREAL_ENV=file\n", encoding="utf-8")
    (repo / ".env.development").write_text("SHARED=development\nDEV_ONLY=1\n", encoding="utf-8")
    (repo / ".env.local").write_text("SHARED=local\nLOCAL_ONLY=1\n", encoding="utf-8")

    monkeypatch.setenv("REAL_ENV", "shell")
    for key in ("MN_ENV", "SHARED", "DEV_ONLY", "LOCAL_ONLY"):
        monkeypatch.delenv(key, raising=False)

    result = load_blueprint_env(repo / "blueprint" / "run_blueprint.py")

    assert result["env"] == "development"
    assert os.environ["MN_ENV"] == "dev"
    assert os.environ["SHARED"] == "local"
    assert os.environ["DEV_ONLY"] == "1"
    assert os.environ["LOCAL_ONLY"] == "1"
    assert os.environ["REAL_ENV"] == "shell"


def test_load_blueprint_env_defaults_to_production_without_selector(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "AGENTS.md").write_text("", encoding="utf-8")
    (repo / "otterdesk_blueprint_env.py").write_text("", encoding="utf-8")
    (repo / ".env.production").write_text("MN_USE_LOCAL_SKILLS=0\nPROD_ONLY=1\n", encoding="utf-8")
    (repo / ".env.development").write_text("MN_USE_LOCAL_SKILLS=1\nDEV_ONLY=1\n", encoding="utf-8")

    for key in ("MN_ENV", "MN_USE_LOCAL_SKILLS", "PROD_ONLY", "DEV_ONLY"):
        monkeypatch.delenv(key, raising=False)

    result = load_blueprint_env(repo)

    assert result["env"] == "production"
    assert os.environ["MN_ENV"] == "production"
    assert os.environ["MN_USE_LOCAL_SKILLS"] == "0"
    assert os.environ["PROD_ONLY"] == "1"
    assert "DEV_ONLY" not in os.environ


def test_find_repo_root_resolves_relative_start(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "AGENTS.md").write_text("", encoding="utf-8")
    (repo / "otterdesk_blueprint_env.py").write_text("", encoding="utf-8")
    script = repo / "blueprint" / "scripts" / "run_blueprint.py"
    script.parent.mkdir(parents=True)
    script.write_text("", encoding="utf-8")
    monkeypatch.chdir(repo)

    relative_script = Path("blueprint/scripts/run_blueprint.py")

    assert find_repo_root(relative_script) == repo.resolve()
    assert workspace_root(relative_script) == tmp_path.resolve()


def test_bootstrap_blueprint_runtime_uses_installed_packages_in_production(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "AGENTS.md").write_text("", encoding="utf-8")
    (repo / "otterdesk_blueprint_env.py").write_text("", encoding="utf-8")
    (repo / ".env.production").write_text("MN_USE_LOCAL_SKILLS=0\n", encoding="utf-8")
    for key in ("MN_ENV", "MN_USE_LOCAL_SKILLS"):
        monkeypatch.delenv(key, raising=False)

    result = bootstrap_blueprint_runtime(repo, packages=["mirrorneuron-blueprint-support-skill"])

    assert result["mode"] == "installed_packages"
    assert result["modules"] == []


def test_bootstrap_blueprint_runtime_delegates_local_skills_to_sdk(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    workspace = tmp_path
    repo.mkdir()
    (repo / "AGENTS.md").write_text("", encoding="utf-8")
    (repo / "otterdesk_blueprint_env.py").write_text("", encoding="utf-8")
    (repo / ".env.development").write_text("MN_USE_LOCAL_SKILLS=1\n", encoding="utf-8")
    for key in ("MN_ENV", "MN_USE_LOCAL_SKILLS"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("MN_ENV", "dev")

    calls = []
    sdk_package = types.ModuleType("mn_sdk")
    runtime_modules = types.ModuleType("mn_sdk.runtime_modules")

    def fake_ensure(required, **kwargs):
        calls.append((required, kwargs))
        return {"ok": True, "skills_root": str(workspace / "mn-skills"), "modules": [{"status": "present"}]}

    runtime_modules.ensure_registered_runtime_modules = fake_ensure
    monkeypatch.setitem(sys.modules, "mn_sdk", sdk_package)
    monkeypatch.setitem(sys.modules, "mn_sdk.runtime_modules", runtime_modules)
    monkeypatch.setattr(otterdesk_blueprint_env, "ensure_local_sdk_importable", lambda start=None: None)

    result = bootstrap_blueprint_runtime(repo, packages=["mirrorneuron-blueprint-support-skill"])

    assert result["mode"] == "local_skill_sources"
    assert result["modules"] == [{"status": "present"}]
    assert calls[0][0] == [{"package": "mirrorneuron-blueprint-support-skill", "reasons": ["blueprint_runtime"]}]
    assert calls[0][1]["workspace_root"] == repo.parent
    assert calls[0][1]["auto_install"] is False
