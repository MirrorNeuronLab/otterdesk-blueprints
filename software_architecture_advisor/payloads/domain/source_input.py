"""Validate the operator-selected repository source."""

from pathlib import Path
import re
from urllib.parse import urlsplit


def github_url(source):
    """Canonical repository-root URLs only; no credentials, ports, refs or redirects."""
    value = urlsplit(source)
    if (
        value.scheme != "https"
        or value.netloc.lower() != "github.com"
        or value.query
        or value.fragment
        or not re.fullmatch(
            r"/[A-Za-z0-9][A-Za-z0-9-]*/[A-Za-z0-9_.-]+/?", value.path
        )
    ):
        raise ValueError(
            "Use a repository URL such as https://github.com/owner/repository "
            "(no credentials, query, fragment, or /tree path)"
        )
    owner, repository = value.path.strip("/").split("/")
    repository = repository.removesuffix(".git")
    if repository in {"", ".", ".."}:
        raise ValueError("A GitHub repository name is required")
    return f"https://github.com/{owner}/{repository}.git"


def source_input(payload):
    folder, url = payload.get("input_folder"), payload.get("repository_url")
    # Setup forms represent an unselected optional source as an empty string.
    folder = None if folder == "" else folder
    url = None if url == "" else url
    if (folder is None) == (url is None):
        raise ValueError("Specify exactly one of input_folder or repository_url")
    if url is not None:
        if not isinstance(url, str) or len(url) > 2000:
            raise ValueError("repository_url must be an HTTPS GitHub repository URL")
        return github_url(url)
    if (
        not isinstance(folder, str)
        or not folder.strip()
        or "://" in folder
        or folder.startswith("git@")
    ):
        raise ValueError("input_folder must be a local directory path")
    path = Path(folder).expanduser().resolve(strict=True)
    if not path.is_dir():
        raise ValueError("input_folder must be a directory")
    return str(path)
