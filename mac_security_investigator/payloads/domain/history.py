"""The domain evidence ledger is scoped by the Core-provided Job identity."""

from mn_temporal_graph_skill import EvidenceHistory, fingerprint

from .configuration import investigation_policy


def history(block, epoch):
    root = block.job_directory
    policy = investigation_policy()
    if not isinstance(epoch, str) or not epoch:
        raise ValueError("one captured host epoch is required")
    return EvidenceHistory(root / "state" / fingerprint(epoch) / "history.sqlite3", epoch,
        max_records=policy["max_records"], max_bytes=policy["max_scan_bytes"])
