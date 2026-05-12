from __future__ import annotations

from pathlib import Path

from .python_workflow_bundle import run_source_python_workflow_bundle_cli


def main(argv: list[str] | None = None) -> Path:
    return run_source_python_workflow_bundle_cli(argv)


if __name__ == "__main__":
    main()
