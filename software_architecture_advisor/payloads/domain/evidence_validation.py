"""Validate report packets against retained graph receipts and frozen witnesses."""
import hashlib
import json

from .graph import normalize


def verify_packets(report):
    reviews = [f["review"] for f in report["findings"] if f.get("review")]
    if reviews != report.get("decisions", []):
        raise ValueError("Published recommendations differ from independently reviewed decisions")
    queries = {q["id"]: q for q in report["queries"]}
    if len(queries) != len(report["queries"]):
        raise ValueError("Duplicate query IDs in report")
    for q in queries.values():
        if q["status"] != "ok":
            continue
        raw = q.get("raw_result")
        if raw is None or hashlib.sha256(json.dumps(raw, sort_keys=True).encode()).hexdigest() != q["result_sha256"]:
            raise ValueError("Query result hash mismatch")
        observed = [normalize(row.get("fields", row)) for row in raw.get("rows", [])]
        if len(observed) != len(q["rows"]):
            raise ValueError("Query row count differs from raw result")
        for source, row in zip(observed, q["rows"], strict=True):
            if any(row.get(key) != value for key, value in source.items()):
                raise ValueError("Query row differs from raw graph result")
    packets = [f["packet"] for f in report["findings"] if f.get("packet")]
    packets += [d["packet"] for d in report.get("decisions", [])]
    for packet in packets:
        for q in packet["queries"]:
            original = queries.get(q["id"])
            if original is None or q["tool"] != original["tool"] or q["status"] != original["status"]:
                raise ValueError("Packet query has no matching receipt")
            for row in q["rows"]:
                if not any(all(candidate.get(key) == value for key, value in row.items()) for candidate in original["rows"]):
                    raise ValueError("Packet contains an invented graph observation")
        for passage in packet["passages"]:
            evidence = report["evidence"].get(passage["id"])
            if evidence is None or not evidence["text"].startswith(passage["text"]):
                raise ValueError("Packet passage differs from frozen evidence")
            if any(passage[key] != evidence[key] for key in ("path", "line_start", "line_end", "kind")):
                raise ValueError("Packet passage provenance mismatch")
