"""VC publication policy for processed Markdown input and output sources."""

from pathlib import Path

from mn_docs_to_markdown_skill import SUPPORTED_SUFFIXES, convert_documents
from mn_sdk.blueprint_support import write_json
from mn_sdk.source_query import source_text_query


def index_output_artifacts(ctx, output_files):
    source_folder = Path(ctx['output_folder']) / 'context_sources'
    paths = sorted({Path(item['path']) for item in output_files
                    if Path(item['path']).suffix.lower() in SUPPORTED_SUFFIXES
                    and not Path(item['path']).resolve().is_relative_to(source_folder.resolve())})
    root = Path(ctx['output_folder']) / 'context_sources' / 'outputs'
    records = convert_documents(paths, source_root=ctx['output_folder'], output_root=root)
    sources = source_text_query(ctx['config'], principal='vc-output-artifacts')
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
    inventory = [{'path': str(Path(r['markdown_path']).relative_to(ctx['output_folder'])),
                  'sha256': r['markdown_sha256'], 'original_ref': r['source_ref']}
                 for r in records]
    catalog_path = root.parent / 'outputs.json'
    write_json(catalog_path, {'files': inventory, 'catalog': catalog, 'receipts': receipts})
    return [*output_files,
            *[{'kind': 'output_source_markdown', 'path': r['markdown_path']} for r in records],
            {'kind': 'output_source_catalog', 'path': str(catalog_path)}]
