"""MCP contract and behavior for drug_discovery_research_assistant."""
from mcp_contract_support import BlueprintMcpHarness


def test_drug_discovery_research_assistant_shared_mcp(tmp_path):
    harness = BlueprintMcpHarness("drug_discovery_research_assistant", tmp_path)
    harness.assert_shared_contract()


def test_drug_discovery_research_assistant_run_controls(tmp_path):
    harness = BlueprintMcpHarness("drug_discovery_research_assistant", tmp_path)
    harness.assert_lifecycle()
