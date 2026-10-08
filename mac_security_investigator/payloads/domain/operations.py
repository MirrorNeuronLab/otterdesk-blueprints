"""Bounded specialists; Core owns routing, retries and step completion."""
from pathlib import Path

from .acquisition import acquire_mac
from .configuration import investigation_policy
from .history import history, read, save
from .patterns import analyze


def capture(context, **_):
    marker = Path(context["run_dir"]) / "scan_batch.json"
    if marker.exists():
        scans = read(context, "scan_batch.json")
    else:
        scans = [acquire_mac(context["run_id"], investigation_policy())]
    if not scans or any(s["host_epoch_id"] != scans[0]["host_epoch_id"] for s in scans):
        raise ValueError("all scans must belong to one local host epoch")
    ref = save(context, "scan_batch.json", scans)
    return {"scan_count": len(scans), "scan_batch": ref}, [ref]


def reconcile(context, **_):
    store = history(context)
    try:
        receipts = [store.ingest_scan(scan) for scan in read(context, "scan_batch.json")]
        # Pin once. Another run must not cause this run to consume future knowledge.
        marker = Path(context["run_dir"]) / "graph_revision.json"
        pinned = read(context, "graph_revision.json") if marker.exists() else {
            "revision": store.revision, "receipts": receipts, "host_epoch_id": store.host_epoch_id}
        ref = save(context, "graph_revision.json", pinned)
        return {"graph_revision": pinned["revision"], "revision_artifact": ref}, [ref]
    finally:
        store.close()


def investigate(context, **_):
    from .context_graph import enrich
    store = history(context)
    try:
        revision = read(context, "graph_revision.json")["revision"]
        report = analyze(store, revision, investigation_policy())
        refs = [save(context, "analysis.json", report)]
        graph = enrich(context, store, report)
        refs.append(save(context, "context_graph.json", graph))
        return {"case_count": len(report["cases"]), "analysis": refs[0]}, refs
    finally:
        store.close()


def publish(context, **_):
    from .reporting import publish_report
    return publish_report(context)
