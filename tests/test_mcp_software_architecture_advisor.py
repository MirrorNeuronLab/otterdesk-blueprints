"""MCP contract and behavior for software_architecture_advisor."""
from mcp_contract_support import BlueprintMcpHarness


def test_software_architecture_advisor_shared_mcp(tmp_path):
    harness = BlueprintMcpHarness("software_architecture_advisor", tmp_path)
    harness.assert_shared_contract()


def test_software_architecture_advisor_run_controls(tmp_path):
    harness = BlueprintMcpHarness("software_architecture_advisor", tmp_path)
    harness.assert_lifecycle()
