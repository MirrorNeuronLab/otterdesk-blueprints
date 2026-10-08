"""Fixed startup/security log scope; diagnostics never imply execution attribution."""
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path

from mn_macos_logs_skill import read_unified_logs
from mn_temporal_graph_skill import fingerprint

from .acquisition import now


PROCESSES = ("launchd", "syspolicyd", "amfid", "backgroundtaskmanagementagent")


def acquire_logs(epoch, limits):
    end_time = datetime.fromisoformat(now().replace("Z", "+00:00")).replace(microsecond=0)
    start_time = end_time - timedelta(days=1)
    end = end_time.isoformat().replace("+00:00", "Z")
    start = start_time.isoformat().replace("+00:00", "Z")
    source = {"source_id": "unified-security-log", "scope": "system",
              "source_name": "Mac startup and security logs", "requested_path": "macOS unified log datastore",
              "capabilities": ["diagnostic_event"], "parser_version": "unified-log-metadata-v1",
              "consistency": "non_atomic", "acquisition": {"earliest": end, "latest": None},
              "requested_window": {"earliest": start, "latest": end}, "processes": list(PROCESSES),
              "records": [], "gaps": ["retention_and_private_value_redaction",
                                        "diagnostics_do_not_establish_startup_execution"]}
    result = read_unified_logs(start=start, end=end, processes=PROCESSES,
                              max_bytes=limits["max_log_bytes"], timeout=limits["log_timeout_seconds"])
    source.update(availability=result["availability"], enumeration=result["enumeration"])
    source["gaps"].extend(result["gaps"])
    for line in result["data"].splitlines():
        if not line.strip():
            continue
        if len(source["records"]) >= limits["max_log_records"]:
            source["enumeration"] = "partial"
            source["gaps"].append("record_limit")
            break
        try:
            value = json.loads(line)
            timestamp = datetime.fromisoformat(value["timestamp"].replace("Z", "+00:00"))
            if timestamp.utcoffset() is None:
                raise ValueError("unknown log timezone")
            stamp = timestamp.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
            if not start_time <= timestamp <= end_time:
                raise ValueError("log record outside selected time window")
            process = Path(value["processImagePath"]).name
            if process not in PROCESSES:
                raise ValueError("log record outside selected process scope")
            fields = {"process": process, "log_record_sha256": hashlib.sha256(line).hexdigest(),
                      "redaction": "Message text, arguments and other log values are not retained."}
            for key in ("bootUUID", "subsystem", "category", "messageType"):
                if isinstance(value.get(key), str) and len(value[key]) <= 256:
                    fields[key] = value[key]
            source["records"].append({"kind": "event", "entity": "logger-" + fingerprint([epoch, process]),
                "capability": "diagnostic_event", "claim_class": "observed", "fields": fields,
                "time": {"earliest": stamp, "latest": stamp}})
        except (KeyError, ValueError, TypeError, AttributeError):
            source["enumeration"] = "partial"
            if "unparsed_or_out_of_scope_record" not in source["gaps"]:
                source["gaps"].append("unparsed_or_out_of_scope_record")
    source["acquisition"]["latest"] = now()
    return source
