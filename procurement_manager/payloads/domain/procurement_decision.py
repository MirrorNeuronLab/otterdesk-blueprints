"""Pure, evidence-linked procurement assessments used by case workers."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from .procurement_cost import model_cost, money


def digest(value: dict[str, Any]) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()
    return hashlib.sha256(encoded).hexdigest()


def action_digest(action: dict[str, Any]) -> str:
    required = {"case_id", "revision", "mode", "kind", "recipient", "body", "attachment_hashes", "disclosure_scope"}
    if missing := required - action.keys():
        raise ValueError(f"missing action fields: {', '.join(sorted(missing))}")
    if action["mode"] not in {"MOCK", "MANUAL"}:
        raise ValueError("live dispatch is unavailable")
    return digest({key: action[key] for key in sorted(required)})


def validate_reviews(packet: dict[str, Any], decisions: list[dict[str, Any]]) -> dict[str, Any]:
    """Check exact decision grants; this does not authenticate actors or dispatch actions."""
    required = set(packet.get("required_reviewers") or [])
    accepted: set[str] = set()
    rejected: set[str] = set()
    for decision in decisions:
        reviewer = decision.get("reviewer")
        if not decision.get("request_id") or not decision.get("actor_id"):
            continue
        try:
            if datetime.fromisoformat(str(decision.get("expires_at"))) <= datetime.fromisoformat(str(packet.get("as_of"))):
                continue
        except ValueError:
            continue
        if reviewer not in required or decision.get("decision_digest") != packet.get("decision_digest"):
            continue
        if decision.get("mode") != packet.get("mode"):
            continue
        assurance = decision.get("identity_assurance")
        if packet.get("mode") == "MOCK":
            if assurance != "SIMULATED":
                continue
        elif reviewer == "owner":
            if assurance != "LOCAL_OWNER":
                continue
        elif assurance != "VERIFIED_THIRD_PARTY":
            continue
        if decision.get("decision") == "reject":
            rejected.add(reviewer)
        elif decision.get("decision") == "approve":
            accepted.add(reviewer)
    missing = sorted(required - accepted)
    return {"status": "REJECTED" if rejected else "APPROVED" if not missing and packet.get("status") == "READY_FOR_REVIEW" else "PENDING", "accepted": sorted(accepted), "missing": missing, "rejected": sorted(rejected)}


def assess_fit(requirement: dict[str, Any], quote: dict[str, Any]) -> dict[str, Any]:
    checks: dict[str, str] = {}
    checks["quantity"] = "PASS" if quote.get("quantity") == requirement.get("quantity") else "FAIL" if quote.get("quantity") is not None else "UNKNOWN"
    observed = quote.get("specifications") or {}
    for key, minimum in (requirement.get("mandatory") or {}).items():
        actual = observed.get(key)
        checks[key] = "UNKNOWN" if actual is None else "PASS" if actual >= minimum else "FAIL"
    status = "FAIL" if "FAIL" in checks.values() else "UNKNOWN" if "UNKNOWN" in checks.values() else "PASS"
    return {"type": "fit", "status": status, "checks": checks, "evidence_refs": [quote.get("evidence_ref")] if quote.get("evidence_ref") else []}


def assess_policy(requirement: dict[str, Any], policy: dict[str, Any], supplier: dict[str, Any], cost: dict[str, Any]) -> dict[str, Any]:
    cap = requirement.get("cash_cap")
    cash = cost["cash_due_at_order"]
    cap_status = "UNKNOWN" if cap is None or cash is None else "PASS" if money(cash) <= money(cap) else "FAIL"
    required = ["owner"] if policy.get("owner_review") else []
    commitment = cost["known_contractual_commitment"]
    if policy.get("finance_threshold") is not None:
        if commitment is None:
            required.append("finance")
        elif money(commitment) > money(policy["finance_threshold"]):
            required.append("finance")
    vendor = supplier.get("approved_vendor")
    if policy.get("new_vendor_review") and vendor is not True:
        required.append("legal")
    if policy.get("sensitive_data_review") and requirement.get("sensitive_data"):
        required.append("security")
    return {"type": "policy", "cash_cap_status": cap_status, "required_reviewers": sorted(set(required)), "policy_source": policy.get("source"), "policy_confirmed": policy.get("confirmed") is True}


def assess_quote(requirement: dict[str, Any], policy: dict[str, Any], supplier: dict[str, Any], *, today: str) -> dict[str, Any]:
    quote = supplier.get("quote")
    available_at = supplier.get("available_at")
    if isinstance(quote, dict) and available_at and datetime.fromisoformat(today) < datetime.fromisoformat(available_at):
        return {"supplier_id": supplier["id"], "supplier_name": supplier.get("name"), "outcome": "WAITING_FOR_EXTERNAL", "comparable": False, "evidence_refs": [], "expected_at": available_at}
    if not isinstance(quote, dict):
        deadline = supplier.get("deadline")
        outcome = "NO_RESPONSE" if deadline and datetime.fromisoformat(today) >= datetime.fromisoformat(deadline) else "WAITING_FOR_EXTERNAL"
        return {"supplier_id": supplier["id"], "outcome": outcome, "comparable": False, "evidence_refs": [], "deadline": deadline}
    fit = assess_fit(requirement, quote)
    cost = model_cost(quote, int(requirement["horizon_months"]))
    policy_result = assess_policy(requirement, policy, supplier, cost)
    expiry = quote.get("expires")
    validity = "UNKNOWN" if not expiry else "EXPIRED" if date.fromisoformat(expiry) < date.fromisoformat(today[:10]) else "CURRENT"
    comparable = fit["status"] == "PASS" and policy_result["cash_cap_status"] == "PASS" and not any(k in cost["unknown_or_unquantified_cost_items"] for k in ("unit_price", "shipping", "tax", "required_support")) and validity == "CURRENT" and cost["currency"] == requirement["currency"]
    return {
        "supplier_id": supplier["id"], "supplier_name": supplier["name"],
        "outcome": "RECEIVED", "quote_version": quote.get("version"), "validity": validity,
        "fit": fit, "cost": cost, "policy": policy_result,
        "supplier_risk": {"approved_vendor": supplier.get("approved_vendor"), "status": "REVIEW_REQUIRED" if supplier.get("approved_vendor") is not True else "KNOWN_APPROVED"},
        "terms": {"warranty_months": (quote.get("specifications") or {}).get("warranty_months"), "status": "REVIEW_REQUIRED"},
        "comparable": comparable, "evidence_refs": [quote["evidence_ref"]] if quote.get("evidence_ref") else [],
    }


def evaluate_case(case: dict[str, Any]) -> dict[str, Any]:
    if case.get("mode") not in {"MOCK", "MANUAL"}:
        raise ValueError("only MOCK and MANUAL are implemented")
    if not isinstance(case.get("case_id"), str) or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", case["case_id"]) is None:
        raise ValueError("case_id must be a short stable identifier")
    if not isinstance(case.get("revision"), int) or case["revision"] < 1:
        raise ValueError("positive case revision is required")
    suppliers = case.get("suppliers")
    if not isinstance(suppliers, list) or not 1 <= len(suppliers) <= 12:
        raise ValueError("case requires 1 to 12 suppliers")
    ids = [supplier.get("id") for supplier in suppliers if isinstance(supplier, dict)]
    if len(ids) != len(suppliers) or any(not isinstance(value, str) or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", value) is None for value in ids) or len(set(ids)) != len(ids):
        raise ValueError("supplier IDs must be unique short identifiers")
    if case.get("mode") == "MANUAL" and not case.get("policy", {}).get("confirmed"):
        return {"status": "WAITING_FOR_USER", "reason": "No company policy loaded or confirmed. Confirm a local review policy before evaluation."}
    requirement = case["request"]
    results = [assess_quote(requirement, case["policy"], supplier, today=case["clock"]) for supplier in case["suppliers"]]
    responsive = [item for item in results if item["outcome"] == "RECEIVED"]
    comparable = [item for item in responsive if item["comparable"]]
    quorum = int(case["policy"].get("min_comparable_quotes", 1))
    status = "WAITING_FOR_EXTERNAL" if any(item["outcome"] == "WAITING_FOR_EXTERNAL" for item in results) else "READY_FOR_REVIEW" if len(comparable) >= quorum else "NEEDS_MORE_QUOTES"
    selected = min(comparable, key=lambda item: Decimal(item["cost"]["known_cost_over_comparison_horizon"])) if comparable and status == "READY_FOR_REVIEW" else None
    packet = {
        "case_id": case.get("case_id"), "revision": case.get("revision", 1), "mode": case["mode"],
        "as_of": case["clock"], "status": status, "requirements": requirement,
        "policy": case["policy"], "quote_outcomes": results,
        "selected_supplier_id": selected["supplier_id"] if selected else None,
        "selected_quote_version": selected["quote_version"] if selected else None,
        "required_reviewers": selected["policy"]["required_reviewers"] if selected else [],
        "review_status": "PENDING" if selected else "NOT_REQUESTED",
        "pending_actions": [
            {"kind": "REVIEW", "reviewer": reviewer, "status": "PENDING"}
            for reviewer in (selected["policy"]["required_reviewers"] if selected else [])
        ],
        "order_status": "NOT_PREPARED",
        "limitations": ["Energy, resale value, and downtime are unquantified; this is a known-cost subtotal, not complete TCO."],
    }
    packet["decision_digest"] = digest({
        "case_id": packet["case_id"], "revision": packet["revision"], "mode": packet["mode"],
        "requirements": requirement, "policy": case["policy"],
        "selected_quote": next((supplier.get("quote") for supplier in case["suppliers"] if supplier["id"] == selected["supplier_id"]), None) if selected else None,
        "selected_assessment": selected, "required_reviewers": packet["required_reviewers"],
    })
    return packet
