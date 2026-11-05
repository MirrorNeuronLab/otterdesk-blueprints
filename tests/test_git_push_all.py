"""Exercise publication ordering and failures with isolated local Git remotes."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "git-push-all.sh"


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
    shutil.copy2(SCRIPT, parent / SCRIPT.name)
    git(parent, "add", ".", env=git_env)
    git(parent, "commit", "-m", "Add blueprint", env=git_env)
    git(parent, "push", env=git_env)
    return parent, parent_remote, parent / "example blueprint", child_remote


def publish(parent, env, message="Update all blueprints"):
    return subprocess.run(
        ["bash", str(parent / SCRIPT.name), message], cwd=parent.parent,
        env=env, text=True, capture_output=True,
    )


def test_publishes_child_before_parent_and_includes_plain_folders(catalog, git_env):
    parent, parent_remote, child, child_remote = catalog
    # Reject a parent update unless its referenced child commit is already public.
    hook = parent_remote / "hooks" / "pre-receive"
    hook.write_text(
        "#!/bin/sh\n"
        "while read old new ref; do\n"
        "  pin=$(git ls-tree \"$new\" -- 'example blueprint' | cut -f1 | awk '{print $3}')\n"
        "  unset GIT_OBJECT_DIRECTORY GIT_ALTERNATE_OBJECT_DIRECTORIES\n"
        f"  git --git-dir='{child_remote}' cat-file -e \"$pin^{{commit}}\" || exit 1\n"
        "done\n"
    )
    hook.chmod(0o755)
    (child / "README.md").unlink()
    (child / "new.txt").write_text("Child change\n")
    plain = parent / "plain blueprint"
    plain.mkdir()
    (plain / "manifest.json").write_text("{}\n")
    result = publish(parent, git_env, "Update $literal `message`")
    assert result.returncode == 0, result.stderr
    pin = git(child_remote, "rev-parse", "main", env=git_env)
    assert git(parent_remote, "rev-parse", "main:example blueprint", env=git_env) == pin
    assert git(parent_remote, "show", "main:plain blueprint/manifest.json", env=git_env) == "{}"
    assert git(child_remote, "log", "-1", "--format=%s", "main", env=git_env) == "Update $literal `message`"
    assert git(parent, "status", "--porcelain", env=git_env) == ""


def test_pushes_existing_commits_without_creating_empty_commits(catalog, git_env):
    parent, parent_remote, child, child_remote = catalog
    (child / "README.md").write_text("Already committed\n")
    git(child, "commit", "-am", "Pending child commit", env=git_env)
    child_head = git(child, "rev-parse", "HEAD", env=git_env)
    result = publish(parent, git_env)
    assert result.returncode == 0, result.stderr
    assert git(child_remote, "rev-parse", "main", env=git_env) == child_head
    assert git(parent_remote, "rev-parse", "main:example blueprint", env=git_env) == child_head
    parent_head = git(parent, "rev-parse", "HEAD", env=git_env)
    assert publish(parent, git_env).returncode == 0
    assert git(parent, "rev-parse", "HEAD", env=git_env) == parent_head


def test_can_commit_and_push_from_a_detached_submodule_pin(catalog, git_env):
    parent, _, child, child_remote = catalog
    git(child, "checkout", "--detach", env=git_env)
    (child / "README.md").write_text("Changed while pinned\n")
    result = publish(parent, git_env)
    assert result.returncode == 0, result.stderr
    assert git(child_remote, "rev-parse", "main", env=git_env) == git(child, "rev-parse", "HEAD", env=git_env)


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
    git(child, "checkout", "main", env=git_env)
    (child / "README.md").write_text("Main branch\n")
    git(child, "commit", "-am", "Main change", env=git_env)
    subprocess.run(["git", "-C", str(child), "merge", "other"], env=git_env, capture_output=True)
    (parent / "README.md").write_text("Unstaged parent change\n")
    result = publish(parent, git_env)
    assert result.returncode != 0
    assert "in-progress Git operation" in result.stderr
    assert git(parent, "diff", "--cached", "--name-only", env=git_env) == ""
