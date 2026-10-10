"""Publish completed review Markdown, excluding captured code and task audits."""

import hashlib
from pathlib import Path

from mn_docs_to_markdown_skill import convert_documents


def publish_outputs(context, *, section_paths=()):
    root = Path(context["run_dir"])
    reports = [root / "report.md", *(root / path for path in section_paths)]
    if any(report.is_symlink() or not report.is_file() for report in reports):
        raise ValueError("Conversation requires the complete published architecture review")
    # Standalone publication uses its run directory identity, like the workspace
    # projection. Deployed publication receives the SDK-provided physical run ID.
    run_id = str(context.get("run_id") or root.name)
    run_key = hashlib.sha256(run_id.encode("utf-8")).hexdigest()
    output = Path(context.get("output_folder") or root)
    return convert_documents(
        reports, source_root=root,
        output_root=output / "context_sources" / "outputs" / run_key,
        max_bytes=4 * 1024 * 1024,
    )
