"""Inert SVG projections of supported evidence; no speculative causal arrows."""

def project(history, revision, records_limit):
    items = []
    for scan in history.scans(revision):
        items.append({"kind": "acquisition", "lane": "Scan acquisition", "label": scan["scan_id"],
                      "time": scan["acquisition"], "known_from_revision": scan["revision"]})
    records = history.assertions(revision)
    for record in records[:records_limit]:
        items.append({"kind": record["kind"], "lane": record["scope"] + " · " + record["entity"],
                      "label": record["kind"] + " · " + record["capability"], "time": record["time"],
                      "known_from_revision": record["known_from_revision"], "evidence_refs": record["evidence_refs"],
                      "claim_class": record["claim_class"], "uncertain": bool(record.get("conflicts"))})
    return {"items": items, "complete": len(records) <= records_limit,
            "qualification": "Occurrence/state time and separate scan markers; gaps do not imply continuous observation."}
