"""MCP contract and behavior for vc_assistant."""
from mcp_contract_support import BlueprintMcpHarness


def test_vc_assistant_shared_mcp(tmp_path):
    harness = BlueprintMcpHarness("vc_assistant", tmp_path)
    harness.assert_shared_contract()


def test_vc_assistant_run_controls(tmp_path):
    harness = BlueprintMcpHarness("vc_assistant", tmp_path)
    harness.assert_lifecycle()
