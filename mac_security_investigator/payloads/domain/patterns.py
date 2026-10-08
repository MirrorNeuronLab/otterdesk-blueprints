"""Startup concerns are deterministic graph matches, never inferred executions."""
from collections import defaultdict

from mn_temporal_graph_skill import compare_time, distinct_occurrences, fingerprint, temporal_path
from mn_temporal_graph_skill.temporal import timestamp

POLICY_VERSION = "mac-log-review-v2"


def _before(a, b):
    return compare_time(a, b)["status"] == "SUPPORTED"


def _supported(r):
    return r["claim_class"] in {"observed", "derived"} and not r.get("conflicts") and r.get("consistent", True)


def _target(r):
    return r["fields"].get("target")


def _coverage(scan, source):
    return {"scan_revision": scan["revision"], "source_id": source["source_id"], "locator": -1}


def _corroborated(history, revision, record, prior, current):
    references = record["fields"].get("corroboration_refs", [])
    scans = {s["scan_id"]: s["revision"] for s in history.scans(revision)}
    for ref in references:
        known = ref.get("scan_revision", scans.get(ref.get("scan_id")))
        if known is None or known > revision or ref.get("source_id") == record["source_id"]:
            continue
        evidence = history.resolve_evidence(ref)
        raw = evidence.get("record")
        receipt = evidence.get("source_receipt", {})
        if (evidence["status"] == "retained" and raw and receipt.get("scope") == record["scope"]
                and "installation" in receipt.get("capabilities", []) and raw.get("capability") == "installation"
                and raw.get("claim_class") == "observed" and raw.get("entity") == record["entity"]
                and not raw.get("conflicts") and raw.get("fields", {}).get("expected_update") is True
                and raw["fields"].get("prior_target") == _target(prior)
                and raw["fields"].get("target") == _target(current)
                and _before(prior, raw) and _before(raw, current)):
            return {**ref, "scan_revision": known}
    return None


def analyze(history, revision, limits):
    size = history.snapshot_size(revision)
    if size["assertions"] > limits["max_history_records"] or size["assertion_bytes"] > limits["max_history_bytes"]:
        return {"schema_version": "mn.mac_security.analysis.v1", "host_epoch_id": history.host_epoch_id,
            "graph_revision": revision, "knowledge_cutoff": revision, "policy_version": POLICY_VERSION,
            "cases": [], "pending_matches": [{"reason": "history_capacity", "resume_revision": revision}],
            "deltas": [], "coverage": [], "completeness": {"status": "INCOMPLETE_SEARCH", "unresolved": ["history_capacity"], "limits": limits},
            "capability_limits": {"TB-02": "NOT_EVALUABLE", "TB-05": "NOT_EVALUABLE"},
            "remediation_performed": False, "current_runtime_status": "unknown"}
    records, scans = history.assertions(revision), history.scans(revision)
    startup_evidence = any("startup_state" in source.get("capabilities", [])
                           for scan in scans for source in scan["sources"])
    collection_scope = "startup_history" if startup_evidence else "macos_unified_logs"
    capability_limits = {"TB-02": "NOT_EVALUABLE", "TB-05": "NOT_EVALUABLE"}
    if not startup_evidence:
        capability_limits.update({"TB-01": "NOT_EVALUABLE", "TB-03": "NOT_EVALUABLE",
                                  "attributed_execution": "NOT_EVALUABLE"})
    states, events, counters = defaultdict(list), defaultdict(list), defaultdict(list)
    for r in records:
        key = (r["scope"], r["entity"])
        if r["kind"] == "state" and r["capability"] == "startup_state":
            states[key].append(r)
        elif r["kind"] == "event" and r["capability"] == "attributed_execution":
            events[key].append(r)
        elif r["kind"] == "counterevidence":
            counters[key].append(r)
    cases, pending, deltas, warnings = [], [], [], []
    if not startup_evidence and any(source["availability"] != "available" or source["enumeration"] != "complete"
                                    for scan in scans for source in scan["sources"]):
        warnings.append("log_coverage_incomplete")
    considered = 0
    for (scope, entity), observed in sorted(states.items()):
        if considered >= limits["max_candidates"]:
            warnings.append("candidate_limit")
            break
        considered += 1
        # Sort by evidence time, independently of ingestion order. Unknown times
        # remain unevaluable rather than being replaced with acquisition time.
        observed.sort(key=lambda r: (timestamp(r["time"]["earliest"]) if r["time"]["earliest"] else float("-inf"), r["assertion_id"]))
        prior = None
        for current in observed:
            if not _supported(current) or not _target(current):
                warnings.append("ambiguous_startup_state")
                continue
            if prior is not None:
                comparable = (prior["source_id"] == current["source_id"]
                              and prior["parser_version"] == current["parser_version"] and _before(prior, current))
                if not comparable:
                    pending.append({"entity": entity, "scope": scope, "pattern_family": "TB-01",
                                    "status": "PARTIAL", "missing": ["comparable_ordered_observations"]})
                elif _target(prior) != _target(current):
                    cases.append(_change_case(history, revision, scope, entity, prior, current,
                                               events[(scope, entity)], counters[(scope, entity)], limits))
                    deltas.append({"kind": "STATE_DIFFERENCE", "entity": entity,
                                   "assertion_ids": [prior["assertion_id"], current["assertion_id"]]})
                else:
                    changed = prior["fields"].get("configuration_sha256") != current["fields"].get("configuration_sha256")
                    deltas.append({"kind": "CONTENT_VERSION_DIFFERENCE" if changed else "UNCHANGED_REOBSERVATION", "entity": entity,
                                   "assertion_ids": [prior["assertion_id"], current["assertion_id"]]})
            else:
                deltas.append({"kind": "FIRST_OBSERVED", "entity": entity, "actual_age": "unknown"})
            prior = current
        # Complete inventories are the only source of scoped absence; a denied
        # middle scan supplies a gap and cannot establish return after absence.
        for a, b in zip(observed, observed[1:]):
            if not _supported(a) or not _supported(b) or not _before(a, b):
                continue
            absent = []
            for scan in scans:
                for source in scan["sources"]:
                    time = source.get("acquisition", scan["acquisition"])
                    if (source["source_id"] == a["source_id"] == b["source_id"] and source["scope"] == scope
                            and source["parser_version"] == a["parser_version"] == b["parser_version"]
                            and source["availability"] == "available" and source["enumeration"] == "complete"
                            and _before(a, {"time": time}) and _before({"time": time}, b)
                            and not any(r["entity"] == entity for r in source.get("records", []))):
                        absent.append(_coverage(scan, source))
            if absent:
                case_id = "case-" + fingerprint([history.host_epoch_id, scope, entity, "TB-03", a["time"], b["time"]])[:24]
                cases.append({"case_id": case_id, "pattern_family": "TB-03", "scope": scope, "anchor": entity,
                    "review_state": "open", "title": "Startup item returned after observed absence", "status": "MATCHED",
                    "distinct_execution_count": 0, "malicious_intent": "not_established",
                    "evidence_refs": [*a["evidence_refs"], *absent, *b["evidence_refs"]],
                    "witness": {"predicate_results": {"present_before": "SUPPORTED", "scoped_absence": "SUPPORTED", "present_after": "SUPPORTED"},
                                "graph_revision": revision, "absence_receipts": absent},
                    "limitations": ["Actor, exact transition time and continuous absence are unknown."]})
                deltas.append({"kind": "RETURN_OBSERVED", "entity": entity, "coverage_witness": absent})
    coverage = [{"scan_id": s["scan_id"], "revision": s["revision"], "source_id": v["source_id"],
                 **{k: v.get(k) for k in ("scope", "availability", "enumeration", "capabilities", "consistency", "gaps",
                                        "requested_path", "requested_window", "processes", "parser_version")}}
                for s in scans for v in s["sources"]]
    if any(c["status"] == "INCOMPLETE_SEARCH" for c in cases):
        warnings.append("graph_traversal_limit")
    for r in records:
        if r["kind"] == "event":
            acquired = next(s["acquisition"] for s in scans if s["revision"] == r["known_from_revision"])
            historical = _before(r, {"time": acquired})
            deltas.append({"kind": "HISTORICAL_EVIDENCE_ADDED" if historical else "DISTINCT_EVENT_ADDED",
                           "assertion_id": r["assertion_id"], "occurrence_time": r["time"],
                           "first_known_revision": r["known_from_revision"], "distinctness": "supported" if r.get("occurrence_key") and not r.get("conflicts") else "unresolved"})
    return {"schema_version": "mn.mac_security.analysis.v1", "host_epoch_id": history.host_epoch_id,
            "graph_revision": revision, "knowledge_cutoff": revision, "policy_version": POLICY_VERSION,
            "collection_scope": collection_scope,
            "cases": cases, "pending_matches": pending, "deltas": deltas, "coverage": coverage,
            "completeness": {"status": "INCOMPLETE_SEARCH" if warnings else
                             "complete_for_declared_startup_scope" if startup_evidence else "complete_for_declared_log_scope",
                             "unresolved": sorted(set(warnings)), "limits": limits},
            "capability_limits": capability_limits,
            "remediation_performed": False, "current_runtime_status": "unknown"}


def _change_case(history, revision, scope, entity, prior, current, events, counters, limits):
    # The connected target-change episode, rather than a scan or title, owns
    # identity. Additional executions and late explanations revise this case.
    identity = [history.host_epoch_id, scope, entity, "TB-01", _target(prior), _target(current), current["time"]]
    case_id = "case-" + fingerprint(identity)[:24]
    activations = [r for r in events if _supported(r) and _target(r) == _target(current)
                   and _before(prior, r) and r["fields"].get("slot_attribution") == "explicit"]
    witness_limited = len(activations) > limits["max_witness_records"]
    activations = sorted(activations, key=lambda r: r["assertion_id"])[:limits["max_witness_records"]]
    count = distinct_occurrences(activations)
    explanations = [r for r in counters if _supported(r) and r["capability"] == "corroborated_expected_update"
                    and r["fields"].get("prior_target") == _target(prior)
                    and r["fields"].get("target") == _target(current)
                    and _before(prior, r) and _before(r, current)
                    and _corroborated(history, revision, r, prior, current)]
    refs = [*prior["evidence_refs"], *current["evidence_refs"], *count["evidence_refs"],
            *(ref for r in explanations for ref in r["evidence_refs"]),
            *(_corroborated(history, revision, r, prior, current) for r in explanations)]
    target_key = "target-" + fingerprint([scope, _target(current)])
    edges = [{**current, "source": entity, "target": target_key, "relation": "DECLARES_TARGET"}]
    for r in activations:
        if r.get("occurrence_key") and not r.get("conflicts"):
            # Executions have explicit slot/target attribution from their own
            # event source. Current configuration is not used as that bridge.
            edges.append({**r, "source": target_key, "target": "execution-" + r["occurrence_key"],
                          "relation": "ATTRIBUTED_EXECUTION"})

    def fetch(frontier, relations, direction, limit):
        selected = [e for e in edges if e["source"] in frontier and e["relation"] in relations]
        return {"edges": selected[:limit], "complete": len(selected) < limit, "unresolved": []}

    graph = temporal_path([entity], ["DECLARES_TARGET", "ATTRIBUTED_EXECUTION"], fetch,
                          host_epoch_id=history.host_epoch_id, scope=scope,
                          max_hops=limits["max_hops"], max_nodes=limits["max_nodes"], max_edges=limits["max_edges"])
    # An event can predate the scan that first observed its configuration. Its
    # own explicit binding is sufficient; the snapshot-to-event path remains
    # rejected if temporally incompatible and is never presented as causal.
    return {"case_id": case_id, "pattern_family": "TB-01", "scope": scope, "anchor": entity,
            "title": "Startup target changed", "status": "INCOMPLETE_SEARCH" if witness_limited or graph["status"] == "INCOMPLETE_SEARCH" else "MATCHED",
            "review_state": "explained" if explanations else "open", "prior_target": _target(prior), "later_target": _target(current),
            "behavioral_support": "supported_state_difference", "security_concern": "explained_expected_update" if explanations else "requires_review",
            "malicious_intent": "not_established", "distinct_execution_count": count["count"],
            "distinct_execution_ids": count["occurrence_ids"], "unresolved_multiplicity": count["unresolved_multiplicity"],
            "execution_count_is_lower_bound": witness_limited,
            "recurrence": "SUPPORTED" if count["count"] >= 2 else "UNKNOWN",
            "evidence_refs": refs, "counterevidence": [r["assertion_id"] for r in explanations],
            "alternatives": ["expected_update", "authorized_configuration_change", "mistaken_identity"],
            "witness": {"witness_id": "witness-" + fingerprint([case_id, revision, refs])[:24],
                        "graph_revision": revision, "pattern_version": 1, "policy_version": POLICY_VERSION,
                        "predicate_results": {"same_scoped_slot": "SUPPORTED", "target_difference": "SUPPORTED", "ordered_observations": "SUPPORTED",
                                              "attributed_activation": "SUPPORTED" if count["count"] else "UNKNOWN"},
                        "change_interval": {"earliest": prior["time"]["earliest"], "latest": current["time"]["latest"],
                                            "qualification": "Difference between non-atomic observations; intermediate states unknown."},
                        "temporal_check": compare_time(prior, current), "graph": graph,
                        "occurrence_basis": count, "cross_run_contribution": sorted({r["scan_revision"] for r in refs})},
            "limitations": ["Exact change time and actor are unknown.", "Continuous execution is not established.",
                            "A changed startup target is not proof of malicious intent.", "Historical execution is available only when source attribution is explicit."]}
