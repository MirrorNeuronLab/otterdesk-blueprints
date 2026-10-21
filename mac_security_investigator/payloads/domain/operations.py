"""Native block operations for bounded local evidence and temporal policy."""
from mn_sdk.agent_events import report_activity

from .acquisition import acquire_mac
from .configuration import BLUEPRINT_ID, investigation_policy
from .history import history
from .patterns import analyze


def capture(block, inputs):
    report_activity("Collecting Mac security evidence", owner_blueprint=BLUEPRINT_ID, step_id=block.step_id, run_dir=block.store.run_dir)
    store = block.store
    scans = store.read_path("scan_batch.json") if store.path("scan_batch.json").exists() else [
        acquire_mac(block.run_id, investigation_policy())]
    if not scans or any(scan["host_epoch_id"] != scans[0]["host_epoch_id"] for scan in scans):
        raise ValueError("all scans must belong to one local host epoch")
    reference = store.commit("scan_batch.json", scans, kind="mac_security_scans")
    return {"scan_count": len(scans), "scan_batch": reference.to_dict()}


def reconcile(block, inputs):
    report_activity("Reconciling temporal security history", owner_blueprint=BLUEPRINT_ID, step_id=block.step_id, run_dir=block.store.run_dir)
    scans = block.store.read(inputs["previous"]["scan_batch"])
    if not scans or any(scan["host_epoch_id"] != scans[0]["host_epoch_id"] for scan in scans):
        raise ValueError("all scans must belong to one local host epoch")
    ledger = history(block, scans[0]["host_epoch_id"])
    try:
        receipts = [ledger.ingest_scan(scan) for scan in scans]
        # A later run cannot advance this run's knowledge cutoff.
        pinned = block.store.read_path("graph_revision.json") if block.store.path("graph_revision.json").exists() else {
            "revision": ledger.revision, "receipts": receipts, "host_epoch_id": ledger.host_epoch_id}
        reference = block.store.commit("graph_revision.json", pinned, kind="mac_security_revision")
        return {"graph_revision": pinned["revision"], "revision_artifact": reference.to_dict()}
    finally:
        ledger.close()


def investigate(block, inputs):
    report_activity("Investigating temporal behavior", owner_blueprint=BLUEPRINT_ID, step_id=block.step_id, run_dir=block.store.run_dir)
    from .context_graph import enrich

    pinned = block.store.read(inputs["previous"]["revision_artifact"])
    ledger = history(block, pinned["host_epoch_id"])
    try:
        revision = pinned["revision"]
        report = analyze(ledger, revision, investigation_policy())
        reference = block.store.commit("analysis.json", report, kind="mac_security_analysis")
        graph = enrich(block, ledger, report)
        block.store.commit("context_graph.json", graph, kind="mac_security_context_graph")
        return {"case_count": len(report["cases"]), "analysis": reference.to_dict()}
    finally:
        ledger.close()
