"""MCP contract and behavior for financial_advisor."""
from mcp_contract_support import BlueprintMcpHarness


def test_financial_advisor_shared_mcp(tmp_path):
    harness = BlueprintMcpHarness("financial_advisor", tmp_path)
    harness.assert_shared_contract()


def test_financial_advisor_run_controls(tmp_path):
    harness = BlueprintMcpHarness("financial_advisor", tmp_path)
    harness.assert_lifecycle()
