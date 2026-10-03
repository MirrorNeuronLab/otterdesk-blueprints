import hashlib
import json

import pytest

from support import ROOT, configuration


def test_capture_code_only_and_beam_dependency_evidence(tmp_path, monkeypatch, architecture_paths):
    from domain.capture import capture
    from domain.static_layers import Project, dependencies
    from domain.records import Records
    from domain.structural_analysis import analyze_dependencies
    from domain.ingest import logical_id
    from mn_graph_analysis_skill import GraphClient

    monkeypatch.setattr(GraphClient, "import_json", lambda *args: None)
    monkeypatch.setattr(GraphClient, "check", lambda *args: None)
    repository = tmp_path / "repo"
    files = {
        "lib/app.ex": "defmodule App do\n alias Worker, as: W\n def run, do: W.run()\nend\n",
        "lib/worker.ex": "defmodule Worker do\n def run, do: :ok\nend\n",
        "mix.exs": "defmodule Project.MixProject do\n use Mix.Project\nend\n",
        "config/config.exs": "import Config\nconfig :app, enabled: true\n",
        "README.md": "IGNORED documentation",
        "data/sample.json": '{"value": "IGNORED sample"}',
        "data/sample.csv": "IGNORED sample",
        "docs/tutorial.ex": "defmodule Ignored.Doc do\nend\n",
        "examples/demo.ex": "defmodule Ignored.Example do\nend\n",
        "test/fixtures/sample.exs": "defmodule Ignored.Fixture do\nend\n",
        "deps/external.ex": "defmodule Ignored.Dependency do\nend\n",
        "_build/generated.ex": "defmodule Ignored.Build do\nend\n",
    }
    for name, text in files.items():
        path = repository / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    manifest = capture(repository, tmp_path / "snapshots", configuration())
    directory = tmp_path / "snapshots" / "snapshots" / manifest["id"]
    sources = json.loads((directory / "sources.json").read_text())
    assert set(sources) == {"lib/app.ex", "lib/worker.ex", "mix.exs", "config/config.exs"}
    assert not any("IGNORED" in value["text"] for value in sources.values())
    assert manifest["coverage"]["source_scope"] == "code_only"
    assert manifest["coverage"]["skipped"]["non_code_files"] == 3
    assert set(manifest["modules"]) == {"App", "Worker", "Project.MixProject"}
    nodes = json.loads((directory / "nodes.json").read_text())
    records = Records(sources, "dependencies", "*", {node["id"]: node for node in nodes})
    dependencies(records, Project(sources, manifest["modules"]))
    graph = records.finish()
    baseline, _ = analyze_dependencies(manifest, nodes, graph["edges"], graph["evidence"], max_dsm_modules=300)
    assert [(edge["source"], edge["target"]) for edge in baseline["dependencies"]] == [("App", "Worker")]
    assert all(edge["src"] == logical_id("module:App") and edge["dst"] == logical_id("module:Worker") for edge in graph["edges"])
    for evidence in graph["evidence"].values():
        assert evidence["sha256"] == hashlib.sha256(files[evidence["path"]].encode()).hexdigest()
        lines = files[evidence["path"]].splitlines(keepends=True)
        assert evidence["text"] == "".join(lines[evidence["line_start"] - 1:evidence["line_end"]])


def test_document_only_repository_is_rejected(tmp_path, architecture_paths):
    from domain.capture import capture
    repository = tmp_path / "repo"
    repository.mkdir()
    (repository / "README.md").write_text("Documentation only")
    with pytest.raises(ValueError, match="No supported code"):
        capture(repository, tmp_path / "outputs", configuration())
