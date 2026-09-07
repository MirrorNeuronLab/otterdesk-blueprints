from pathlib import Path
import pytest
from workspace_paths import companion_workspace

@pytest.fixture(autouse=True)
def litigation_import_paths(monkeypatch):
    root = Path(__file__).resolve().parents[2]
    monkeypatch.syspath_prepend(str(root / "litigation_analyst/payloads"))
    workspace = companion_workspace(root)
    for repo in ["mn-skills", "mn-agents"]:
        for source in (workspace / repo).glob("*/src"):
            monkeypatch.syspath_prepend(str(source))
