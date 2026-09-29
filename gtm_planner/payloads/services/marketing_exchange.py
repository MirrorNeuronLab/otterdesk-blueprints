"""Runtime-owned read-only MCP exchange; no domain processing."""
import json
import os
from pathlib import Path
from mn_sdk import Client
from mn_sdk_mcp import JobExchangeStore, run_job_mcp_server
from mn_sdk_mcp.cli import default_store_path, default_port

if __name__ == "__main__":
    client = Client(timeout=15)
    try:
        execution = os.environ["MN_JOB_ID"]
        run = json.loads(client.get_run(execution))
        if run.get("run_id") != execution or not run.get("job_id"):
            raise ValueError("Execution identity mismatch")
        job = json.loads(client.get_job(run["job_id"]))
    finally:
        client.channel.close()
    path = default_store_path()
    store = JobExchangeStore(path, allowed_root=path.parent.parent, job_id=run["job_id"],
        blueprint_id=job["blueprint_id"], run_id=os.environ["MN_RUN_ID"], goal_id="bibblio-marketing")
    run_job_mcp_server(store, host="127.0.0.1", port=default_port())
