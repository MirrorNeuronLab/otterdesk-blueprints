import json
import pytest


def events(capsys):
    return [
        json.loads(line.removeprefix("__MN_EVENT__"))
        for line in capsys.readouterr().out.splitlines()
    ]


def action(query):
    return {
        "name": "invoke_skill",
        "arguments": {
            "skill": "mirrorneuron.graph.analysis",
            "operation": "query",
            "arguments": {"rgql": query},
        },
        "reason": "Check correspondent activity",
    }


def test_graph_execution_events_preserve_query_and_omit_evidence(capsys):
    from domain.app.activity import observe_action

    query = "MATCH (n) RETURN n.logical_id LIMIT 2"
    result = {
        "provenance": "observed_graph_query",
        "result": {"rows": [["private evidence"]]},
    }
    assert observe_action(action(query), {"records": [{}]}, lambda *_: result) is result
    started, completed = events(capsys)
    assert started["payload"]["query"] == query
    assert completed["payload"]["engine"] == "MN Graph Engine (Rust)"
    assert completed["payload"]["row_count"] == 1
    assert "private evidence" not in json.dumps([started, completed])


def test_rejected_query_emits_failure_not_engine_success(capsys):
    from domain.app.activity import observe_action

    def reject(*_):
        raise ValueError("graph queries require literal LIMIT in 1..50")

    with pytest.raises(ValueError, match="LIMIT"):
        observe_action(action("MATCH (n) RETURN n"), {"records": [{}]}, reject)
    started, failed = events(capsys)
    assert failed["type"] == "investigation_action_failed"
    assert "LIMIT" in failed["payload"]["message"]
    assert "engine" not in failed["payload"]


def test_query_preview_is_bounded_and_full_action_is_unchanged(capsys):
    from domain.app.activity import observe_action

    request = action("x" * 10000)
    observe_action(request, {"records": [{}]}, lambda *_: {})
    for event in events(capsys):
        assert event["payload"]["query_truncated"]
        assert len(event["payload"]["query"]) == 1000
    assert len(request["arguments"]["arguments"]["rgql"]) == 10000


def test_completed_checkpoint_does_not_reemit_action_events(tmp_path, capsys):
    from domain.app.activity import observe_action
    from mn_prototype_bounded_tool_loop_agent.checkpoint import CheckpointLoop

    def propose(_):
        return {"name": "finish", "arguments": {"reason": "done"}, "reason": "Complete"}

    def execute(action, state):
        return observe_action(action, state, lambda *_: {"reason": "done"})

    path = tmp_path / "checkpoint.json"
    CheckpointLoop(path, {}).run(propose, execute)
    assert len(events(capsys)) == 2
    CheckpointLoop(path, {}).run(propose, execute)
    assert events(capsys) == []
