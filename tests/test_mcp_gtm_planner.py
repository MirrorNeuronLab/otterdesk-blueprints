"""MCP contract and behavior for gtm_planner."""
from mcp_contract_support import BlueprintMcpHarness


def test_gtm_planner_shared_mcp(tmp_path):
    harness = BlueprintMcpHarness("gtm_planner", tmp_path)
    harness.assert_shared_contract()


def test_gtm_planner_run_controls(tmp_path):
    harness = BlueprintMcpHarness("gtm_planner", tmp_path)
    harness.assert_lifecycle()


def test_peer_exchange_cannot_control_runs(tmp_path):
    import asyncio
    from mn_sdk_mcp import JobExchangeStore, create_job_mcp_server
    store = JobExchangeStore(tmp_path / "peer.sqlite3", allowed_root=tmp_path, job_id="peer", blueprint_id="marketing", run_id="run")
    server = create_job_mcp_server(store)
    names = {tool.name for tool in asyncio.run(server.list_tools())}
    assert names == {"get_job_snapshot", "get_job_updates", "get_job_record", "request_peer_input"}
    assert not {"start_run", "pause_run", "resume_run", "stop_run"} & names
