"""MCP contract and behavior for ros_amr_controller."""
from mcp_contract_support import BlueprintMcpHarness


def test_ros_amr_controller_shared_mcp(tmp_path):
    harness = BlueprintMcpHarness("ros_amr_controller", tmp_path)
    harness.assert_shared_contract()


def test_ros_amr_controller_run_controls(tmp_path):
    harness = BlueprintMcpHarness("ros_amr_controller", tmp_path)
    harness.assert_lifecycle()


def test_ros_amr_controller_domain_operation_is_observed(tmp_path):
    harness = BlueprintMcpHarness("ros_amr_controller", tmp_path)
    harness.call("start_run", request_id="start")
    receipt = harness.call("navigate_to_zone", request_id="domain", **{'zone': 'zone_a'})
    assert receipt["status"] == "accepted"
    assert harness.call("navigate_to_zone", request_id="domain", **{'zone': 'zone_a'})["operation_id"] == receipt["operation_id"]
    completed = harness.call("get_operation_status", operation_id=receipt["operation_id"])
    assert completed["status"] == "completed"
    assert len([call for call in harness.calls if call[0] == "navigate_to_zone"]) == 1


def test_real_worker_tools_match_the_authored_contract(tmp_path, monkeypatch):
    from mcp_contract_support import assert_worker_registry
    assert_worker_registry("ros_amr_controller", tmp_path, monkeypatch)
