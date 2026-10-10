"""Choose the saved research brief as a Job conversation source.

The document skill owns conversion and receipts. The SDK and Membrane own
scoped publication, indexing and exact source retrieval; ledgers and runtime
traces are not additional conversation subjects.
"""

import hashlib
from pathlib import Path

from mn_docs_to_markdown_skill import convert_documents


def publish_outputs(output_dir: Path, run_id: str):
    report = output_dir / "research_brief.md"
    if report.is_symlink() or not report.is_file():
        raise ValueError("Conversation requires the complete saved research brief")
    # Hashing the retained run identity keeps retries stable and prevents an
    # identity from selecting a filesystem path.
    run_key = hashlib.sha256(run_id.encode("utf-8")).hexdigest()
    return convert_documents(
        [report], source_root=output_dir,
        output_root=output_dir / "context_sources" / "outputs" / run_key,
        max_bytes=4 * 1024 * 1024,
    )
