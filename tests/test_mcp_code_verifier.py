"""Shared installed supervision, manual and run-control contracts."""
from mcp_contract_support import BlueprintMcpHarness


def test_code_verifier_shared_mcp(tmp_path):
    BlueprintMcpHarness('code_verifier', tmp_path).assert_shared_contract()


def test_code_verifier_run_controls(tmp_path):
    BlueprintMcpHarness('code_verifier', tmp_path).assert_lifecycle()
