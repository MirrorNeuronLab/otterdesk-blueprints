"""Installed Web Lab Operator supervision contract, independent of a live run."""

from mcp_contract_support import BlueprintMcpHarness


def test_web_lab_operator_shared_mcp(tmp_path):
    BlueprintMcpHarness('web_lab_operator', tmp_path).assert_shared_contract()


def test_web_lab_operator_run_controls(tmp_path):
    BlueprintMcpHarness('web_lab_operator', tmp_path).assert_lifecycle()
