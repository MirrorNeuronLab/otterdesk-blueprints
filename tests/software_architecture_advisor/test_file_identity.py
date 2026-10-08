import json
from pathlib import Path
import shutil

import pytest

from support import configuration


def test_capture_file_identity_survives_edit_rename_and_graph_evolution(tmp_path, monkeypatch):
    from domain.capture import capture
    from domain.lazy import LayerManager
    from domain.records import Records
    from mn_graph_analysis_skill import GraphClient
    monkeypatch.setattr(GraphClient, 'import_json', lambda *args: None)
    monkeypatch.setattr(GraphClient, 'check', lambda *args: None)
    repo, workspace = tmp_path / 'checkout', tmp_path / 'index'
    repo.mkdir()
    (repo / 'a.py').write_text('def run():\n    return 1\n')
    (repo / 'b.ts').write_text('export const value = 1;\n')
    config = configuration()
    config['ingest']['repository_id'] = 'fixture/architecture'

    def index():
        manifest = capture(repo, workspace, config)
        directory = workspace / 'snapshots' / manifest['id']
        nodes = json.loads((directory / 'nodes.json').read_text())
        files = {n['properties']['current_path']: n for n in nodes if n['kind'] == 'File'}
        assert len(files) == len(manifest['sources']) == 2
        assert len({n['id'] for n in nodes}) == len(nodes)
        return directory, files

    _, first = index()
    (repo / 'a.py').write_text('import os\ndef run():\n    return 2\n')
    _, edited = index()
    assert first['a.py']['id'] == edited['a.py']['id']
    assert first['a.py']['properties']['node_id'] == edited['a.py']['properties']['node_id']
    assert first['a.py']['properties']['content_hash'] != edited['a.py']['properties']['content_hash']
    (repo / 'src').mkdir()
    (repo / 'a.py').rename(repo / 'src/core.py')
    directory, moved = index()
    assert moved['src/core.py']['id'] == first['a.py']['id']
    assert moved['src/core.py']['properties']['previous_paths'] == ['a.py']
    assert index()[1] == moved
    known = {n['id']: n for n in json.loads((directory / 'nodes.json').read_text())}
    collector = Records(json.loads((directory / 'sources.json').read_text()), 'dependencies', '*', known)
    file_key = moved['src/core.py']['properties']['key']
    collector.node(file_key, 'File')
    with pytest.raises(ValueError, match='captured persistent file'):
        collector.node('file:src/core.py', 'File')
    with pytest.raises(ValueError, match='frozen file identity'):
        collector.node(file_key, 'File', content_hash='0' * 64)
    witness = collector.cite('src/core.py', 1)
    module_key = next(n['properties']['key'] for n in known.values()
                      if n['kind'] == 'Module' and n['properties']['path'] == 'src/core.py')
    collector.edge(module_key, file_key, 'DECLARED_IN', witness)
    assert collector.finish()['edges'][0]['dst'] == moved['src/core.py']['id']
    # Publishing derived graph generations must retain base files and links.
    manager = LayerManager(directory, config)
    manager._publish({})
    generation = manager.current()
    nodes = json.loads((Path(generation['directory']) / 'nodes.json').read_text())
    assert {n['id'] for n in nodes if n['kind'] == 'File'} == {n['id'] for n in moved.values()}
    assert json.loads((Path(generation['directory']) / 'edges.json').read_text())
    # A fresh checkout of the same logical repository has the same initial IDs.
    other = tmp_path / 'other-checkout'
    shutil.copytree(repo, other)
    fresh = capture(other, tmp_path / 'other-index', config)
    assert fresh['repository_id'] == 'fixture/architecture'
    fresh_nodes = json.loads((tmp_path / 'other-index/snapshots' / fresh['id'] / 'nodes.json').read_text())
    assert next(n for n in fresh_nodes if n.get('properties', {}).get('path') == 'b.ts')['id'] == first['b.ts']['id']


def test_failed_graph_publication_preserves_previous_identity_baseline(tmp_path, monkeypatch):
    from domain.capture import capture
    from mn_graph_analysis_skill import GraphClient
    monkeypatch.setattr(GraphClient, 'import_json', lambda *args: None)
    monkeypatch.setattr(GraphClient, 'check', lambda *args: None)
    repo, workspace = tmp_path / 'repo', tmp_path / 'index'
    repo.mkdir()
    (repo / 'a.ts').write_text('hello')
    first = capture(repo, workspace, configuration())
    (repo / 'a.ts').rename(repo / 'b.ts')
    def fail(*args):
        raise RuntimeError('import failed')
    monkeypatch.setattr(GraphClient, 'import_json', fail)
    with pytest.raises(RuntimeError, match='import failed'):
        capture(repo, workspace, configuration())
    assert (workspace / 'CURRENT').read_text() == first['id']
