"""Immutable matter snapshots and attributable offline review imports in Job-owned storage."""
from datetime import datetime, timezone
import json
from pathlib import Path

from mn_temporal_graph_skill import EvidenceHistory, fingerprint

DISPOSITIONS = {"Reviewed with qualification", "Revised", "Request evidence", "Dismissed"}


def apply_reviews(workspace, reviews):
    if reviews.get("version") != "mn.litigation.review.v1" or reviews.get("matter_id") != workspace["matter_id"]:
        raise ValueError("Review file must belong to this matter and the supported review contract")
    items = reviews.get("decisions")
    if not isinstance(items, list) or len(items) > 500:
        raise ValueError("Review file exceeds the bounded decision contract")
    known = {f["id"]: f for f in workspace["findings"]}
    for item in items:
        if (not isinstance(item, dict) or item.get("action") not in DISPOSITIONS
                or any(not isinstance(item.get(k), str) or not item[k].strip() or len(item[k]) > 4000
                       for k in ("id", "finding_id", "material_digest", "actor", "at", "rationale", "text"))):
            raise ValueError("Review decision requires an attributable action, rationale, exact revision and text")
        parsed = datetime.fromisoformat(item["at"].replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("Review time requires a timezone")
        finding = known.get(item["finding_id"])
        if finding is None:
            continue
        if any(r["id"] == item["id"] and r != item for r in finding["review_history"]):
            raise ValueError("Immutable review decision changed")
        if item not in finding["review_history"]:
            finding["review_history"].append(item)
        # Past wording is preserved. An old decision never approves changed evidence.
        if item["material_digest"] == finding["material_digest"]:
            finding["review_state"] = item["action"]
            finding["reviewed_text"] = item["text"]
        else:
            finding["review_state"] = "Needs reassessment"
    for finding in workspace["findings"]:
        current = [item for item in finding["review_history"] if item["material_digest"] == finding["material_digest"]]
        by_actor = {item["actor"]: item for item in current}
        if len({(item["action"], item["text"]) for item in by_actor.values()}) > 1:
            finding["review_state"] = "Reviewers disagree"


def publish(context, workspace):
    root = Path(context["run_dir"])
    capture = root / "case/workspace_capture.json"
    if capture.exists():
        clock = json.loads(capture.read_text())
    else:
        # This is the ledger's first retained snapshot, not run start, source
        # creation/production time or a claim about earlier investigative discovery.
        clock = {"at": datetime.now(timezone.utc).isoformat()}
        capture.write_text(json.dumps(clock))
    workspace["captured_at"] = clock["at"]
    job_root, job_id = context.get("job_data_dir"), context.get("job_id")
    mode = "Job history" if job_root and job_id else "Single snapshot; Job history unavailable"
    epoch = fingerprint([job_id, workspace["matter_id"], workspace["access_scope"]])
    path = (Path(job_root) / "state" / epoch / "history.sqlite3") if job_root and job_id else root / "case/temporal_history.sqlite3"
    history = EvidenceHistory(path, epoch, max_records=20000, max_bytes=32*1024*1024)
    try:
        source_events = {}
        for event in workspace["temporal"]["events"]:
            source_events.setdefault(event["source_ids"][0], []).append({key: event[key] for key in
                ("kind", "entity", "claim_class", "capability", "time", "fields", "occurrence_key")})
        sources = [{"source_id": s["source_id"], "scope": workspace["access_scope"],
            "availability": "available" if s["text"] is not None else "unsupported", "enumeration": "partial",
            "parser_version": "litigation.workspace.v1", "capabilities": ["source_version", "top_level_email_headers"],
            "records": [{"kind": "state", "entity": s["source_id"], "claim_class": "observed",
                "capability": "source_version", "time": {"earliest": None, "latest": None},
                "fields": {"normalized_sha256": s["content_sha256"], "original_sha256": s["original_sha256"]}},
                *source_events.get(s["source_id"], [])]
                if s["text"] is not None else []} for s in workspace["sources"]]
        if not sources:
            workspace["changes"] = {"mode": mode, "previous_snapshot": None, "items": []}
            return workspace
        run_identity = str(context.get("run_id") or root.name)
        receipt = history.ingest_scan({"host_epoch_id": epoch, "scan_id": fingerprint([run_identity, workspace["snapshot_id"]]),
            "acquisition": {"earliest": clock["at"], "latest": clock["at"]}, "sources": sources})
        revision = receipt["revision"]
        known_events = {(item['source_id'], item['fields'].get('normalized_sha256')): item
            for item in history.assertions(revision, scope=workspace['access_scope']) if item['kind'] == 'event'}
        scans = {item['revision']: item['acquisition']['earliest'] for item in history.scans(revision)}
        for event in workspace['temporal']['events']:
            known = known_events[(event['source_ids'][0], event['fields']['normalized_sha256'])]
            event['known_from_revision'] = known['known_from_revision']
            event['first_known_at'] = scans[known['known_from_revision']]
            event['history_evidence_refs'] = known['evidence_refs']
        previous = history.previous_report(revision)
        allowed = {s["source_id"] for s in workspace["sources"]}
        # An old snapshot supported by now-restricted records cannot enter this package.
        if previous and not set(previous["source_versions"]) <= allowed:
            previous = None
        old_findings = {f["id"]: f for f in (previous or {}).get("findings", [])}
        changes = []
        for finding in workspace["findings"]:
            old = old_findings.get(finding["id"])
            changed = old is None or old["material_digest"] != finding["material_digest"]
            finding["revision"] = (old["revision"] if old else 0) + int(changed)
            finding["review_history"] = old.get("review_history", []) if old else []
            if old and old.get("reviewed_text"):
                finding["reviewed_text"] = old["reviewed_text"]
                finding["review_state"] = "Needs reassessment" if changed else old["review_state"]
            if changed:
                changes.append({"kind": "New finding" if old is None else "Revised finding",
                    "finding_id": finding["id"], "before": old["assessment"] if old else None,
                    "after": finding["assessment"], "basis": "Source basis, counterevidence, gaps or wording changed"})
        old_sources = (previous or {}).get("source_versions", {})
        for source in workspace["sources"]:
            if old_sources.get(source["source_id"]) != source["content_sha256"]:
                changes.append({"kind": "New source" if source["source_id"] not in old_sources else "Revised source",
                    "source_id": source["source_id"], "event_time": "See source chronology; capture date is separate"})
        for identifier, old in old_findings.items():
            if not any(f["id"] == identifier for f in workspace["findings"]):
                changes.append({"kind": "Finding no longer retained", "finding_id": identifier,
                    "before": old["assessment"], "after": "No current retained finding; the prior revision remains historical"})
        review_file = context["payload"].get("review_file")
        if review_file:
            review_path = Path(review_file)
            if review_path.is_symlink() or review_path.stat().st_size > 2*1024*1024:
                raise ValueError("Review file must be a bounded regular JSON file")
            apply_reviews(workspace, json.loads(review_path.read_text()))
        workspace["changes"] = {"mode": mode, "revision": revision,
            "previous_snapshot": previous["snapshot_id"] if previous else None, "items": changes,
            "definition": "Investigation knowledge revisions, separate from source event dates. Counts may overlap."}
        record = {"snapshot_id": workspace["snapshot_id"], "captured_at": clock["at"],
            "source_versions": {s["source_id"]: s["content_sha256"] for s in workspace["sources"]},
            "findings": workspace["findings"], "changes": workspace["changes"]}
        report_id = fingerprint([run_identity, workspace["snapshot_id"]])
        # Exact delivery replay returns the same revisions and decisions.
        existing = history.get_report(report_id)
        if existing:
            if fingerprint(existing) != fingerprint(record):
                raise ValueError("Published investigation snapshot changed on replay")
        else:
            history.save_report(report_id, revision, fingerprint(record), record)
        return workspace
    finally:
        history.close()
