from dataclasses import replace
import pytest


def test_frozen_case_file_graph_identity_tracks_raw_versions_and_renames(tmp_path):
    from domain.file_identity import capture_file_identities
    from domain.ingestion import CaseCorpus
    from domain.graph_projection import build_records
    from mn_graph_analysis_skill import compute_content_hash
    source = tmp_path / 'case-input'
    source.mkdir()
    document = source / 'evidence.md'
    document.write_text('Approval is unverified.\n')
    context = {'job_id': 'matter-fixture', 'config': {'investigation': {'access_scope': 'case'}}}

    def index(run):
        hashes = {p: compute_content_hash(p.read_bytes()) for p in source.iterdir()}
        repository_id, identities = capture_file_identities(source, tmp_path / 'runs' / run, context, hashes)
        nodes, edges = build_records(CaseCorpus(source, 'case').scan(), repository_id=repository_id, file_identities=identities)
        assert not edges and len(nodes) == 1
        return nodes[0]

    first = index('first')
    document.write_text('Approval was disputed.\n')
    edited = index('edited')
    assert edited['id'] == first['id']
    assert edited['properties']['node_id'] == first['properties']['node_id']
    assert edited['properties']['content_hash'] != first['properties']['content_hash']
    document.rename(source / 'renamed.md')
    moved = index('moved')
    assert moved['id'] == first['id']
    assert moved['properties']['previous_paths'] == ['evidence.md']
    assert moved['properties']['current_path'] == 'renamed.md'
    assert moved['properties']['source_id'] == 'case:renamed.md'
    assert index('reindex') == moved


def test_normalized_document_edit_preserves_entity_but_not_citation_version():
    from domain.models import CaseDocument
    from domain.graph_projection import build_records
    from mn_graph_analysis_skill import compute_content_hash
    document = CaseDocument('case:a.md', 'a.md', 'text/markdown', compute_content_hash(b'first'), 5, 'first', 'case')
    first = build_records([document])[0][0]
    edited = replace(document, text='second', content_sha256=compute_content_hash(b'second'), size_bytes=6)
    second = build_records([edited])[0][0]
    assert first['id'] == second['id']
    assert first['properties']['content_sha256'] != second['properties']['content_sha256']
    assert first['properties']['content_hash_basis'] == 'normalized_source'
    with pytest.raises(ValueError, match='identity is missing'):
        build_records([document], repository_id='matter', file_identities={})
