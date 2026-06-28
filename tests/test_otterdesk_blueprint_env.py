from __future__ import annotations

import os

from otterdesk_blueprint_env import load_blueprint_env, normalized_env, parse_env_line


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
