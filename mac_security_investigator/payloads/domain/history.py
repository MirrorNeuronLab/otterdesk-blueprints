"""The domain evidence ledger is scoped by the Core-provided Job identity."""
import os
from pathlib import Path

from mn_temporal_graph_skill import EvidenceHistory, fingerprint

from .configuration import investigation_policy


def history(block, epoch):
    root = os.environ.get("MN_JOB_DATA_DIR")
    if not root or not block.job_id:
        raise ValueError("Core-provided Job identity and job-data directory are required")
    policy = investigation_policy()
    if not isinstance(epoch, str) or not epoch:
        raise ValueError("one captured host epoch is required")
    return EvidenceHistory(Path(root) / "state" / fingerprint(epoch) / "history.sqlite3", epoch,
        max_records=policy["max_records"], max_bytes=policy["max_scan_bytes"])
