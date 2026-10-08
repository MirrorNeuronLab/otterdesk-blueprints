"""Local log-history scope without inspecting installation or startup files."""
import os
import platform

from mn_temporal_graph_skill import fingerprint


def require_mac():
    if platform.system() != "Darwin":
        raise ValueError("This co-worker requires macOS. Start it on a Mac.")


def host_epoch():
    require_mac()
    # Separate the logs-only history from earlier startup snapshots. This scope
    # identifies the host/user, not installation continuity across restores.
    return "mac-logs-" + fingerprint([platform.node(), os.getuid()])
