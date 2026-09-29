"""Validate untrusted review records and exact snapshot citations."""

from .review_packets import APPLICABILITY, COVERAGE, CLAIM_TYPES, CONFIDENCE


def text(value, name, limit=6000):
    if not isinstance(value, str) or not value.strip() or len(value.encode()) > limit:
        raise ValueError(f"Invalid {name}")
    return value


def rows(value, key, limit=30):
    items = value.get(key, [])
    if (
        not isinstance(items, list)
        or len(items) > limit
        or any(not isinstance(v, dict) for v in items)
    ):
        raise ValueError(f"Invalid {key}")
    return items


def strings(value, key, allowed=None):
    result = value.get(key, [])
    if (
        not isinstance(result, list)
        or len(result) > 60
        or any(not isinstance(x, str) for x in result)
    ):
        raise ValueError(f"Invalid {key}")
    if allowed is not None and not set(result) <= set(allowed):
        raise ValueError(f"Unknown {key}")
    return result


def citation(value, snapshot):
    if not isinstance(value, dict):
        raise ValueError("Citation must be an object")
    source = snapshot["sources"].get(value.get("path"))
    if not source or value.get("sha256") != source["sha256"]:
        raise ValueError("Citation path/hash mismatch")
    start, end = value.get("start_offset"), value.get("end_offset")
    if (
        type(start) is not int
        or type(end) is not int
        or not 0 <= start < end <= len(source["text"])
    ):
        raise ValueError("Citation offset range invalid")
    if value.get("excerpt") != source["text"][start:end]:
        raise ValueError("Citation excerpt differs from exact offsets")
    if len(value["excerpt"].encode()) > 4000:
        raise ValueError("Citation exceeds excerpt limit")
    first = source["text"].count("\n", 0, start) + 1
    last = source["text"].count("\n", 0, max(start, end - 1)) + 1
    if value.get("start_line") != first or value.get("end_line") != last:
        raise ValueError("Citation line range differs from offsets")
    return {
        k: value[k]
        for k in [
            "path",
            "sha256",
            "start_offset",
            "end_offset",
            "start_line",
            "end_line",
            "excerpt",
        ]
    }


def validate_result(
    task, value, snapshot, packets, requirements=(), allowed_sources=None
):
    if (
        not isinstance(value, dict)
        or value.get("task_id") != task["task_id"]
        or value.get("kind") != task["kind"]
    ):
        raise ValueError("Result task identity mismatch")
    if value.get("status") not in {"completed", "blocked", "not_analyzed"}:
        raise ValueError("Invalid status")
    if value["status"] != "completed":
        return {
            "task_id": task["task_id"],
            "kind": task["kind"],
            "status": value["status"],
            "reason": text(value.get("reason"), "reason"),
            "claims": [],
            "observations": [],
            "proposed_followups": [],
        }
    text(value.get("conclusion"), "conclusion")
    text(value.get("scope"), "scope")
    strings(value, "limitations")
    claims = rows(value, "claims")
    claim_ids = set()
    observations = rows(value, "observations")
    obs_ids = set()
    for claim in claims:
        ident = text(claim.get("claim_id"), "claim_id", 80)
        if ident in claim_ids:
            raise ValueError("Duplicate claim id")
        claim_ids.add(ident)
        for k in ["statement", "rationale", "counterevidence"]:
            text(claim.get(k), k)
        if (
            claim.get("claim_type") not in CLAIM_TYPES
            or claim.get("confidence") not in CONFIDENCE
        ):
            raise ValueError("Invalid claim enums")
        if type(claim.get("finding", False)) is not bool:
            raise ValueError("Invalid finding flag")
        evidence = rows(claim, "evidence", 8)
        if claim["claim_type"] in {"observed", "derived", "inferred"} and not evidence:
            raise ValueError("Evidence required for observed/derived/inferred claim")
        if not evidence and claim["confidence"] not in {"low", "insufficient_evidence"}:
            raise ValueError("Unsupported claim confidence")
    for obs in observations:
        ident = text(obs.get("observation_id"), "observation_id", 80)
        if ident in obs_ids:
            raise ValueError("Duplicate observation id")
        obs_ids.add(ident)
        text(obs.get("summary"), "observation summary")
        if not rows(obs, "evidence", 8):
            raise ValueError("Observation requires evidence")
    for item in claims + observations:
        for c in item.get("evidence", []):
            citation(c, snapshot)
            if allowed_sources is not None and not any(
                c["path"] == a["path"]
                and a["start_offset"]
                <= c["start_offset"]
                < c["end_offset"]
                <= a["end_offset"]
                for a in allowed_sources
            ):
                raise ValueError("Citation was outside reviewed input scope")
    if task["kind"] in {"aspect_analysis", "aspect_challenge"}:
        if value.get("aspect_id") != task["aspect_id"]:
            raise ValueError("Wrong aspect")
        if (
            value.get("applicability") not in APPLICABILITY
            or value.get("coverage") not in COVERAGE
        ):
            raise ValueError("Invalid applicability/coverage")
        text(value.get("applicability_reason"), "applicability_reason")
        if value.get("outcome") not in {
            "finding_identified",
            "no_finding_in_analyzed_scope",
            "undetermined",
        }:
            raise ValueError("Invalid outcome")
        items = rows(value, "content", 40)
        if {r.get("requirement_id") for r in items} != set(requirements) or len(
            items
        ) != len(requirements):
            raise ValueError("Aspect content must address every requirement")
        for item in items:
            text(item.get("answer"), "content answer")
            strings(item, "claim_ids", claim_ids)
            if item.get("status") not in {"addressed", "unknown", "not_applicable"}:
                raise ValueError("Invalid content status")
            if item["status"] == "addressed" and not item.get("claim_ids"):
                raise ValueError("Addressed content requires a claim")
        if value["coverage"] == "complete_for_stated_scope" and any(
            r["status"] == "unknown" for r in items
        ):
            raise ValueError("Unknown requirement cannot be complete")
        if task["kind"] == "aspect_challenge" and value.get("analysis_verdict") not in {
            "supported",
            "contradicted",
            "inconclusive",
        }:
            raise ValueError("Missing challenge verdict")
    if task["kind"] in {"section_synthesis", "executive_synthesis"}:
        strings(value, "source_task_ids", task.get("input_task_ids", []))
        if not value.get("source_task_ids"):
            raise ValueError("Synthesis requires source tasks")
    for rec in rows(value, "recommendations", 10):
        refs = strings(rec, "claim_ids", claim_ids)
        if not refs:
            raise ValueError("Recommendation requires claims")
        for k in [
            "action",
            "alternatives",
            "impact",
            "effort",
            "urgency",
            "priority",
            "prerequisites",
            "risks",
            "validation",
            "success_conditions",
            "next_decision",
        ]:
            text(rec.get(k), k)
    for item in rows(value, "verification_tasks", 15):
        for k in ["question", "method", "required_input", "acceptance"]:
            text(item.get(k), k)
        strings(item, "claim_ids", claim_ids)
    for item in rows(value, "assumptions", 10):
        for k in ["statement", "decision_affected", "verification"]:
            text(item.get(k), k)
    for item in rows(value, "work_packages", 10):
        if not strings(item, "claim_ids", claim_ids):
            raise ValueError("Work package requires claims")
        for k in [
            "goal",
            "constraints",
            "non_goals",
            "migration_steps",
            "required_tests",
            "acceptance",
            "stop_conditions",
        ]:
            text(item.get(k), k)
        strings(item, "files", snapshot["sources"])
        if not item.get("files"):
            raise ValueError("Work package requires actual files")
    seen = set()
    for proposal in rows(value, "proposed_followups", 4):
        if proposal.get("packet_id") not in packets:
            raise ValueError("Unknown followup packet")
        text(proposal.get("reason"), "followup reason", 2000)
        if not strings(proposal, "evidence_refs", claim_ids | obs_ids):
            raise ValueError("Followup requires evidence refs")
        key = (proposal["packet_id"], proposal["reason"].strip().lower())
        if key in seen:
            raise ValueError("Duplicate followup")
        seen.add(key)
    return value
