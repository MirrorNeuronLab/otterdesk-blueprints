"""MCP contract and behavior for ct_reader."""
from mcp_contract_support import BlueprintMcpHarness


def test_ct_reader_shared_mcp(tmp_path):
    harness = BlueprintMcpHarness("ct_reader", tmp_path)
    harness.assert_shared_contract()


def test_ct_reader_run_controls(tmp_path):
    harness = BlueprintMcpHarness("ct_reader", tmp_path)
    harness.assert_lifecycle()
