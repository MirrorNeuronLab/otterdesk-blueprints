"""MCP contract and behavior for litigation_analyst."""
from mcp_contract_support import BlueprintMcpHarness


def test_litigation_analyst_shared_mcp(tmp_path):
    harness = BlueprintMcpHarness("litigation_analyst", tmp_path)
    harness.assert_shared_contract()


def test_litigation_analyst_run_controls(tmp_path):
    harness = BlueprintMcpHarness("litigation_analyst", tmp_path)
    harness.assert_lifecycle()
