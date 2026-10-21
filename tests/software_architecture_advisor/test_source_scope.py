from native_test_support import block_context
import hashlib
import json

import pytest

from support import configuration


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


def test_capture_preserves_staged_git_index_for_checkpoint_verification(tmp_path, monkeypatch):
    import os
    import subprocess
    from domain.capture import capture
    from mn_graph_analysis_skill import GraphClient
    monkeypatch.setattr(GraphClient, "import_json", lambda *args: None)
    monkeypatch.setattr(GraphClient, "check", lambda *args: None)
    repository = tmp_path / "repo"
    repository.mkdir()
    source = repository / "a.py"
    source.write_text("def run():\n    return 1\n")
    def git(*args):
        return subprocess.run(["git", "-C", str(repository), *args], check=True, capture_output=True)
    git("init")
    git("add", ".")
    git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.test", "commit", "-m", "baseline")
    index = repository / ".git/index"
    original = index.read_bytes()
    stat = source.stat()
    os.utime(source, ns=(stat.st_atime_ns, stat.st_mtime_ns + 2_000_000_000))
    manifest = capture(repository, tmp_path / "snapshots", configuration())
    assert index.read_bytes() == original
    assert manifest["worktree_state"] == "clean worktree"
    assert manifest["git_anchor"] == git("rev-parse", "HEAD").stdout.decode().strip()


def test_unparsed_source_formats_and_explicit_extensions_remain_visible(tmp_path, monkeypatch):
    from domain.capture import capture
    from domain.static_analysis import build
    from mn_graph_analysis_skill import GraphClient
    monkeypatch.setattr(GraphClient,'import_json',lambda *args:None)
    monkeypatch.setattr(GraphClient,'check',lambda *args:None)
    repository=tmp_path/'repo with spaces';repository.mkdir()
    for name,text in {'main.clj':'(defn run [] 1)', 'source with spaces/資料.dsl':'module Main', 'README.md':'ignored',
                      'data.json':'{}'}.items():
        path=repository/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text)
    cfg=configuration();cfg['ingest']['additional_extensions']=['.dsl']
    run=tmp_path/'run';manifest=capture(repository,run/'evidence',cfg)
    assert set(manifest['sources'])=={'main.clj','source with spaces/資料.dsl'}
    assert manifest['coverage']['uncaptured_extensions']=={'.md':1,'.json':1}
    assert '.dsl' in manifest['ingest_config']['capture_extensions']
    (run/'snapshot.json').write_text(json.dumps(manifest))
    build(block_context({'run_dir':run,'config':cfg}))
    facts=json.loads((run/'data/static-code.json').read_text())
    score=json.loads((run/'data/architecture-score.json').read_text())
    assert facts['coverage']['status_counts']=={'unsupported':2}
    assert score['assessed_weight']==0 and score['score'] is None


@pytest.mark.parametrize('extra', [['.json'],['.md'],['../code'],[''],[1],'.lua'])
def test_additional_source_extensions_reject_documents_and_invalid_suffixes(extra):
    from domain.config import validate_config
    cfg=configuration();cfg['ingest']['additional_extensions']=extra
    with pytest.raises(ValueError,match='additional_extensions'):validate_config(cfg)
