from __future__ import annotations

import json
import importlib.util
from pathlib import Path
import pytest
from mn_sdk.blueprint_support import list_pending_human_requests, record_human_response

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "procurement_manager" / "payloads" / "domain"
spec = importlib.util.spec_from_file_location(
    "procurement_domain", PACKAGE / "__init__.py", submodule_search_locations=[str(PACKAGE)]
)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
import sys
sys.modules["procurement_domain"] = module
spec.loader.exec_module(module)

from procurement_domain.procurement_decision import action_digest, evaluate_case, validate_reviews  # noqa: E402
from procurement_domain.case_packet import emit_review_requests  # noqa: E402


def sample():
    return json.loads((ROOT / "procurement_manager" / "examples" / "procurement_case" / "procurement_case.json").read_text())


def test_sample_known_cost_and_reviews():
    packet = evaluate_case(sample())
    assert packet["status"] == "READY_FOR_REVIEW"
    assert packet["mode"] == "MOCK"
    assert packet["selected_supplier_id"] == "cedar"
    assert packet["required_reviewers"] == ["finance", "legal", "owner", "security"]
    atlas, cedar, delta = packet["quote_outcomes"]
    assert (atlas["cost"]["cash_due_at_order"], atlas["cost"]["known_cost_over_comparison_horizon"]) == ("34500.00", "40500.00")
    assert (cedar["cost"]["cash_due_at_order"], cedar["cost"]["known_cost_over_comparison_horizon"]) == ("34800.00", "34800.00")
    assert float(atlas["cost"]["known_cost_over_comparison_horizon"]) - float(cedar["cost"]["known_cost_over_comparison_horizon"]) == 5700
    assert delta["outcome"] == "NO_RESPONSE"
    assert len(atlas["cost"]["cash_flows"]) == 6


def test_missing_cost_and_failed_fit_never_become_eligible():
    case = sample()
    case["suppliers"][0]["quote"]["shipping"] = None
    case["suppliers"][1]["quote"]["specifications"]["gpu_memory_gb"] = 16
    packet = evaluate_case(case)
    assert packet["status"] == "NEEDS_MORE_QUOTES"
    atlas, cedar, _ = packet["quote_outcomes"]
    assert atlas["cost"]["cash_due_at_order"] is None
    assert "shipping" in atlas["cost"]["unknown_or_unquantified_cost_items"]
    assert cedar["fit"]["status"] == "FAIL"


def test_included_support_is_not_added_twice_and_digest_changes_with_terms():
    case = sample()
    first = evaluate_case(case)
    case["suppliers"][1]["quote"]["specifications"]["warranty_months"] = 12
    second = evaluate_case(case)
    assert first["decision_digest"] != second["decision_digest"]
    assert second["quote_outcomes"][1]["fit"]["status"] == "FAIL"


def test_manual_requires_confirmed_policy():
    case = sample()
    case["mode"] = "MANUAL"
    case["policy"]["confirmed"] = False
    assert evaluate_case(case)["status"] == "WAITING_FOR_USER"


def test_no_response_requires_elapsed_deadline():
    case = sample()
    case["clock"] = case["started_at"]
    packet = evaluate_case(case)
    assert packet["status"] == "WAITING_FOR_EXTERNAL"
    assert packet["quote_outcomes"][2]["outcome"] == "WAITING_FOR_EXTERNAL"


def test_supplier_delay_uses_simulated_clock_without_sleeping():
    case = sample()
    case["clock"] = "2026-10-02T09:00:00-04:00"
    outcomes = evaluate_case(case)["quote_outcomes"]
    assert outcomes[0]["outcome"] == "RECEIVED"
    assert outcomes[1]["outcome"] == "WAITING_FOR_EXTERNAL"
    assert outcomes[1]["expected_at"] == "2026-10-03T09:00:00-04:00"
    case["clock"] = "2026-10-03T09:00:00-04:00"
    assert evaluate_case(case)["quote_outcomes"][1]["outcome"] == "RECEIVED"


def test_action_digest_binds_exact_disclosure_and_body():
    action = {"case_id": "case-1", "revision": 1, "mode": "MOCK", "kind": "RFQ", "recipient": "atlas@example", "body": "Quote five units", "attachment_hashes": [], "disclosure_scope": []}
    original = action_digest(action)
    assert action_digest({**action, "body": "Quote six units"}) != original
    assert action_digest({**action, "attachment_hashes": ["new-hash"]}) != original


def test_decision_digest_excludes_display_clock_but_binds_selected_quote():
    case = sample()
    original = evaluate_case(case)["decision_digest"]
    case["clock"] = "2026-10-07T09:00:00-04:00"
    assert evaluate_case(case)["decision_digest"] == original
    case["suppliers"][1]["quote"]["unit_price"] = "6300.00"
    assert evaluate_case(case)["decision_digest"] != original


def test_reviews_are_bound_to_digest_mode_and_assurance():
    packet = evaluate_case(sample())
    decisions = [
        {"request_id": f"review-{reviewer}", "actor_id": f"simulated-{reviewer}", "expires_at": "2026-10-31T09:00:00-04:00", "reviewer": reviewer, "decision": "approve", "decision_digest": packet["decision_digest"], "mode": "MOCK", "identity_assurance": "SIMULATED"}
        for reviewer in packet["required_reviewers"]
    ]
    assert validate_reviews(packet, decisions)["status"] == "APPROVED"
    decisions[0]["decision_digest"] = "stale"
    assert validate_reviews(packet, decisions)["status"] == "PENDING"
    decisions[0]["decision_digest"] = packet["decision_digest"]
    decisions[0]["identity_assurance"] = "MANUAL_ATTESTATION"
    assert validate_reviews(packet, decisions)["status"] == "PENDING"


def test_conversation_review_requests_are_exact_and_idempotent(tmp_path):
    packet = evaluate_case(sample())
    ctx = {"run_id": "sample-run", "run_dir": str(tmp_path / "sample-run")}
    requests = emit_review_requests(ctx, packet)
    assert len(requests) == 4
    assert emit_review_requests(ctx, packet) == []
    events = [json.loads(line) for line in (tmp_path / "sample-run" / "human.jsonl").read_text().splitlines()]
    assert len(events) == 4
    assert all(packet["decision_digest"] in event["payload"]["prompt"] for event in events)
    assert all(event["payload"]["decision_type"] == "procurement_review" for event in events)
    record_human_response("sample-run", requests[0], {"decision": "approve", "approved": True}, runs_root=tmp_path)
    assert len(list_pending_human_requests("sample-run", runs_root=tmp_path)) == 3


def test_manual_conversation_does_not_offer_external_role_approval(tmp_path):
    case = sample()
    case["mode"] = "MANUAL"
    packet = evaluate_case(case)
    ctx = {"run_id": "manual-run", "run_dir": str(tmp_path / "manual-run")}
    requests = emit_review_requests(ctx, packet)
    assert len(requests) == 1
    assert "-owner-" in requests[0]


def test_supplier_scope_must_be_bounded_and_unambiguous():
    case = sample()
    case["suppliers"].append(dict(case["suppliers"][0]))
    with pytest.raises(ValueError, match="supplier IDs"):
        evaluate_case(case)
