import copy
import json


def test_history_bounds_evidence_without_changing_audit():
    from domain.app.prompt_context import investigation_history
    records = [{"action": {"name": "invoke_skill", "arguments": {}},
                "result": {"passages": [{"evidence_id": f"ev-{i}", "text": "x" * 20000} for i in range(30)]}} for _ in range(8)]
    original = copy.deepcopy(records)
    view = investigation_history(records)
    assert view and len(json.dumps(view).encode()) < 12100
    assert view[-1]["result"]["passages"][0]["evidence_id"] == "ev-0"
    assert view[-1]["context_preview"] is True
    assert "incomplete" in view[-1]["coverage_note"]
    assert records == original


def test_requested_manual_is_not_shortened():
    from domain.app.prompt_context import investigation_history
    record = {"action": {"name": "read_skill"}, "result": {"manual": "manual " * 1000}}
    assert investigation_history([record]) == [record]
