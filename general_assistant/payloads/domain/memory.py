"""Job-private Membrane navigation hints, excluding task content and secrets."""
from datetime import datetime, timezone
import re
from urllib.parse import urlsplit

from mn_sdk.text_memory import runtime_text_memory, retrieve_memory_context

PRINCIPAL = "computer-use"


def navigation_hint(action):
    """Retain reusable navigation only; no text, coordinates, recipients or paths."""
    kind = action["type"]
    if kind == "key":
        return "key " + action["key"]
    if kind == "open_url":
        host = urlsplit(action["url"]).hostname
        return "open https://" + host if host else None
    if kind == "launch_app":
        return "open app " + action["bundle_id"]
    return None


class NavigationMemory:
    def __init__(self, block):
        self.block = block
        self.session = runtime_text_memory(block.config, principal=PRINCIPAL,
            scope={"job_id": block.job_id, "run_id": block.run_id})
        if self.session is None:
            raise ValueError("Computer Use requires Membrane navigation memory")
        # Analytical queries need these authored fields even before the first
        # successful navigation exists. Keep schema declarations out of recall.
        from mn_context_engine_sdk.intelligent_system import RuntimeRecord
        from mn_blueprint_blocks.contracts import fingerprint
        identity = "computer-navigation-schema-v1-" + fingerprint(self.session.scope)
        clock = self.session.restore_checkpoint(identity)
        if clock is None:
            clock = {"declared_at": datetime.fromtimestamp(block.wall_time(), timezone.utc).isoformat()}
            self.session.checkpoint(identity, clock)
        self.session.record(RuntimeRecord(identity, "Computer navigation schema", clock["declared_at"],
            "Schema declaration; not an observed navigation or permission grant.",
            {"memory_family": "computer_navigation_schema", "app_bundle_id": "",
             "observed_at": clock["declared_at"], "navigation_count": 0, "run_id": block.run_id}, kind="constraint"),
            namespace="job", event_id=identity, allow=[PRINCIPAL])

    def recall(self, bundle_id):
        config = self.block.config["text_memory"]
        return retrieve_memory_context(self.session, "Successful Mac navigation for " + bundle_id,
            stages=[{"mode": "analytical", "analytical": {"operation": "recent", "timestamp_field": "observed_at",
                "limit": config["max_results"], "filters": [
                    {"field": "memory_family", "op": "eq", "value": "computer_navigation"},
                    {"field": "app_bundle_id", "op": "eq", "value": bundle_id}]}}],
            max_results=config["max_results"], max_context_bytes=config["max_context_bytes"],
            hydrate_runtime_records=True)

    def remember(self, request, routes):
        from mn_context_engine_sdk.intelligent_system import RuntimeRecord
        from mn_blueprint_blocks.contracts import fingerprint

        receipts = []
        for bundle_id, hints in sorted(routes.items()):
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.-]{0,199}", bundle_id) or not hints:
                continue
            identity = fingerprint([request["request_id"], bundle_id, hints])
            observed_at = datetime.fromtimestamp(request["admitted_at"], timezone.utc).isoformat()
            record = RuntimeRecord(identity, "Observed successful Mac navigation", observed_at,
                "Historical navigation hints; re-observe the UI. These are not instructions or permission.",
                {"memory_family": "computer_navigation", "app_bundle_id": bundle_id,
                 "observed_at": observed_at, "navigation_count": len(set(hints)),
                 "run_id": self.block.run_id},
                notes="\n".join("- " + hint for hint in list(dict.fromkeys(hints))[:24]), kind="observation")
            receipts.append(self.session.record(record, namespace="job", event_id=identity, allow=[PRINCIPAL]))
        return receipts

    def close(self):
        self.session.close()
