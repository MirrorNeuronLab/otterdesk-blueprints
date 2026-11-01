"""Human questions follow evidence readiness, without granting execution authority."""
from __future__ import annotations

import copy
import importlib
import json
from pathlib import Path

import pytest
from mn_blueprint_blocks.context import BlockContext
from mn_sdk.blueprint_support import read_human_events, record_human_response
from mn_sdk_common.committed_artifacts import CommittedJsonStore

ROOT = Path(__file__).resolve().parents[1] / "procurement_manager"


@pytest.fixture
def procurement(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "payloads"))
    return {name: importlib.import_module("domain." + name)
            for name in ("procurement_decision", "case_packet", "supervision", "reporting")}


def sample():
    return json.loads((ROOT / "examples/procurement_case/procurement_case.json").read_text())


def context(tmp_path):
    return BlockContext(store=CommittedJsonStore(tmp_path / "run"), invocation_id="handoff",
                        revision="supervision-test", run_id="run")


def test_sample_explains_the_decision_before_technical_packet_details(procurement):
    packet = procurement["procurement_decision"].evaluate_case(sample())
    before = copy.deepcopy(packet)
    report = procurement["case_packet"].render_case_packet(packet)
    assert report.index("## Decision brief") < report.index("## Your next decision") < report.index("## Packet details")
    assert "Cedar Compute has the lowest known cost" in report
    assert "USD 34,800.00" in report and "USD 40,500.00" in report and "USD 5,700.00 lower known cost" in report
    assert "USD 300.00 more cash at order" in report
    assert "not complete total cost of ownership" in report
    assert "No quote by the recorded deadline; no price or rejection is inferred" in report
    assert "Simulation" in report and "does not change the report" in report
    assert "Status at publication" in report and "responses are recorded separately" in report
    assert packet == before


def test_equal_known_cost_is_presented_as_a_tie(procurement):
    case = sample()
    case["suppliers"][0]["quote"]["required_support"] = {"included": True}
    case["suppliers"][1]["quote"]["unit_price"] = "5740.00"
    packet = procurement["procurement_decision"].evaluate_case(case)
    report = procurement["case_packet"].render_case_packet(packet)
    assert "The same known cost as" in report
    assert "0.00 lower known cost" not in report


def test_incomplete_quotes_explain_the_specific_blocker_and_ask_for_evidence(procurement):
    case = sample()
    case["suppliers"][0]["quote"]["shipping"] = None
    case["suppliers"][1]["quote"]["specifications"]["gpu_memory_gb"] = 16
    packet = procurement["procurement_decision"].evaluate_case(case)
    review = procurement["supervision"].build_human_review({"procurement_case": packet})
    report = procurement["case_packet"].render_case_packet(packet)
    assert review["interaction_kind"] == "missing_information" and review["options"] == []
    assert "Not quoted: shipping" in report and "gpu memory gb: fail" in report
    assert "No supplier is ready" in report and "No reviews requested yet" in report
    assert "| Atlas Supply | Meets requirements | Not quoted |" in report


def test_policy_block_preserves_case_identity_and_does_not_offer_approval(procurement):
    case = sample()
    case.update(mode="MANUAL")
    case["policy"]["confirmed"] = False
    packet = procurement["procurement_decision"].evaluate_case(case)
    review = procurement["supervision"].build_human_review({"procurement_case": packet})
    assert packet["case_id"] == case["case_id"] and packet["revision"] == case["revision"]
    assert packet["quote_outcomes"] == [] and packet["review_status"] == "NOT_REQUESTED"
    assert review["summary"] == "Confirm the review policy"
    assert review["options"] == [] and review["blocking"] is False
    assert "reply alone does not confirm" in review["next_step"]
    assert "None" not in procurement["case_packet"].render_case_packet(packet)


def test_outstanding_quotes_get_a_followup_question_instead_of_a_purchase_approval(procurement):
    case = sample()
    case["clock"] = case["started_at"]
    packet = procurement["procurement_decision"].evaluate_case(case)
    review = procurement["supervision"].build_human_review({"procurement_case": packet})
    assert "outstanding quote" in review["prompt"]
    assert "not watching for supplier replies" in review["why_now"]
    assert not any(option["label"] == "Approve" for option in review["options"])


def test_each_required_review_explains_its_own_scope_and_keeps_exact_binding(procurement, tmp_path):
    packet = procurement["procurement_decision"].evaluate_case(sample())
    block = context(tmp_path)
    assert len(procurement["case_packet"].emit_review_requests(block, packet)) == 4
    events = read_human_events("run", runs_root=tmp_path)
    assert events[0]["payload"]["reviewer"] == "owner"
    requests = {event["payload"]["reviewer"]: event["payload"] for event in events}
    assert "cash due at order" in requests["finance"]["prompt"]
    assert "commercial terms" in requests["legal"]["prompt"]
    assert "sensitive data" in requests["security"]["prompt"]
    assert "mandatory requirements" in requests["owner"]["prompt"]
    for request in requests.values():
        assert request["decision_digest"] == packet["decision_digest"]
        assert packet["decision_digest"] not in request["prompt"]
        assert request["interaction_kind"] == "approval" and request["blocking"] is False
        assert len(request["context"]) <= 6
        assert {option["label"] for option in request["options"]} == {"Approve", "Request changes", "Reject"}
        assert "does not change the report" in request["context"][-1]["value"]


@pytest.mark.parametrize("summary, expected", [
    ({}, "Resolve the comparison blocker"),
    ({"preferred_vendor": "Supplier", "budget_status": "not_set"}, "Set the purchase budget"),
    ({"preferred_vendor": "Supplier", "budget_status": "within_budget"}, "Review the shortlist"),
])
def test_market_question_tracks_what_the_comparison_can_support(procurement, summary, expected):
    review = procurement["supervision"].build_human_review({"procurement_summary": summary})
    assert review["summary"] == expected
    assert review["blocking"] is False and "new run" in review["next_step"]
    assert all(option["label"] != "Approve" for option in review["options"])


def test_handoff_replay_never_reopens_a_recorded_question(procurement, tmp_path):
    block = context(tmp_path)
    review = procurement["supervision"].build_human_review({})
    artifact = {"human_review": review}
    ids = procurement["supervision"].emit_handoff_question(block, artifact)
    assert len(ids) == 1
    record_human_response("run", ids[0], {"decision": "respond", "notes": "The budget is still exploratory."}, runs_root=tmp_path)
    assert procurement["supervision"].emit_handoff_question(block, artifact) == []
    assert len(read_human_events("run", runs_root=tmp_path)) == 2


def test_market_report_leads_with_explained_costs_and_one_next_question(procurement):
    artifact = {"preferred_candidate": "candidate", "recommended_action": "consider", "confidence": "low", "currency": "EUR",
                "candidate_comparisons": [{"candidate_id": "candidate", "tco_methodology": {"horizon_years": 5}}],
                "procurement_summary": {"preferred_vendor": "Supplier", "budget_status": "not_set", "landed_acquisition_cost": 100,
                                        "financial_npv_tco": 150, "risk_adjusted_npv_tco": 200},
                "evidence_gaps": ["Written quote needed."]}
    report = procurement["reporting"].render_markdown(artifact)
    assert report.index("## Decision brief") < report.index("## Your next decision") < report.index("## Detailed cost and readiness")
    assert "today's money" in report and "Adds modeled disruption" in report
    assert "Comparison horizon: 5 years. Currency: EUR." in report
    assert "EUR 150.00" in report and "$150.00" not in report
    assert report.count("What is your maximum all-in purchase budget") == 1
    assert "Written quote needed." in report


def test_case_names_cannot_add_markdown_table_columns_or_sections(procurement):
    case = sample()
    case["suppliers"][1]["name"] = "Long | name\n## Injected section<script>"
    packet = procurement["procurement_decision"].evaluate_case(case)
    report = procurement["case_packet"].render_case_packet(packet)
    assert "Long \\| name ## Injected section&lt;script&gt;" in report
    assert "\n## Injected section" not in report and "<script>" not in report


def test_inline_report_and_optional_budget_use_existing_desktop_contract():
    product = json.loads((ROOT / "extensions/product.json").read_text())
    guide = json.loads((ROOT / "extensions/ui.json").read_text())["setup_guide"]
    contracts = json.loads((ROOT / "contracts.json").read_text())
    assert product["capabilities"] == ["conversation_result_text:procurement_manager_report.md"]
    assert any(item["path"] == "procurement_manager_report.md" for item in contracts["outputs"]["artifacts"])
    assert [field["path"] for field in guide["fields"] if field.get("required")] == ["inputs.payload.item_description"]
    profile = json.loads((ROOT / "payloads/prompts/conversation.json").read_text())
    assert all(len(guidance) <= 1000 for guidance in profile["stages"].values())
