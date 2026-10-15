"""MCP contract and behavior for research_assistant."""
from mcp_contract_support import BlueprintMcpHarness


def test_research_assistant_shared_mcp(tmp_path):
    harness = BlueprintMcpHarness("research_assistant", tmp_path)
    harness.assert_shared_contract()


def test_research_assistant_run_controls(tmp_path):
    harness = BlueprintMcpHarness("research_assistant", tmp_path)
    harness.assert_lifecycle()
