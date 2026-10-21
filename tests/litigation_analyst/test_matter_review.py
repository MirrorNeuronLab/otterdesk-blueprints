"""Product acceptance guards; fixtures make no live model requests."""
# ruff: noqa: F811 -- Imported pytest fixtures are requested by parameter name.
import hashlib
import json
from copy import deepcopy
from types import SimpleNamespace

import pytest
from test_litigation_analyst import BLUEPRINT, make_context, modules  # noqa: F401


def fixture_matter():
    return json.loads((BLUEPRINT / "examples/approval_reversal_case/matter.json").read_text())


def fixture_sources(matter):
    result = {}
    for row in matter["financial_events"]:
        result.setdefault(row["source_id"], []).append(row["quote"])
    return [SimpleNamespace(source_id=s, text="\n".join(t),
            content_sha256=hashlib.sha256("\n".join(t).encode()).hexdigest()) for s, t in result.items()]


def test_financial_arithmetic_separates_approval_and_reversal(modules):
    from domain.financial_review import build
    matter = fixture_matter()
    result = build(matter, fixture_sources(matter), {})
    transaction = result["transactions"][0]
    assert transaction["posting_reversal_net"] == "0.00"
    assert transaction["request_minus_approval"] == "4500.00"
    assert transaction["net_matches_recorded"] is True
    assert len(result["evidence"]) == 5
    assert "does not establish bank settlement" in transaction["qualification"]


@pytest.mark.parametrize("change", ["amount", "reference", "currency", "quote", "excluded"])
def test_financial_annotations_need_exact_authorized_record(modules, change):
    from domain.financial_review import build
    matter = fixture_matter()
    sources = fixture_sources(matter)
    flag = {}
    if change == "amount": matter["financial_events"][0]["amount"] = "9999"
    if change == "reference": matter["financial_events"][0]["transaction_ref"] = "TX-OTHER"
    if change == "currency": matter["financial_events"][0]["currency"] = "EUR"
    if change == "quote": matter["financial_events"][0]["quote"] += " invented"
    if change == "excluded": flag[matter["financial_events"][0]["source_id"]] = "Excluded"
    with pytest.raises(ValueError):
        build(matter, sources, flag)


def test_duplicate_records_never_double_count_and_conflicts_fail(modules):
    from domain.financial_review import build
    matter = fixture_matter()
    sources = fixture_sources(matter)
    row = deepcopy(matter["financial_events"][2])
    matter["financial_events"].append(row)
    assert len(build(matter, sources, {})["events"]) == 5
    row["event_type"] = "settlement"
    with pytest.raises(ValueError, match="Conflicting"):
        build(matter, sources, {})


def test_matter_schema_and_frozen_replay(modules, tmp_path):
    from domain.matter_intake import prepare
    from litigation_native_test_support import block_context
    context = make_context(tmp_path)
    path = tmp_path / "matter.json"
    context["payload"]["matter_file"] = str(path)
    matter = fixture_matter()
    path.write_text(json.dumps(matter))
    native = block_context(context)
    assert prepare(native, context['payload']) == prepare(native, context['payload'])
    matter["title"] = "Changed"
    path.write_text(json.dumps(matter))
    with pytest.raises(ValueError, match="fresh review run"): prepare(native, context['payload'])
    matter["exclusions"][0]["reviewed_at"] = "Yesterday"
    path.write_text(json.dumps(matter))
    with pytest.raises(ValueError, match="ISO timestamp"): prepare(native, context['payload'])


def test_preflight_failure_precedes_download_and_case_analysis(modules, tmp_path, monkeypatch):
    import domain.model_preflight as preflight
    context = make_context(tmp_path)
    context["config"]["model_preflight"]["enabled"] = True
    client = SimpleNamespace(model="registered-remote")
    def unavailable(*args, **kwargs):
        assert kwargs["client"] is client
        assert kwargs["memory_recall"] is False
        assert "evidence" not in kwargs["request"]
        raise RuntimeError("private provider detail")
    monkeypatch.setattr(preflight, "durable_json_decision", unavailable)
    monkeypatch.setattr(modules["intake"], "prepare_emc2", lambda *a: pytest.fail("Downloaded before preflight"))
    with pytest.raises(ValueError, match="no fallback"):
        modules["intake"].prepare_sources(context, llm_client=client)
    receipt = json.loads((context["run_dir"] / "case/model_preflight.json").read_text())
    assert receipt["model"] == "registered-remote" and receipt["fallback_model"] is None
    assert receipt["case_evidence_sent"] is False
    assert "private provider detail" not in json.dumps(receipt)
    assert not (context["run_dir"] / "case/sources.json").exists()


def test_first_pass_budget_and_structural_index_are_explicit(modules, tmp_path):
    from domain.review_scope import decision_config, limits
    config = make_context(tmp_path)["config"]
    config["review"]["profile"] = "first_pass"
    config["source_relationships"]["mode"] = "hybrid"
    plan = limits(config)
    assert (plan["max_rounds"], plan["max_decisions"], plan["relationship_call_ceiling"]) == (1, 6, 0)
    assert plan["relationship_mode"] == "structural"
    assert decision_config(config)["context_memory"]["policy"]["max_calls"] == 6
    assert config["source_relationships"]["mode"] == "hybrid"
    config["review"]["profile"] = "unknown"
    with pytest.raises(ValueError): limits(config)


def test_manual_exclusion_applies_to_unlabelled_mailbox_children(modules):
    from domain.handling import cleared_observation, review_flags
    documents = [SimpleNamespace(source_id="case:box#1", container_source_id="case:box", text="Unlabelled private record")]
    excluded = [{"source_id": "case:box", "reviewer": "Counsel", "reviewed_at": "2026-10-18T00:00:00Z", "reason": "Outside scope"}]
    flags = review_flags(documents, excluded)
    assert set(flags) == {"case:box#1"}
    assert cleared_observation({"passages": [{"source_id": "case:box#1", "text": "private"}]}, flags) == {"passages": []}


def test_work_requests_do_not_invent_assignees_or_dates(modules):
    from domain.gap_work import project
    h = {"work_items": [{"question": "Confirm settlement?", "requested_record": "TX-104 bank statement",
        "why_it_matters": "Determine whether accounting reversal matches settlement", "closure_condition": "Reconcile signed external record",
        "priority": "High", "priority_basis": "Material loss remains unresolved", "evidence_ids": ["e1"]}]}
    gap = project("Q1", h, {"e1": {}}, [])[0]
    assert gap["owner"] == "Unassigned" and gap["internal_target"] is None
    assert project("Q1", h, {}, []) == []
    assigned = project("Q1", h, {"e1": {}}, [{"question": "Confirm settlement?", "owner": "Counsel"}])[0]
    assert assigned["owner"] == "Counsel"


def test_unexamined_questions_are_not_presented_as_answered(modules, tmp_path):
    from domain.matter_intake import empty
    from domain.review_products import attach
    matter = empty()
    matter["issues"] = [{"id": "Q1", "question": "Was authority sufficient?"}]
    workspace = {"issues": [], "findings": [], "analysis": {"status": "Draft"}, "capabilities": {}, "snapshot_id": "base"}
    result = attach(workspace, {}, matter, [], {}, {"profile": "first_pass"})
    assert result["counsel_issues"][0]["status"] == "Unexamined in this review"
    assert result["analysis"]["partial_review"] is True


def test_offline_evaluation_does_not_equate_numbers_with_accuracy(modules, tmp_path):
    from domain.evaluation import evaluate
    from domain.financial_review import build
    matter = fixture_matter()
    sources = fixture_sources(matter)
    financial = build(matter, sources, {})
    root = tmp_path / "run"
    (root / "case").mkdir(parents=True)
    (root / "case/sources.json").write_text(json.dumps([vars(s) for s in sources]))
    workspace = {"snapshot_id": "snapshot", "evidence": financial["evidence"], "financial_review": financial, "findings": []}
    (root / "case/workspace.json").write_text(json.dumps(workspace))
    result = evaluate(root, BLUEPRINT / "examples/approval_reversal_case/expected.json")
    assert result["mechanical_checks_pass"] is True
    assert result["acceptance"] == "pending_attorney_review"
    workspace["evidence"][0]["text"] += "tampered"
    (root / "case/workspace.json").write_text(json.dumps(workspace))
    assert evaluate(root, BLUEPRINT / "examples/approval_reversal_case/expected.json")["acceptance"] == "failed"


def test_bundled_annotations_match_actual_frozen_normalization(modules, tmp_path):
    context = make_context(tmp_path, BLUEPRINT / "examples/approval_reversal_case/inputs")
    context["payload"]["matter_file"] = str(BLUEPRINT / "examples/approval_reversal_case/matter.json")
    modules["intake"].prepare_sources(context)
    inventory = json.loads((context["run_dir"] / "case/source_inventory.json").read_text())
    assert inventory["matter_sha256"] and inventory["handling_sha256"]
