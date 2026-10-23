"""Choose the finished customer report for source-grounded conversation.

The document skill owns complete conversion and receipts. Raw financial
documents and the JSON audit bundle are not additional conversation subjects.
"""

import hashlib

from mn_docs_to_markdown_skill import convert_documents


def publish_outputs(block):
    root = block.store.run_dir
    report = root / "financial_advisor_report.md"
    if report.is_symlink() or not report.is_file():
        raise ValueError("Conversation requires the complete saved financial report")
    run_key = hashlib.sha256(block.run_id.encode("utf-8")).hexdigest()
    return convert_documents(
        [report], source_root=root,
        output_root=block.output_directory / "context_sources" / "outputs" / run_key,
        max_bytes=4 * 1024 * 1024,
    )
