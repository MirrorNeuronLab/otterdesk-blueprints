"""Bounded, user-initiated unified-log collection without OS file inspection."""
from datetime import datetime, timezone
import os


def now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def acquire_mac(scan_id, limits):
    from .discovery import host_epoch
    from .system_logs import acquire_logs
    epoch = host_epoch()
    start = now()
    source = acquire_logs(epoch, limits)
    return {"host_epoch_id": epoch, "scan_id": scan_id,
            "acquisition": {"earliest": start, "latest": now()}, "sources": [source],
            "self_activity": {"pid": os.getpid(), "kind": "mac_log_acquisition"}}
