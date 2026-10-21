"""VC publication policy for processed Markdown input and output sources."""

from pathlib import Path

from mn_docs_to_markdown_skill import SUPPORTED_SUFFIXES, convert_documents
from mn_sdk.blueprint_support import write_json
from mn_sdk.source_query import source_text_query


def index_output_artifacts(block, output_files):
    source_folder = block.store.path('context_sources')
    paths = sorted({block.store.path(item['path']) for item in output_files
                    if Path(item['path']).suffix.lower() in SUPPORTED_SUFFIXES
                    and not block.store.path(item['path']).is_relative_to(source_folder)})
    root = source_folder / 'outputs'
    records = convert_documents(paths, source_root=block.store.run_dir, output_root=root)
    sources = source_text_query(block.config, principal='vc-output-artifacts',
        scope={'job_id': block.job_id, 'run_id': block.run_id})
    receipts, catalog = [], None
    try:
        if sources is not None:
            receipts = sources.ingest([{
                'source_ref': 'outputs/' + r['markdown_ref'], 'text': r['markdown'],
                'aliases': [r['source_ref']],
                'allow': ['vc-output-artifacts', 'vc-company-analysis'],
                'upstream': [{'artifact_role': 'output', 'original_sha256': r['original_sha256'],
                              'markdown_sha256': r['markdown_sha256'],
                              'extraction_method': r['extraction_method']}],
            } for r in records])
            catalog = sources.catalog()
    finally:
        if sources is not None:
            sources.close()
    inventory = [{'path': str(Path(r['markdown_path']).relative_to(block.store.run_dir)),
                  'sha256': r['markdown_sha256'], 'original_ref': r['source_ref']}
                 for r in records]
    catalog_path = root.parent / 'outputs.json'
    write_json(catalog_path, {'files': inventory, 'catalog': catalog, 'receipts': receipts})
    return [*output_files,
            *[{'kind': 'output_source_markdown', 'path': str(Path(r['markdown_path']).relative_to(block.store.run_dir))} for r in records],
            {'kind': 'output_source_catalog', 'path': str(catalog_path.relative_to(block.store.run_dir))}]
