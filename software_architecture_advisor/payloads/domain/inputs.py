"""Resolve local folders or public HTTPS GitHub repositories into frozen inputs."""
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time
from urllib.parse import urlsplit

from .ingest import snapshot_repository
from .events import emit

DEFAULT_GOAL = "Inspect the software architecture, identify the most actionable boundary or coupling problem, and check counter-evidence before recommending a change."


def github_url(source):
    """Canonical repository-root URLs only; no credentials, ports, refs or redirects."""
    value = urlsplit(source)
    if (value.scheme != "https" or value.netloc.lower() != "github.com" or value.query or value.fragment
            or not re.fullmatch(r"/[A-Za-z0-9][A-Za-z0-9-]*/[A-Za-z0-9_.-]+/?", value.path)):
        raise ValueError("Use a repository URL such as https://github.com/owner/repository (no credentials, query, fragment, or /tree path)")
    owner, repository = value.path.strip("/").split("/")
    repository = repository.removesuffix(".git")
    if repository in {"", ".", ".."}:
        raise ValueError("A GitHub repository name is required")
    return f"https://github.com/{owner}/{repository}.git"


def validate_source(source):
    if source is None:
        return
    if not isinstance(source, (str, Path)) or not str(source).strip() or len(str(source)) > 2000:
        raise ValueError("source must be a folder path or HTTPS GitHub repository URL")
    value = str(source)
    if "://" in value or value.startswith("git@"):
        github_url(value)


def resolve_source(source, workspace, config):
    validate_source(source)
    if source is None:
        raise ValueError("Specify repository_url or input_folder")
    value = str(source)
    if "://" not in value and not value.startswith("git@"):
        path = Path(value).expanduser().resolve(strict=True)
        if not path.is_dir():
            raise ValueError("Source must be a directory")
        return path, {"kind": "folder", "location": str(path)}, False
    url = github_url(value)
    downloads = Path(workspace).resolve() / "repositories"
    downloads.mkdir(parents=True, exist_ok=True)
    destination = Path(tempfile.mkdtemp(prefix="github-", dir=downloads))
    # Keep each checkout: snapshots and lazy Git history must retain their captured objects.
    depth = config["ingest"]["git_commits"]
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull,
               GIT_TERMINAL_PROMPT="0", GIT_ASKPASS="/bin/false")
    command = ["git", "-c", "core.hooksPath=" + os.devnull, "-c", "core.fsmonitor=false",
               "-c", "protocol.allow=never", "-c", "protocol.https.allow=always",
               "-c", "http.followRedirects=false", "-c", "http.sslVerify=true",
               "clone", "--quiet", "--template=", "--no-recurse-submodules", "--single-branch", "--no-tags",
               "--depth", str(depth), "--", url, str(destination)]
    began = time.perf_counter()
    try:
        subprocess.run(command, check=True, capture_output=True, text=True, env=env,
                       timeout=config.get("source", {}).get("clone_timeout_seconds", 180))
    except (OSError, subprocess.SubprocessError) as exc:
        shutil.rmtree(destination)
        detail = (exc.stderr or "")[-1200:] if isinstance(exc, subprocess.CalledProcessError) else str(exc)
        raise RuntimeError(f"GitHub download failed; check the public repository URL and network access. {detail}") from exc
    return destination, {"kind": "github", "location": url, "checkout": str(destination),
                         "branch": "remote default branch", "history_depth": depth,
                         "submodules": "not fetched", "git_lfs": "pointer files only; objects not fetched",
                         "download_ms": round((time.perf_counter()-began)*1000, 2)}, True


def ingest_source(source, workspace, config, facts_path=None, progress=None):
    if progress:
        progress("downloading" if source is not None and "://" in str(source) else "resolving_source")
    emit("source.acquisition.started")
    try:
        path, info, downloaded = resolve_source(source, workspace, config)
    except Exception as exc:
        emit("source.acquisition.failed", error=f"{type(exc).__name__}: {exc}")
        raise
    emit("source.acquisition.completed", input=info)
    if progress:
        progress("capturing_sources")
    emit("snapshot.capture.started", repository=str(path), facts_path=str(facts_path) if facts_path else None)
    try:
        manifest = snapshot_repository(path, workspace, config, facts_path, input_info=info)
        emit("snapshot.capture.completed", snapshot=manifest["id"], input=manifest["input"], metrics=manifest["metrics"],
             source_files=manifest["coverage"]["source_files"], modules=len(manifest["modules"]))
        if progress:
            progress(f"Captured {manifest['coverage']['source_files']} files and {len(manifest['modules'])} modules")
        return manifest
    except Exception as exc:
        emit("snapshot.capture.failed", error=f"{type(exc).__name__}: {exc}")
        if downloaded:
            shutil.rmtree(path)
            emit("source.checkout.removed", path=str(path), reason="capture failed")
        raise
