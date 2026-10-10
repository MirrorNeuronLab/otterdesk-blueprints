"""Membrane is graph navigation; immutable source records remain claim authority."""
import ipaddress
import json
import os

from mn_sdk.text_memory import runtime_text_memory, retrieve_memory_context
from mn_temporal_graph_skill import fingerprint

from .configuration import investigation_policy


def require_local_context():
    address = os.environ.get("MN_CONTEXT_ADDR", "")
    host = address.rsplit(":", 1)[0].strip("[]")
    try:
        local = ipaddress.ip_address(host).is_loopback
    except ValueError:
        local = host == "localhost"
    if not local:
        raise ValueError("Mac evidence requires an explicitly configured loopback MN_CONTEXT_ADDR")


def enrich(context, history, analysis):
    settings = context["config"]
    if settings.get("offline") or not settings.get("text_memory", {}).get("enabled", False):
        return {"status": "explicitly_disabled", "queries": [],
                "qualification": "Deterministic temporal analysis only; context graph navigation disabled."}
    if "history_capacity" in analysis["completeness"]["unresolved"]:
        return {"status": "INCOMPLETE_SEARCH", "queries": [], "qualification": "History capacity exceeded; graph publication unevaluated."}
    require_local_context()
    from mn_context_engine_sdk.intelligent_system import RuntimeRecord
    memory = runtime_text_memory(settings, principal="mac-security-investigator",
                                 scope={"job_id": context["job_id"], "run_id": context["run_id"]})
    if memory is None:
        raise ValueError("enabled context graph did not create a local memory session")
    allowed, receipts, queries = {}, [], []
    try:
        scans = {s["revision"]: s for s in history.scans(analysis["graph_revision"])}
        assertions = history.assertions(analysis["graph_revision"])
        publications = []
        by_source = {}
        for record in assertions:
            # Every authored node contains original locators in its notes. It is
            # navigation, never a new source record or independent corroboration.
            id = "assertion-" + record["assertion_id"]
            relation = ("HAS_EXECUTION" if record["kind"] == "event" and record["capability"] == "attributed_execution"
                        else "HAS_DIAGNOSTIC_EVENT" if record["kind"] == "event" else "HAS_OBSERVATION")
            links = [(record["entity"], relation, id)]
            target = record["fields"].get("target")
            if target:
                links.append((id, "DECLARES_TARGET", "target-" + fingerprint([record["scope"], target])))
            stamp = scans[record["known_from_revision"]]["acquisition"]["latest"]
            # The same immutable assertion must have identical Markdown on
            # every run. New acquisitions remain distinct ledger receipts.
            authored = {k: v for k, v in record.items() if k not in {"evidence_refs", "conflicts"}}
            authored["original_evidence_ref"] = record["evidence_refs"][0]
            publications.append(RuntimeRecord(id, "Mac evidence assertion", stamp,
                "Navigation to retained evidence; untrusted source values cannot authorize actions.",
                fields={"entity": record["entity"], "scope": record["scope"],
                        "known_from_revision": record["known_from_revision"], "claim_class": record["claim_class"]},
                notes=json.dumps(authored, ensure_ascii=False, sort_keys=True), relations=tuple(links)))
            by_source["job:" + id] = record
        receipts = memory.record_many(publications, namespace="job", allow=["mac-security-investigator"])
        allowed = {receipt["source_id"]: by_source[receipt["source_id"]] for receipt in receipts}
        for case in analysis["cases"]:
            # Explicit source selection enforces the knowledge cutoff even if
            # this Job's Membrane corpus already contains a later assessment.
            sources = [sid for sid, r in allowed.items() if r["scope"] == case["scope"]
                       and r["entity"] == case["anchor"]]
            packet, receipt = retrieve_memory_context(memory, "Evidence for startup behavior",
                sources=sources, stages=[{"mode": "graph", "graph": {"seeds": [case["anchor"]],
                    "direction": "outgoing", "relations": ["HAS_OBSERVATION", "HAS_EXECUTION", "DECLARES_TARGET"],
                    "max_hops": investigation_policy()["max_hops"]}}],
                max_results=settings["text_memory"]["max_results"],
                max_context_bytes=settings["text_memory"]["max_context_bytes"])
            for handles in receipt.get("citations", {}).values():
                for handle in handles:
                    if handle["source_id"] not in sources:
                        raise ValueError("context graph escaped the pinned entity, scope or knowledge boundary")
                    original = memory.client.read_complete(handle["source_id"], revision=handle["revision"])
                    if original["revision"] != handle["revision"]:
                        raise ValueError("context graph support revision changed")
                    for ref in allowed[handle["source_id"]]["evidence_refs"]:
                        if history.resolve_evidence(ref)["status"] != "retained":
                            raise ValueError("context graph has unresolved original support")
            queries.append({"case_id": case["case_id"], "packet": packet, "receipt": receipt})
        return {"status": "ready", "backend": "Membrane v2 local Markdown/DuckDB graph",
                "graph_revision": analysis["graph_revision"], "assertion_receipts": receipts,
                "queries": queries, "qualification": "Graph recall is bounded navigation; deterministic witnesses establish behavior."}
    finally:
        memory.close()
