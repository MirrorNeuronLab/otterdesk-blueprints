"""MCP contract and behavior for cctv_operator."""
from mcp_contract_support import BlueprintMcpHarness


def test_cctv_operator_shared_mcp(tmp_path):
    harness = BlueprintMcpHarness("cctv_operator", tmp_path)
    harness.assert_shared_contract()


def test_cctv_operator_run_controls(tmp_path):
    harness = BlueprintMcpHarness("cctv_operator", tmp_path)
    harness.assert_lifecycle()


def test_cctv_operator_domain_operation_is_observed(tmp_path):
    harness = BlueprintMcpHarness("cctv_operator", tmp_path)
    harness.call("start_run", request_id="start")
    receipt = harness.call("set_monitoring_instruction", request_id="domain", **{'instruction': 'Watch the corridor.', 'clear': False, 'analyze_now': True})
    assert receipt["status"] == "accepted"
    assert harness.call("set_monitoring_instruction", request_id="domain", **{'instruction': 'Watch the corridor.', 'clear': False, 'analyze_now': True})["operation_id"] == receipt["operation_id"]
    completed = harness.call("get_operation_status", operation_id=receipt["operation_id"])
    assert completed["status"] == "completed"
    assert len([call for call in harness.calls if call[0] == "set_monitoring_instruction"]) == 1


def test_real_worker_tools_match_the_authored_contract(tmp_path, monkeypatch):
    from mcp_contract_support import assert_worker_registry
    assert_worker_registry("cctv_operator", tmp_path, monkeypatch)
