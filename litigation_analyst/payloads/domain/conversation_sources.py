"""Publish reviewed work product for the Job's Membrane conversation corpus.

The document skill owns conversion; the SDK owns ingestion and retrieval.
Only named report outputs are subjects, never the case audit or model receipts.
"""

from pathlib import Path

from mn_docs_to_markdown_skill import convert_documents


REPORTS = ("final_report.md", "evidence_appendix.md", "graph_appendix.md")


def publish_outputs(context):
    output = context.get("output_folder")
    if not output:
        return []
    run = Path(context["run_dir"])
    paths = [run / name for name in REPORTS]
    if any(path.is_symlink() or not path.is_file() for path in paths):
        raise ValueError("Conversation reports require complete regular output files")
    # A stable name follows the retained run identity; repeated publication uses
    # the skill's content-hash receipts without conversion or model calls.
    root = Path(output) / "context_sources" / "outputs" / run.name
    return convert_documents(paths, source_root=run, output_root=root,
                             max_bytes=4 * 1024 * 1024)
