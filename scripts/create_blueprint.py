"""Create a public no-op blueprint repository and register its catalog submodule."""

import argparse
import datetime
import json
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OWNER = "MirrorNeuronLab"
TEMPLATE = ROOT / "templates" / "blueprint"


class CreationError(Exception):
    """A setup failure with an actionable CLI message."""


def run(*command, cwd=ROOT):
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            text=True,
            capture_output=True,
            timeout=120,
        )
    except subprocess.TimeoutExpired as error:
        raise CreationError(
            f"Timed out running {command[0]}. Check its status before retrying."
        ) from error
    if result.returncode:
        detail = result.stderr.strip() or result.stdout.strip()
        raise CreationError(detail or f"{command[0]} failed.")
    return result.stdout.strip()


def validate_name(name):
    if not re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", name):
        raise CreationError(
            "Use 1–64 lowercase letters, numbers, underscores or hyphens, starting with a letter."
        )
    if name in {
        "con",
        "prn",
        "aux",
        "nul",
        *(f"com{i}" for i in range(1, 10)),
        *(f"lpt{i}" for i in range(1, 10)),
    }:
        raise CreationError("Choose a name that is also a valid folder on Windows.")


def preflight(name):
    for executable in ("git", "gh"):
        if shutil.which(executable) is None:
            raise CreationError(f"Install {executable} before creating a blueprint.")
    if Path(run("git", "rev-parse", "--show-toplevel")).resolve() != ROOT:
        raise CreationError(
            "Run this script from an otterdesk-blueprints Git checkout."
        )
    target = ROOT / name
    if target.exists() or target.is_symlink():
        raise CreationError(f"The blueprint folder already exists: {target}")
    try:
        inventory = json.loads((ROOT / "index.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise CreationError(
            "Couldn't read the catalog index.json. Fix it before creating a blueprint."
        ) from error
    if not isinstance(inventory, list) or not all(
        isinstance(item, str) for item in inventory
    ):
        raise CreationError(
            "The catalog index.json must be an ordered list of package paths."
        )
    if name in inventory:
        raise CreationError(f"The catalog already contains {name}.")
    for entry in inventory:
        bundle = (ROOT / entry).resolve()
        if not bundle.is_relative_to(ROOT):
            raise CreationError("A catalog package path escapes this checkout.")
        try:
            manifest = json.loads(
                (bundle / "manifest.json").read_text(encoding="utf-8")
            )
        except (OSError, ValueError) as error:
            raise CreationError(
                f"Couldn't read {entry}/manifest.json. Initialize catalog submodules before creating a blueprint."
            ) from error
        if manifest.get("id") == name:
            raise CreationError(f"Blueprint ID {name} already belongs to {entry}.")
    if run("git", "ls-files", "--", name):
        raise CreationError(f"The Git index already contains {name}.")
    metadata = Path(run("git", "rev-parse", "--git-path", f"modules/{name}"))
    if not metadata.is_absolute():
        metadata = ROOT / metadata
    if metadata.exists():
        raise CreationError(
            f"Submodule Git metadata already exists for {name}. Resolve it before retrying."
        )
    if run("git", "status", "--porcelain", "--", ".gitmodules"):
        raise CreationError(
            "Commit or resolve the existing .gitmodules changes before creating a blueprint."
        )
    if run("git", "ls-files", "--unmerged"):
        raise CreationError(
            "Resolve the catalog's Git conflicts before creating a blueprint."
        )
    git_directory = Path(run("git", "rev-parse", "--absolute-git-dir"))
    if any(
        (git_directory / state).exists()
        for state in (
            "MERGE_HEAD",
            "CHERRY_PICK_HEAD",
            "REVERT_HEAD",
            "rebase-merge",
            "rebase-apply",
        )
    ):
        raise CreationError(
            "Finish the catalog's in-progress Git operation before creating a blueprint."
        )
    if not TEMPLATE.is_dir():
        raise CreationError(f"The blueprint template is missing: {TEMPLATE}")
    try:
        run("gh", "auth", "status", "--hostname", "github.com")
    except CreationError as error:
        raise CreationError(
            "Log in first: gh auth login --hostname github.com --git-protocol ssh"
        ) from error


def render(destination, name):
    replacements = {
        "{{BLUEPRINT_ID}}": name,
        "{{BLUEPRINT_NAME}}": name.replace("_", " ").replace("-", " ").capitalize(),
        "{{JOB_NAME}}": name.replace("_", "-"),
        "{{YEAR}}": str(datetime.date.today().year),
        "{{OWNER}}": OWNER,
    }
    for source in sorted(TEMPLATE.rglob("*")):
        if source.is_symlink():
            raise CreationError(f"Template symlinks are not supported: {source}")
        if source.is_dir():
            continue
        target = destination / source.relative_to(TEMPLATE)
        target.parent.mkdir(parents=True, exist_ok=True)
        content = source.read_text(encoding="utf-8")
        for token, value in replacements.items():
            content = content.replace(token, value)
        if re.search(r"\{\{[A-Z_]+\}\}", content):
            raise CreationError(f"Unresolved template value in {source.name}.")
        if source.suffix == ".json":
            json.loads(content)
        target.write_text(content, encoding="utf-8")


def create(name):
    validate_name(name)
    preflight(name)
    target = ROOT / name
    repository = f"{OWNER}/mn-blueprint-{name}"
    https_url = f"https://github.com/{repository}.git"
    ssh_url = f"git@github.com:{repository}.git"
    remote_created = False
    try:
        with tempfile.TemporaryDirectory(prefix="otterdesk-blueprint-") as temporary:
            prepared = Path(temporary) / name
            render(prepared, name)
            run("git", "init", "--initial-branch=main", cwd=prepared)
            run("git", "add", "--all", cwd=prepared)
            run(
                "git",
                "commit",
                "--quiet",
                "-m",
                f"Initialize {name} blueprint",
                cwd=prepared,
            )
            run("git", "remote", "add", "origin", ssh_url, cwd=prepared)
            print(f"Creating public repository {repository}...", flush=True)
            # Creation rejects existing repositories; they are never reused or overwritten.
            run(
                "gh",
                "repo",
                "create",
                repository,
                "--public",
                "--description",
                f"OtterDesk blueprint: {name}. No-op starter.",
            )
            remote_created = True
            shutil.copytree(prepared, target)
        print("Pushing the starter to main...", flush=True)
        run("git", "push", "--set-upstream", "origin", "main", cwd=target)
        # Register the existing local repo: public consumers get HTTPS, while its
        # development origin stays SSH. No parent commit or catalog entry is made.
        run("git", "submodule", "add", "--branch", "main", https_url, name)
        run("git", "submodule", "absorbgitdirs", "--", name)
        run("git", "switch", "--no-track", "--create", "development", cwd=target)
    except (CreationError, OSError, ValueError) as error:
        if remote_created:
            print(
                f"Repository created: https://github.com/{repository}", file=sys.stderr
            )
            if target.exists():
                print(
                    f"Starter preserved at {target}. Check the push and submodule status before retrying.",
                    file=sys.stderr,
                )
        raise CreationError(str(error)) from error
    print(f"Created https://github.com/{repository}")
    print(f"Folder: {target}")
    print(
        "The submodule pin is staged. index.json and the catalog commit are unchanged."
    )
    print(
        f"Run: mn blueprint run {shlex.quote(str(target))} --detached --follow-seconds 0"
    )
    print(
        f'Commit and push the catalog: ./scripts/git-push-all.sh "Add {name} blueprint"'
    )


def main():
    if sys.version_info < (3, 9):
        print("Error: Python 3.9 or newer is required.", file=sys.stderr)
        return 1
    parser = argparse.ArgumentParser(
        prog="create_blueprint.sh",
        description="Create a public MirrorNeuronLab blueprint repo with a runnable no-op starter and pin it as a submodule.",
    )
    parser.add_argument(
        "-n", "--name", required=True, help="Blueprint folder and ID, e.g. my_blueprint"
    )
    arguments = parser.parse_args()
    try:
        create(arguments.name)
    except (CreationError, OSError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
