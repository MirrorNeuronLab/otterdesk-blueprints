"""MCP contract and behavior for mac_security_investigator."""
from mcp_contract_support import BlueprintMcpHarness


def test_mac_security_investigator_shared_mcp(tmp_path):
    harness = BlueprintMcpHarness("mac_security_investigator", tmp_path)
    harness.assert_shared_contract()


def test_mac_security_investigator_run_controls(tmp_path):
    harness = BlueprintMcpHarness("mac_security_investigator", tmp_path)
    harness.assert_lifecycle()
