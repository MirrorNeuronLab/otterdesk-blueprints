from pathlib import Path
import pytest
from workspace_paths import companion_workspace

ROOT = Path(__file__).resolve().parents[2]

@pytest.fixture(autouse=True)
def architecture_paths(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / 'achitecture_advisor/payloads'))
    workspace = companion_workspace(ROOT)
    for repo in ['mn-skills', 'mn-agents']:
        for path in (workspace/repo).glob('*/src'):
            monkeypatch.syspath_prepend(str(path))
