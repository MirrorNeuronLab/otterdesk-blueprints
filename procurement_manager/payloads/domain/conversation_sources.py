"""Select the completed procurement report for Job source conversations."""

import hashlib
from pathlib import Path

from mn_docs_to_markdown_skill import convert_documents


def publish_outputs(output_dir: Path, run_id: str):
    report = output_dir / "purchasing_manager_report.md"
    if report.is_symlink() or not report.is_file():
        raise ValueError("Conversation requires the complete saved procurement report")
    # Run identity names an isolated subject; it never selects a filesystem path.
    run_key = hashlib.sha256(run_id.encode("utf-8")).hexdigest()
    return convert_documents(
        [report], source_root=output_dir,
        output_root=output_dir / "context_sources" / "outputs" / run_key,
        max_bytes=4 * 1024 * 1024,
    )
