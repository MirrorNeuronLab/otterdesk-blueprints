"""MCP contract and behavior for procurement_manager."""
from mcp_contract_support import BlueprintMcpHarness


def test_procurement_manager_shared_mcp(tmp_path):
    harness = BlueprintMcpHarness("procurement_manager", tmp_path)
    harness.assert_shared_contract()


def test_procurement_manager_run_controls(tmp_path):
    harness = BlueprintMcpHarness("procurement_manager", tmp_path)
    harness.assert_lifecycle()
