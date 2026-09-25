"""The conversation choice binds to published report bytes and survives retries."""
import hashlib
import json


def test_review_direction_is_report_bound_and_closes_after_response(tmp_path, architecture_paths):
    from domain.review_direction import publish_review_direction
    from mn_sdk.blueprint_support import (
        list_pending_human_requests,
        read_human_events,
        record_human_response,
    )

    run_dir = tmp_path / "run-1"
    run_dir.mkdir()
    report = {
        "status": "review_draft",
        "findings": [
            {"review": {"verdict": "supported"}},
            {"review": {"verdict": "inconclusive"}},
        ],
        "structural_analysis": {"dependency_edges": 7},
    }
    report_bytes = json.dumps(report, sort_keys=True).encode()
    (run_dir / "report.json").write_bytes(report_bytes)
    context = {"run_id": "run-1", "run_dir": str(run_dir)}

    first = publish_review_direction(context, report)
    assert first["decision_digest"] == hashlib.sha256(report_bytes).hexdigest()
    assert publish_review_direction(context, report) == first
    pending = list_pending_human_requests("run-1", runs_root=tmp_path)
    assert len(pending) == 1
    payload = pending[0]["payload"]
    assert payload["request_id"] == first["request_id"]
    assert payload["interaction_kind"] == "judgment"
    assert payload["blocking"] is False
    assert payload["context"][1] == {"label": "Findings", "value": "2 assessed of 2"}
    assert payload["options"][0]["description"]

    record_human_response(
        "run-1", first["request_id"],
        {"response": {"decision": "respond", "action": "Challenge a finding", "notes": "Check incident logs"}},
        runs_root=tmp_path,
    )
    assert list_pending_human_requests("run-1", runs_root=tmp_path) == []
    assert len(read_human_events("run-1", runs_root=tmp_path)) == 2

    report["status"] = "partial"
    (run_dir / "report.json").write_text(json.dumps(report), encoding="utf-8")
    second = publish_review_direction(context, report)
    assert second["request_id"] != first["request_id"]
    assert "partial" in list_pending_human_requests("run-1", runs_root=tmp_path)[0]["payload"]["summary"]


def test_changed_report_supersedes_an_unanswered_choice(tmp_path, architecture_paths):
    from domain.review_direction import publish_review_direction
    from mn_sdk.blueprint_support import list_pending_human_requests, read_human_events

    run_dir = tmp_path / "run-2"
    run_dir.mkdir()
    context = {"run_id": "run-2", "run_dir": str(run_dir)}
    report = {"status": "review_draft", "findings": [], "structural_analysis": {}}
    (run_dir / "report.json").write_text(json.dumps(report), encoding="utf-8")
    first = publish_review_direction(context, report)
    report["status"] = "partial"
    (run_dir / "report.json").write_text(json.dumps(report), encoding="utf-8")
    second = publish_review_direction(context, report)

    pending = list_pending_human_requests("run-2", runs_root=tmp_path)
    assert [event["payload"]["request_id"] for event in pending] == [second["request_id"]]
    assert read_human_events("run-2", runs_root=tmp_path)[1]["payload"] == {
        "request_id": first["request_id"], "reason": "superseded_report"
    }
