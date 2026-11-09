"""Exercise publication ordering and failures with isolated local Git remotes."""

import os
import shlex
import shutil
import subprocess
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "git-push-all.sh"
RELEASE_SCRIPT = SCRIPT.with_name("sync-development-to-main.sh")


@pytest.fixture
def git_env():
    return {
        **os.environ,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_AUTHOR_NAME": "Blueprint test",
        "GIT_AUTHOR_EMAIL": "blueprint@example.invalid",
        "GIT_COMMITTER_NAME": "Blueprint test",
        "GIT_COMMITTER_EMAIL": "blueprint@example.invalid",
        "GIT_ALLOW_PROTOCOL": "file",
    }


def git(path, *args, env):
    return subprocess.check_output(
        ["git", "-C", str(path), *args], env=env, text=True, stderr=subprocess.PIPE,
    ).strip()


def repository(path, env):
    path.mkdir()
    git(path, "init", "--initial-branch=main", env=env)
    (path / "README.md").write_text("Initial content\n")
    git(path, "add", ".", env=env)
    git(path, "commit", "-m", "Initial commit", env=env)
    remote = path.with_name(path.name + ".git")
    git(path.parent, "init", "--bare", "--initial-branch=main", str(remote), env=env)
    git(path, "remote", "add", "origin", str(remote), env=env)
    git(path, "push", "--set-upstream", "origin", "main", env=env)
    return remote


@pytest.fixture
def catalog(tmp_path, git_env):
    parent = tmp_path / "catalog with spaces"
    parent_remote = repository(parent, git_env)
    source = tmp_path / "blueprint source"
    child_remote = repository(source, git_env)
    git(parent, "submodule", "add", "--branch", "main", str(child_remote), "example blueprint", env=git_env)
    (parent / "scripts").mkdir()
    for script in (SCRIPT, RELEASE_SCRIPT):
        shutil.copy2(script, parent / "scripts" / script.name)
    git(parent, "add", ".", env=git_env)
    git(parent, "commit", "-m", "Add blueprint", env=git_env)
    git(parent, "push", env=git_env)
    child = parent / "example blueprint"
    for path in (parent, child):
        git(path, "switch", "-c", "development", env=git_env)
    return parent, parent_remote, child, child_remote


def publish(parent, env, message="Update all blueprints"):
    return subprocess.run(
        ["bash", str(parent / "scripts" / SCRIPT.name), message], cwd=parent.parent,
        env=env, text=True, capture_output=True,
    )


def promote(parent, env, *arguments):
    return subprocess.run(
        ["bash", str(parent / "scripts" / RELEASE_SCRIPT.name), *arguments],
        cwd=parent.parent, env=env, text=True, capture_output=True, timeout=30,
    )


def require_published_pin(parent_remote, child_remote, child_name, branch):
    hook = parent_remote / "hooks" / "pre-receive"
    hook.write_text(
        "#!/bin/sh\n"
        "while read -r old new ref; do\n"
        f"  pin=$(git rev-parse \"$new\":{shlex.quote(child_name)}) || exit 1\n"
        "  unset GIT_OBJECT_DIRECTORY GIT_ALTERNATE_OBJECT_DIRECTORIES\n"
        f"  git --git-dir={shlex.quote(str(child_remote))} "
        f"merge-base --is-ancestor \"$pin\" refs/heads/{branch} || exit 1\n"
        "done\n"
    )
    hook.chmod(0o755)


def test_publishes_child_before_parent_and_includes_plain_folders(catalog, git_env):
    parent, parent_remote, child, child_remote = catalog
    require_published_pin(parent_remote, child_remote, child.name, "development")
    production = git(parent_remote, "rev-parse", "main", env=git_env)
    production_pin = git(child_remote, "rev-parse", "main", env=git_env)
    (child / "README.md").unlink()
    (child / "new.txt").write_text("Child change\n")
    plain = parent / "plain blueprint"
    plain.mkdir()
    (plain / "manifest.json").write_text("{}\n")
    result = publish(parent, git_env, "Update $literal `message`")
    assert result.returncode == 0, result.stderr
    pin = git(child_remote, "rev-parse", "development", env=git_env)
    assert git(parent_remote, "rev-parse", "development:example blueprint", env=git_env) == pin
    assert git(parent_remote, "show", "development:plain blueprint/manifest.json", env=git_env) == "{}"
    assert git(child_remote, "log", "-1", "--format=%s", "development", env=git_env) == "Update $literal `message`"
    assert git(parent_remote, "rev-parse", "main", env=git_env) == production
    assert git(child_remote, "rev-parse", "main", env=git_env) == production_pin
    assert git(parent, "status", "--porcelain", env=git_env) == ""


def test_pushes_existing_commits_without_creating_empty_commits(catalog, git_env):
    parent, parent_remote, child, child_remote = catalog
    (child / "README.md").write_text("Already committed\n")
    git(child, "commit", "-am", "Pending child commit", env=git_env)
    child_head = git(child, "rev-parse", "HEAD", env=git_env)
    result = publish(parent, git_env)
    assert result.returncode == 0, result.stderr
    assert git(child_remote, "rev-parse", "development", env=git_env) == child_head
    assert git(parent_remote, "rev-parse", "development:example blueprint", env=git_env) == child_head
    parent_head = git(parent, "rev-parse", "HEAD", env=git_env)
    assert publish(parent, git_env).returncode == 0
    assert git(parent, "rev-parse", "HEAD", env=git_env) == parent_head


@pytest.mark.parametrize("checkout", ["--detach", "main"])
def test_requires_development_in_submodules_before_staging(catalog, git_env, checkout):
    parent, _, child, child_remote = catalog
    git(child, "checkout", checkout, env=git_env)
    child_head = git(child, "rev-parse", "HEAD", env=git_env)
    (child / "README.md").write_text("Changed while pinned\n")
    result = publish(parent, git_env)
    assert result.returncode != 0
    assert "to development before publishing" in result.stderr
    assert git(child, "diff", "--cached", "--name-only", env=git_env) == ""
    assert git(child_remote, "rev-parse", "main", env=git_env) == child_head


def test_missing_submodule_fails_before_staging_parent(catalog, git_env):
    parent, _, _, _ = catalog
    git(parent, "submodule", "deinit", "--force", "example blueprint", env=git_env)
    (parent / "README.md").write_text("Unstaged parent change\n")
    parent_head = git(parent, "rev-parse", "HEAD", env=git_env)
    result = publish(parent, git_env)
    assert result.returncode != 0
    assert "Initialize submodules first" in result.stderr
    assert git(parent, "diff", "--cached", "--name-only", env=git_env) == ""
    assert git(parent, "rev-parse", "HEAD", env=git_env) == parent_head


def test_rejected_child_push_does_not_commit_or_publish_parent(catalog, git_env):
    parent, parent_remote, child, child_remote = catalog
    hook = child_remote / "hooks" / "pre-receive"
    hook.write_text("#!/bin/sh\nexit 1\n")
    hook.chmod(0o755)
    (child / "README.md").write_text("Unpublished child change\n")
    (parent / "README.md").write_text("Unstaged parent change\n")
    parent_head = git(parent, "rev-parse", "HEAD", env=git_env)
    result = publish(parent, git_env)
    assert result.returncode != 0
    assert git(parent, "rev-parse", "HEAD", env=git_env) == parent_head
    assert git(parent_remote, "rev-parse", "main", env=git_env) == parent_head
    assert git(parent, "diff", "--cached", "--name-only", env=git_env) == ""


def test_conflicted_child_fails_before_committing_any_repository(catalog, git_env):
    parent, _, child, _ = catalog
    git(child, "checkout", "-b", "other", env=git_env)
    (child / "README.md").write_text("Other branch\n")
    git(child, "commit", "-am", "Other change", env=git_env)
    git(child, "checkout", "development", env=git_env)
    (child / "README.md").write_text("Development change\n")
    git(child, "commit", "-am", "Development change", env=git_env)
    subprocess.run(["git", "-C", str(child), "merge", "other"], env=git_env, capture_output=True)
    (parent / "README.md").write_text("Unstaged parent change\n")
    result = publish(parent, git_env)
    assert result.returncode != 0
    assert "in-progress Git operation" in result.stderr
    assert git(parent, "diff", "--cached", "--name-only", env=git_env) == ""


def test_promotes_nested_submodules_before_the_catalog(catalog, git_env):
    parent, parent_remote, child, child_remote = catalog
    nested_remote = repository(parent.parent / "nested source", git_env)
    nested = child / "nested blueprint"
    git(child, "submodule", "add", str(nested_remote), nested.name, env=git_env)
    git(nested, "switch", "-c", "development", env=git_env)
    (nested / "README.md").write_text("Reviewed nested change\n")
    git(nested, "commit", "-am", "Update nested blueprint", env=git_env)
    git(child, "commit", "-am", "Pin nested blueprint", env=git_env)
    git(parent, "commit", "-am", "Pin blueprint for release", env=git_env)
    require_published_pin(child_remote, nested_remote, nested.name, "main")
    require_published_pin(parent_remote, child_remote, child.name, "main")
    checkouts = [(parent, parent_remote), (child, child_remote), (nested, nested_remote)]
    before = [git(remote, "rev-parse", "main", env=git_env) for _, remote in checkouts]

    preview = promote(parent, git_env, "--dry-run")
    assert preview.returncode == 0, preview.stderr
    for (checkout, remote), commit in zip(checkouts, before):
        assert git(checkout, "rev-parse", "main", env=git_env) == commit
        assert git(remote, "rev-parse", "main", env=git_env) == commit

    result = promote(parent, git_env)
    assert result.returncode == 0, result.stderr
    for checkout, remote in checkouts:
        assert git(checkout, "branch", "--show-current", env=git_env) == "development"
        commit = git(checkout, "rev-parse", "HEAD", env=git_env)
        assert git(checkout, "rev-parse", "main", env=git_env) == commit
        assert git(remote, "rev-parse", "main", env=git_env) == commit
        assert git(checkout, "status", "--porcelain", env=git_env) == ""
    assert promote(parent, git_env).returncode == 0


@pytest.mark.parametrize("commit_child", [False, True])
def test_promotion_rejects_dirty_or_unpinned_changes(catalog, git_env, commit_child):
    parent, parent_remote, child, child_remote = catalog
    production = git(parent_remote, "rev-parse", "main", env=git_env)
    production_pin = git(child_remote, "rev-parse", "main", env=git_env)
    (child / "README.md").write_text("Work in progress\n")
    if commit_child:
        git(child, "commit", "-am", "Unpinned child commit", env=git_env)
    result = promote(parent, git_env)
    assert result.returncode != 0
    expected_error = "updated submodule pin" if commit_child else "Commit or stash changes"
    assert expected_error in result.stderr
    assert git(parent_remote, "rev-parse", "main", env=git_env) == production
    assert git(child_remote, "rev-parse", "main", env=git_env) == production_pin


def test_promotion_checks_diverged_remote_main_before_any_push(catalog, git_env):
    parent, parent_remote, child, child_remote = catalog
    other = parent.parent / "production checkout"
    git(parent.parent, "clone", str(parent_remote), str(other), env=git_env)
    (other / "README.md").write_text("Independent production fix\n")
    git(other, "commit", "-am", "Production fix", env=git_env)
    git(other, "push", env=git_env)
    production = git(other, "rev-parse", "HEAD", env=git_env)
    production_pin = git(child_remote, "rev-parse", "main", env=git_env)
    (child / "README.md").write_text("Development release\n")
    git(child, "commit", "-am", "Review child changes", env=git_env)
    git(parent, "commit", "-am", "Pin blueprint for release", env=git_env)

    result = promote(parent, git_env)
    assert result.returncode != 0
    assert "Couldn't fast-forward origin/main" in result.stderr
    assert git(parent_remote, "rev-parse", "main", env=git_env) == production
    assert git(child_remote, "rev-parse", "main", env=git_env) == production_pin


def test_promotion_can_retry_after_a_rejected_catalog_push(catalog, git_env):
    parent, parent_remote, child, child_remote = catalog
    production = git(parent_remote, "rev-parse", "main", env=git_env)
    (child / "README.md").write_text("Reviewed change\n")
    git(child, "commit", "-am", "Review child changes", env=git_env)
    git(parent, "commit", "-am", "Pin blueprint for release", env=git_env)
    hook = parent_remote / "hooks" / "pre-receive"
    hook.write_text("#!/bin/sh\nexit 1\n")
    hook.chmod(0o755)

    assert promote(parent, git_env).returncode != 0
    assert git(child_remote, "rev-parse", "main", env=git_env) == git(child, "rev-parse", "HEAD", env=git_env)
    assert git(parent_remote, "rev-parse", "main", env=git_env) == production
    assert git(parent, "rev-parse", "main", env=git_env) == production
    hook.unlink()
    result = promote(parent, git_env)
    assert result.returncode == 0, result.stderr
    assert git(parent_remote, "rev-parse", "main", env=git_env) == git(parent, "rev-parse", "HEAD", env=git_env)
