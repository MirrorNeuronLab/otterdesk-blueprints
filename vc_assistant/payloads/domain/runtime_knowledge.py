"""Qualified authored VC knowledge, with explicit event-time uncertainty."""

from datetime import datetime, timezone
import json

from mn_sdk.context_session.contracts import digest


def event_timestamp(value):
    if not isinstance(value, str) or not value:
        return None
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if stamp.tzinfo is None:
        return None
    return stamp.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def latest_source_timestamp(sources):
    clocks = [value for source in sources
              if (value := event_timestamp(source.get("retrieved_at"))) is not None]
    return max(clocks, key=lambda value: datetime.fromisoformat(value.replace("Z", "+00:00")), default="")


def authored_record(record, published_at):
    from mn_context_engine_sdk.intelligent_system import RuntimeRecord

    def cell(value):
        return json.dumps(value, ensure_ascii=False, allow_nan=False).replace("|", "\\u007c")

    event_time = event_timestamp(record.get("timestamp"))
    identity = "vc-" + digest(record)
    fields = {
        "memory_family": record["memory_family"], "snapshot_id": record["snapshot_id"],
        "runtime_kind": record["kind"], "entity_id": record["observation_id"],
        "company": record["company"], "event_timestamp": event_time,
        "event_time_status": "known" if event_time else "unknown",
        "timestamp_basis": "event" if event_time else "runtime_publication",
    }
    for key in ("value", "unit", "claim_type", "claim_family", "source_type", "status", "retrieval_status",
                "quality", "method_id", "score", "agent_id", "operation", "tool_status",
                "source_count", "stop_reason"):
        if key not in record:
            continue
        value = record.get(key)
        if type(value) in {int, float, bool, type(None)} or isinstance(value, str) and len(value) <= 256:
            fields[key] = value
    details = [
        "Recorded runtime knowledge: founder claims, blocked research and method scores",
        "do not independently confirm facts. Missing event_timestamp means event time",
        "is unknown; publication time is not event time.", "",
        "| detail | value |", "| --- | --- |",
    ]
    # Notes preserve complete non-scalar and long values without repeating
    # exact values already present in Facts. Explicit nulls remain in Facts.
    represented = {**fields, "kind": record["kind"],
                   "observation_id": record["observation_id"],
                   "qualification": record.get("qualification") or "unverified",
                   "timestamp": event_time}
    for key, value in record.items():
        if (key not in {"relations", "memory_family", "snapshot_id"}
                and (key not in represented or represented[key] != value)):
            details.append("| " + cell(key) + " | " + cell(value) + " |")
    return RuntimeRecord(
        identity, "VC " + record["kind"] + " " + record["observation_id"],
        event_time or published_at, record.get("qualification") or "unverified",
        fields=fields, notes="\n".join(details),
        relations=tuple((edge["source"], edge["relation"], edge["target"])
                        for edge in record.get("relations", [])),
        kind="hypothesis" if record["kind"] == "claim" else "observation",
    )


def publication_clock(memory, snapshot_id):
    key = ["vc-runtime-publication", snapshot_id]
    saved = memory.restore_checkpoint(key)
    if saved is None:
        saved = {"published_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")}
        # Persist before upload so retry does not author a different event body.
        memory.checkpoint(key, saved)
    return saved["published_at"]
